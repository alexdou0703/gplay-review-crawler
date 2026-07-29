"""Pure-pandas aggregations behind the Analysis tab.

Every function takes the reviews DataFrame produced by get_reviews() and
returns plain DataFrames ready for charting — no Streamlit, no I/O, so the
logic is unit-testable. `lang` is used as the market proxy throughout:
Google Play does not expose a reviewer's real country (the stored `country`
column is the crawl query's country), review language is the closest signal
for "which market is engaging".
"""

import re
from collections import Counter

import pandas as pd

# Minimal stopword set for complaint/campaign keyword mining. Vietnamese +
# English cover the current use case; Thai text has no word spacing, so
# bigram mining is weak there (documented limitation, needs a tokenizer).
STOPWORDS = {
    "và", "là", "của", "có", "không", "tôi", "mình", "bị", "cho", "này", "thì",
    "nó", "được", "quá", "rất", "lại", "mà", "các", "khi", "đã", "vì", "nhưng",
    "cũng", "một", "ứng", "dụng", "app", "cái", "còn", "như", "giờ", "nên",
    "the", "i", "to", "a", "it", "my", "and", "is", "this", "you", "for", "of",
}


def prepare(df: pd.DataFrame) -> pd.DataFrame:
    """Parse review timestamps and drop rows without one. Idempotent."""
    out = df.copy()
    out["dt"] = pd.to_datetime(out["review_created_at"], errors="coerce")
    return out.dropna(subset=["dt"])


def volume_rating_by_period(df: pd.DataFrame, freq: str = "W") -> pd.DataFrame:
    """Review volume + average rating per period. freq: 'W' weeks, 'ME' months."""
    g = (
        df.set_index("dt")
        .resample(freq)
        .agg(n=("score", "size"), avg_score=("score", "mean"))
        .reset_index()
        .rename(columns={"dt": "period"})
    )
    return g


def detect_spikes(
    vol: pd.DataFrame, factor: float = 2.0, min_reviews: int = 30, window: int = 8
) -> pd.DataFrame:
    """Flag periods whose volume jumps well above the recent baseline.

    Baseline = rolling median of the PRIOR `window` periods (shifted, so a
    spike doesn't inflate its own baseline). A spike must beat factor×baseline
    and an absolute floor so tiny datasets don't flag noise. Each spike gets a
    tone: volume surges with clearly better-than-usual ratings look like a
    campaign/feature push, clearly worse look like a backlash event.
    """
    out = vol.copy()
    out["baseline"] = out["n"].shift(1).rolling(window, min_periods=max(2, window // 2)).median()
    out["is_spike"] = (
        out["baseline"].notna()
        & (out["n"] >= factor * out["baseline"])
        & (out["n"] >= min_reviews)
    )

    overall = (out["avg_score"] * out["n"]).sum() / max(out["n"].sum(), 1)
    def tone(row):
        if not row["is_spike"]:
            return ""
        if row["avg_score"] >= overall + 0.4:
            return "positive"
        if row["avg_score"] <= overall - 0.4:
            return "negative"
        return "mixed"
    out["tone"] = out.apply(tone, axis=1)
    return out


def lang_share_by_period(df: pd.DataFrame, freq: str = "ME") -> pd.DataFrame:
    """Review count and share per language per period (market-push signal)."""
    g = (
        df.dropna(subset=["lang"])
        .set_index("dt")
        .groupby([pd.Grouper(freq=freq), "lang"])
        .size()
        .rename("n")
        .reset_index()
        .rename(columns={"dt": "period"})
    )
    totals = g.groupby("period")["n"].transform("sum")
    g["share"] = g["n"] / totals
    return g


def version_timeline(df: pd.DataFrame, min_reviews: int = 30) -> pd.DataFrame:
    """Per app version: first appearance in reviews (release proxy), volume,
    average rating. Sorted by first_seen so regressions read chronologically."""
    v = (
        df.dropna(subset=["app_version"])
        .groupby("app_version")
        .agg(first_seen=("dt", "min"), n=("score", "size"), avg_score=("score", "mean"))
        .reset_index()
    )
    v = v[v["n"] >= min_reviews].sort_values("first_seen")
    return v


def top_bigrams(texts: pd.Series, top: int = 12) -> list[tuple[str, int]]:
    """Most common word pairs in the given review texts, stopwords filtered.
    Bigrams keep compound phrases intact ('xác minh', 'quảng cáo')."""
    counter: Counter = Counter()
    for text in texts.fillna(""):
        words = [
            w for w in re.findall(r"\w+", text.lower())
            if w not in STOPWORDS and len(w) > 1 and not w.isdigit()
        ]
        counter.update(zip(words, words[1:]))
    return [(f"{a} {b}", c) for (a, b), c in counter.most_common(top)]


def spike_details(
    df: pd.DataFrame, spikes: pd.DataFrame, freq: str = "W"
) -> list[dict]:
    """Explain each flagged spike: window, volume vs baseline, rating, which
    languages drove it, versions that first appeared in it, top phrases.

    This is the "what campaign / which market / what update" view.
    """
    versions = version_timeline(df, min_reviews=1)
    offset = pd.tseries.frequencies.to_offset(freq)
    details = []
    for _, row in spikes[spikes["is_spike"]].iterrows():
        start = row["period"] - offset
        end = row["period"]
        window_df = df[(df["dt"] > start) & (df["dt"] <= end)]
        lang_counts = window_df["lang"].value_counts()
        new_versions = versions[
            (versions["first_seen"] > start) & (versions["first_seen"] <= end)
        ]["app_version"].tolist()
        details.append({
            "period": end,
            "n": int(row["n"]),
            "baseline": float(row["baseline"]),
            "avg_score": float(row["avg_score"]),
            "tone": row["tone"],
            "langs": lang_counts.head(3).to_dict(),
            "new_versions": new_versions,
            "bigrams": top_bigrams(window_df["content"], top=8),
        })
    return details
