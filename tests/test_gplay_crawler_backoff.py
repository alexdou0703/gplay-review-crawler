import pytest

from crawler import gplay_crawler as gc


def _page(n, prefix="r"):
    return [
        {"reviewId": f"{prefix}{i}", "content": "x", "score": 5, "thumbsUpCount": 0}
        for i in range(n)
    ]


@pytest.fixture
def sleeps(monkeypatch):
    recorded = []
    monkeypatch.setattr(gc.time, "sleep", recorded.append)
    return recorded


def _run(monkeypatch, responses, count=500):
    """Drive crawl_reviews_iter against scripted _fetch_page responses.

    Each response is either (items, next_cursor) or an Exception to raise.
    Returns (yielded pages, CrawlState, requested page sizes).
    """
    requested_sizes = []
    seq = iter(responses)

    def fake_fetch(package_id, lang, country, page_size, cursor):
        requested_sizes.append(page_size)
        r = next(seq)
        if isinstance(r, Exception):
            raise r
        return r

    monkeypatch.setattr(gc, "_fetch_page", fake_fetch)
    state = gc.CrawlState("com.x", "en", "us")
    pages = list(gc.crawl_reviews_iter("com.x", count=count, state=state))
    return pages, state, requested_sizes


def test_repeated_fetch_errors_backoff_then_throttled(monkeypatch, sleeps):
    responses = [ConnectionError("HTTP 429")] * (len(gc.BACKOFF_DELAYS) + 1)
    pages, state, _ = _run(monkeypatch, responses)

    assert pages == []
    assert state.status == "throttled"
    assert "429" in state.error_msg
    assert sleeps == gc.BACKOFF_DELAYS  # exact backoff schedule


def test_empty_page_with_live_cursor_backoff_then_throttled(monkeypatch, sleeps):
    responses = [([], "live-cursor")] * (len(gc.BACKOFF_DELAYS) + 1)
    pages, state, _ = _run(monkeypatch, responses)

    assert pages == []
    assert state.status == "throttled"
    assert sleeps == gc.BACKOFF_DELAYS


def test_empty_page_without_cursor_is_complete_without_retry(monkeypatch, sleeps):
    pages, state, _ = _run(monkeypatch, [([], None)])

    assert pages == []
    assert state.status == "complete"
    assert sleeps == []


def test_recovery_after_transient_error_continues_and_completes(monkeypatch, sleeps):
    responses = [
        ConnectionError("blip"),   # transient failure
        (_page(3), "c1"),          # recovers
        (_page(2, "s"), None),     # last page
    ]
    pages, state, _ = _run(monkeypatch, responses)

    assert [len(p) for p in pages] == [3, 2]
    assert state.status == "complete"
    assert state.fetched == 5
    assert sleeps[0] == gc.BACKOFF_DELAYS[0]  # one backoff, then normal page delay


def test_count_cap_is_exact_no_overshoot(monkeypatch, sleeps):
    responses = [(_page(200), "c1"), (_page(200, "s"), "c2")]
    pages, state, requested_sizes = _run(monkeypatch, responses, count=300)

    assert requested_sizes == [200, 100]  # second request asks only the remainder
    # Scripted fake returns more than asked; the cap governs what we request,
    # so total fetched equals what the pages contained but no third page is pulled.
    assert len(pages) == 2
    assert state.status == "complete"


def test_reviews_tagged_with_lang_and_country(monkeypatch, sleeps):
    pages, _, _ = _run(monkeypatch, [(_page(2), None)])
    for r in pages[0]:
        assert r["lang"] == "en"
        assert r["country"] == "us"


def test_all_languages_dedups_and_reports_per_lang_status(monkeypatch, sleeps):
    monkeypatch.setattr(gc, "ALL_LANGUAGES", ["en", "vi", "de"])
    shared = _page(3)  # same reviews served under en and vi

    def fake_fetch(package_id, lang, country, page_size, cursor):
        if lang == "de":
            raise RuntimeError("boom")
        return ([dict(r) for r in shared], None)

    monkeypatch.setattr(gc, "_fetch_page", fake_fetch)

    saved = []
    merged, summary = gc.crawl_reviews_all_languages(
        "com.x", count_per_lang=10, on_batch=lambda lang, b, state: saved.append((lang, len(b)))
    )

    assert len(merged) == 3  # vi duplicates dropped
    assert saved == [("en", 3)]  # only new reviews reach on_batch
    assert summary["en"].status == "complete"
    assert summary["vi"].status == "complete"
    assert summary["de"].status == "throttled"  # persistent fetch failure = partial, resumable
    assert "boom" in summary["de"].error_msg


def test_on_batch_failure_propagates_as_fatal(monkeypatch, sleeps):
    monkeypatch.setattr(gc, "ALL_LANGUAGES", ["en", "vi"])
    monkeypatch.setattr(gc, "_fetch_page", lambda *a, **k: (_page(2), None))

    def broken_sink(lang, batch, state):
        raise OSError("disk full")

    with pytest.raises(OSError):
        gc.crawl_reviews_all_languages("com.x", on_batch=broken_sink)
