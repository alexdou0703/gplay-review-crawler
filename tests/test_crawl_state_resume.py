import sqlite3

import pytest

from crawler import gplay_crawler as gc
from storage.sqlite_store import (
    init_db, save_crawl_state, save_reviews_and_state, load_crawl_state, count_reviews,
)


def _page(n, prefix="r"):
    return [
        {"reviewId": f"{prefix}{i}", "content": "x", "score": 5, "thumbsUpCount": 0}
        for i in range(n)
    ]


@pytest.fixture
def db(tmp_path):
    path = str(tmp_path / "resume.db")
    init_db(path)
    return path


@pytest.fixture
def sleeps(monkeypatch):
    recorded = []
    monkeypatch.setattr(gc.time, "sleep", recorded.append)
    return recorded


def test_crawl_state_roundtrip(db):
    state = gc.CrawlState("com.x", "en", "us")
    state.cursor = "ckpt-1"
    state.status = "throttled"
    state.fetched = 180
    state.error_msg = "HTTP 429"
    save_crawl_state(state, db)

    loaded = load_crawl_state("com.x", "en", "us", db)
    assert (loaded.cursor, loaded.status, loaded.fetched, loaded.error_msg) == (
        "ckpt-1", "throttled", 180, "HTTP 429"
    )
    assert load_crawl_state("com.x", "vi", "us", db) is None


def test_save_reviews_and_state_is_one_transaction(db):
    state = gc.CrawlState("com.x", "en", "us")
    state.cursor = "c1"
    state.fetched = 2

    inserted = save_reviews_and_state(_page(2), "com.x", state, db)

    assert inserted == 2
    loaded = load_crawl_state("com.x", "en", "us", db)
    assert loaded.cursor == "c1"
    assert loaded.fetched == 2


def test_save_reviews_and_state_rolls_back_together_on_failure(db, monkeypatch):
    import storage.sqlite_store as store

    def boom(conn, state):
        raise sqlite3.OperationalError("disk I/O error")

    monkeypatch.setattr(store, "_upsert_crawl_state", boom)

    state = gc.CrawlState("com.x", "en", "us")
    state.cursor = "c1"
    with pytest.raises(sqlite3.OperationalError):
        save_reviews_and_state(_page(2), "com.x", state, db)

    # Review rows written before the failing state write must also be gone.
    assert count_reviews("com.x", db) == 0
    assert load_crawl_state("com.x", "en", "us", db) is None


def test_resume_or_fresh_semantics():
    prior = gc.CrawlState("com.x", "en", "us")
    prior.cursor = "ckpt"
    prior.status = "throttled"
    assert gc.resume_or_fresh(prior, "com.x", "en", "us") is prior

    done = gc.CrawlState("com.x", "en", "us")
    done.status = "complete"
    done.cursor = None
    fresh = gc.resume_or_fresh(done, "com.x", "en", "us")
    assert fresh is not done and fresh.cursor is None

    errored = gc.CrawlState("com.x", "en", "us")
    errored.status = "error"
    errored.cursor = "ckpt"
    assert gc.resume_or_fresh(errored, "com.x", "en", "us") is not errored

    assert gc.resume_or_fresh(None, "com.x", "en", "us").cursor is None


def test_iter_resumes_from_stored_cursor(monkeypatch, sleeps):
    received_cursors = []

    def fake_fetch(package_id, lang, country, page_size, cursor):
        received_cursors.append(cursor)
        return (_page(2, "s"), None)

    monkeypatch.setattr(gc, "_fetch_page", fake_fetch)

    state = gc.CrawlState("com.x", "en", "us")
    state.cursor = "ckpt-from-db"
    state.status = "throttled"
    state.fetched = 100

    pages = list(gc.crawl_reviews_iter("com.x", count=200, state=state))

    assert received_cursors[0] == "ckpt-from-db"  # continues, not restarts
    assert len(pages) == 1
    assert state.status == "complete"
    assert state.fetched == 102  # cumulative across resume


def test_interrupt_then_resume_end_to_end(monkeypatch, db, sleeps):
    script = {None: (_page(3, "a"), "c1"), "c1": (_page(3, "b"), "c2"), "c2": (_page(1, "z"), None)}
    monkeypatch.setattr(
        gc, "_fetch_page",
        lambda package_id, lang, country, page_size, cursor: script[cursor],
    )

    # First run: consume one page (with its checkpoint), then get interrupted
    state = gc.CrawlState("com.x", "en", "us")
    pages = gc.crawl_reviews_iter("com.x", count=None, state=state)
    first = next(pages)
    save_reviews_and_state(first, "com.x", state, db)
    pages.close()  # simulates process death after the save

    # Second run: resume from what the DB remembers
    resumed = gc.resume_or_fresh(load_crawl_state("com.x", "en", "us", db), "com.x", "en", "us")
    assert resumed.cursor == "c1"
    rest = [r["reviewId"] for p in gc.crawl_reviews_iter("com.x", count=None, state=resumed) for r in p]

    assert rest == [f"b{i}" for i in range(3)] + ["z0"]  # picks up exactly where it left off
    assert resumed.status == "complete"


def test_all_languages_uses_provided_states(monkeypatch, sleeps):
    monkeypatch.setattr(gc, "ALL_LANGUAGES", ["en", "vi"])
    received = []

    def fake_fetch(package_id, lang, country, page_size, cursor):
        received.append((lang, cursor))
        return (_page(1, lang), None)

    monkeypatch.setattr(gc, "_fetch_page", fake_fetch)

    en_state = gc.CrawlState("com.x", "en", "us")
    en_state.cursor = "en-ckpt"
    en_state.status = "throttled"

    _, summary = gc.crawl_reviews_all_languages("com.x", states={"en": en_state})

    assert ("en", "en-ckpt") in received  # resumed language starts at its checkpoint
    assert ("vi", None) in received       # unlisted language starts fresh
    assert summary["en"] is en_state
