import pandas as pd
import pytest

from analysis.review_analytics import (
    prepare, volume_rating_by_period, detect_spikes, lang_share_by_period,
    version_timeline, top_bigrams, spike_details,
)


def _df(rows):
    return prepare(pd.DataFrame(rows))


def _review(date, score=5, lang="vi", version="1.0", content="hay lắm"):
    return {
        "review_created_at": date, "score": score, "lang": lang,
        "app_version": version, "content": content, "reply_content": "",
    }


@pytest.fixture
def steady_then_spike():
    """10 weeks of ~40 reviews/week, then one week of 200 low-score reviews."""
    rows = []
    for week in range(10):
        day = pd.Timestamp("2026-01-05") + pd.Timedelta(weeks=week)
        rows += [_review(str(day), score=4) for _ in range(40)]
    spike_day = pd.Timestamp("2026-01-05") + pd.Timedelta(weeks=10)
    rows += [_review(str(spike_day), score=1, content="quảng cáo nhiều bắt xác minh tuổi",
                     version="2.0") for _ in range(200)]
    return _df(rows)


def test_prepare_drops_undated_rows():
    df = _df([_review("2026-01-01"), _review("not-a-date"), _review("")])
    assert len(df) == 1


def test_spike_detected_with_negative_tone(steady_then_spike):
    vol = detect_spikes(volume_rating_by_period(steady_then_spike, "W"))
    spikes = vol[vol["is_spike"]]
    assert len(spikes) == 1
    assert spikes.iloc[0]["n"] == 200
    assert spikes.iloc[0]["tone"] == "negative"  # low-score surge = backlash


def test_no_spike_on_steady_volume():
    rows = []
    for week in range(12):
        day = pd.Timestamp("2026-01-05") + pd.Timedelta(weeks=week)
        rows += [_review(str(day)) for _ in range(50)]
    vol = detect_spikes(volume_rating_by_period(_df(rows), "W"))
    assert not vol["is_spike"].any()


def test_small_bumps_below_min_reviews_not_flagged():
    rows = []
    for week in range(10):
        day = pd.Timestamp("2026-01-05") + pd.Timedelta(weeks=week)
        rows += [_review(str(day)) for _ in range(5)]
    day = pd.Timestamp("2026-01-05") + pd.Timedelta(weeks=10)
    rows += [_review(str(day)) for _ in range(20)]  # 4x baseline but tiny absolute
    vol = detect_spikes(volume_rating_by_period(_df(rows), "W"))
    assert not vol["is_spike"].any()


def test_lang_share_sums_to_one_per_period():
    rows = [_review("2026-01-10", lang="vi")] * 30 + [_review("2026-01-10", lang="th")] * 10
    share = lang_share_by_period(_df(rows), "ME")
    assert share.groupby("period")["share"].sum().round(6).eq(1.0).all()
    vi = share[share["lang"] == "vi"].iloc[0]
    assert vi["share"] == pytest.approx(0.75)


def test_version_timeline_orders_by_first_seen():
    rows = (
        [_review("2026-02-01", version="2.0", score=1)] * 40
        + [_review("2026-01-01", version="1.0", score=5)] * 40
    )
    vt = version_timeline(_df(rows), min_reviews=10)
    assert list(vt["app_version"]) == ["1.0", "2.0"]
    assert vt.iloc[1]["avg_score"] < vt.iloc[0]["avg_score"]


def test_top_bigrams_keeps_compound_phrases():
    texts = pd.Series(["bắt xác minh tuổi", "xác minh phiền phức", "xác minh 123"])
    bigrams = dict(top_bigrams(texts))
    assert "xác minh" in bigrams
    assert bigrams["xác minh"] == 3
    assert not any(p.split()[1].isdigit() for p in bigrams)


def test_spike_details_reports_market_version_and_phrases(steady_then_spike):
    vol = detect_spikes(volume_rating_by_period(steady_then_spike, "W"))
    details = spike_details(steady_then_spike, vol, "W")
    assert len(details) == 1
    d = details[0]
    assert d["langs"].get("vi", 0) >= 200          # which market drove it
    assert "2.0" in d["new_versions"]               # which update landed in the window
    assert any("xác minh" in p for p, _ in d["bigrams"])  # what users complained about
