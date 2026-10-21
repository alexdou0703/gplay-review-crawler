import pandas as pd

from analysis.review_analytics import (
    prepare, top_language_share, data_fingerprint,
    volume_rating_by_period, detect_spikes,
)


def test_prepare_normalizes_timezone_null_dimensions_and_duplicates():
    df = pd.DataFrame([
        {"review_id": "r1", "review_created_at": "2026-01-01T10:00:00+07:00", "lang": " ", "app_version": "", "reply_content": "  "},
        {"review_id": "r1", "review_created_at": "2026-01-01T10:00:00Z", "lang": "vi", "app_version": "1.0", "reply_content": "ok"},
        {"review_id": "r2", "review_created_at": "bad", "lang": None, "app_version": None, "reply_content": None},
    ])
    out = prepare(df)
    assert len(out) == 1
    assert str(out.iloc[0]["lang"]) == "vi"
    assert out.iloc[0]["reply_content"] == "ok"
    assert str(out["dt"].dtype).startswith("datetime64[us, UTC]") or "UTC" in str(out["dt"].dtype)


def test_language_tail_is_explicit_other_and_reconciles():
    rows = []
    for lang in ["en", "vi", "de", "fr"]:
        rows += [{"review_created_at": "2026-01-01", "lang": lang, "score": 5}]
    out = top_language_share(prepare(pd.DataFrame(rows)), "ME", top_n=2)
    assert "Other" in set(out["lang"])
    assert len(set(out["lang"])) == 3
    assert out.groupby("period")["share"].sum().round(6).eq(1).all()


def test_fingerprint_changes_when_dataset_changes():
    a = pd.DataFrame([{"review_created_at": "2026-01-01", "crawled_at": "a"}])
    b = pd.DataFrame([{"review_created_at": "2026-01-01", "crawled_at": "b"}])
    assert data_fingerprint(a) != data_fingerprint(b)


def test_empty_calendar_period_is_not_a_measured_spike_baseline():
    rows = [
        {"review_created_at": "2026-01-05", "score": 5},
        {"review_created_at": "2026-01-19", "score": 1},
    ]
    vol = volume_rating_by_period(prepare(pd.DataFrame(rows)), "W")
    assert (~vol["observed"]).any()
    assert not detect_spikes(vol, min_reviews=1, window=2)["is_spike"].any()
