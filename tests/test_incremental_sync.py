import pytest

from crawler import gplay_crawler as gc
from crawl_service import sync_package
from storage.sqlite_store import (
    init_db, save_reviews, save_crawl_state, load_crawl_state,
    count_known_review_ids, list_stored_langs, count_reviews,
)


def _page(n, prefix="r"):
    return [
        {"reviewId": f"{prefix}{i}", "content": "x", "score": 5, "thumbsUpCount": 0,
         "lang": "en", "country": "us"}
        for i in range(n)
    ]


@pytest.fixture
def db(tmp_path):
    path = str(tmp_path / "sync.db")
    init_db(path)
    return path


@pytest.fixture
def sleeps(monkeypatch):
    recorded = []
    monkeypatch.setattr(gc.time, "sleep", recorded.append)
    return recorded


def test_count_known_review_ids_chunks_over_500_and_scopes_to_package(db):
    save_reviews(_page(3, "known"), "com.x", db)
    ids = [f"unknown{i}" for i in range(1100)] + ["known0", "known1", "known2"]
    assert count_known_review_ids(ids, "com.x", db) == 3
    assert count_known_review_ids(ids, "com.other", db) == 0  # package-scoped


def test_sync_stops_after_two_consecutive_known_pages(monkeypatch, sleeps):
    fetch_calls = []

    def fake_fetch(package_id, lang, country, page_size, cursor):
        fetch_calls.append(cursor)
        return (_page(3), f"c{len(fetch_calls)}")  # endless known pages

    monkeypatch.setattr(gc, "_fetch_page", fake_fetch)

    pages = list(gc.sync_reviews_iter("com.x", known_count_fn=lambda ids: len(ids)))

    assert len(fetch_calls) == 2  # stop rule kicks in, no endless walk
    assert len(pages) == 2  # known pages still yielded (upsert refreshes them)


def test_sync_fetches_new_then_stops_at_known_region(monkeypatch, sleeps):
    script = [
        (_page(3, "new"), "c1"),   # fresh reviews
        (_page(3, "old"), "c2"),   # fully known
        (_page(3, "older"), "c3"), # fully known → stop
        (_page(3, "never"), "c4"),
    ]
    seq = iter(script)
    monkeypatch.setattr(gc, "_fetch_page", lambda *a, **k: next(seq))

    known = lambda ids: 0 if ids[0].startswith("new") else len(ids)
    pages = list(gc.sync_reviews_iter("com.x", known_count_fn=known))

    yielded = [p[0]["reviewId"] for p in pages]
    assert yielded == ["new0", "old0", "older0"]  # never reaches page 4


def test_sync_on_empty_db_walks_available_history(monkeypatch, sleeps):
    script = [(_page(3, "a"), "c1"), (_page(2, "b"), None)]
    seq = iter(script)
    monkeypatch.setattr(gc, "_fetch_page", lambda *a, **k: next(seq))

    state = gc.CrawlState("com.x", "en", "us")
    pages = list(gc.sync_reviews_iter("com.x", known_count_fn=lambda ids: 0, state=state))

    assert sum(len(p) for p in pages) == 5
    assert state.status == "complete"


def test_sync_ignores_deep_history_checkpoint(monkeypatch, sleeps):
    received_cursors = []

    def fake_fetch(package_id, lang, country, page_size, cursor):
        received_cursors.append(cursor)
        return (_page(2), None)

    monkeypatch.setattr(gc, "_fetch_page", fake_fetch)

    state = gc.CrawlState("com.x", "en", "us")
    state.cursor = "deep-history-ckpt"
    state.status = "throttled"
    list(gc.sync_reviews_iter("com.x", known_count_fn=lambda ids: 0, state=state))

    assert received_cursors == [None]  # starts from newest, not the checkpoint


def test_sync_page_budget_stops_walk_with_partial_status(monkeypatch, sleeps):
    def fake_fetch(package_id, lang, country, page_size, cursor):
        return (_page(3, f"p{cursor}"), f"{cursor}x")  # endless NEW pages

    monkeypatch.setattr(gc, "_fetch_page", fake_fetch)

    state = gc.CrawlState("com.x", "en", "us")
    pages = list(gc.sync_reviews_iter(
        "com.x", known_count_fn=lambda ids: 0, state=state, max_pages=3
    ))

    assert len(pages) == 3  # budget respected — no unbounded history walk
    assert state.status == "partial"


def test_sync_package_uses_stored_country(monkeypatch, db, sleeps):
    rows = [dict(r, country="vn") for r in _page(2, "old")]
    save_reviews(rows, "com.x", db)

    received = []

    def fake_fetch(package_id, lang, country, page_size, cursor):
        received.append(country)
        return ([], None)

    monkeypatch.setattr(gc, "_fetch_page", fake_fetch)
    sync_package("com.x", db)

    assert received == ["vn"]  # syncs under the dataset's country, not "us"


def test_sync_package_saves_new_and_preserves_crawl_state(monkeypatch, db, sleeps):
    # Existing dataset: lang 'en' with 2 old reviews + a throttled deep checkpoint
    save_reviews(_page(2, "old"), "com.x", db)
    ckpt = gc.CrawlState("com.x", "en", "us")
    ckpt.cursor = "deep-ckpt"
    ckpt.status = "throttled"
    ckpt.fetched = 200
    save_crawl_state(ckpt, db)

    script = [(_page(2, "fresh") + _page(2, "old"), None)]  # newest page: 2 new + 2 known
    seq = iter(script)
    monkeypatch.setattr(gc, "_fetch_page", lambda *a, **k: next(seq))

    results = sync_package("com.x", db)

    assert list_stored_langs("com.x", db) == ["en"]  # synced the stored lang
    new_count, state = results["en"]
    assert new_count == 2
    assert count_reviews("com.x", db) == 4
    # Deep-history checkpoint untouched — the next full crawl still resumes it
    stored = load_crawl_state("com.x", "en", "us", db)
    assert (stored.cursor, stored.status, stored.fetched) == ("deep-ckpt", "throttled", 200)
