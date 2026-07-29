import sqlite3

import pytest

from crawler import gplay_crawler as gc
from crawl_cli import build_parser, DEFAULT_MAX
from crawl_service import crawl_package
from storage.sqlite_store import init_db, load_crawl_state, count_reviews


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


def test_parser_defaults_and_lang_split():
    args = build_parser().parse_args(["com.x"])
    assert (args.langs, args.country, args.max, args.full, args.sync) == ("all", None, None, False, False)

    args = build_parser().parse_args(["com.x", "--langs", "en,vi", "--full"])
    assert args.full and args.langs == "en,vi"


def test_parser_rejects_conflicting_scopes():
    with pytest.raises(SystemExit):
        build_parser().parse_args(["com.x", "--full", "--max", "100"])
    with pytest.raises(SystemExit):
        build_parser().parse_args(["com.x", "--sync", "--full"])


def test_main_rejects_non_positive_max():
    from crawl_cli import main
    with pytest.raises(SystemExit):
        main(["com.x", "--max", "0"])


def test_crawl_package_fresh_discards_checkpoint(monkeypatch, tmp_path):
    recorded = []
    monkeypatch.setattr(gc.time, "sleep", recorded.append)
    db = str(tmp_path / "fresh.db")
    init_db(db)

    from storage.sqlite_store import save_crawl_state
    prior = gc.CrawlState("com.x", "en", "us")
    prior.cursor = "expired-ckpt"
    prior.status = "throttled"
    save_crawl_state(prior, db)

    received = []

    def fake_fetch(package_id, lang, country, page_size, cursor):
        received.append(cursor)
        return (_page(1), None)

    monkeypatch.setattr(gc, "_fetch_page", fake_fetch)
    summary = crawl_package("com.x", db, ["en"], count=None, fresh=True)

    assert received == [None]  # checkpoint ignored, restarted from newest
    assert summary["en"].status == "complete"


def test_init_db_enables_wal(tmp_path):
    db = str(tmp_path / "wal.db")
    init_db(db)
    with sqlite3.connect(db) as conn:
        assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"


def test_crawl_package_persists_pages_and_terminal_states(monkeypatch, tmp_path, sleeps):
    db = str(tmp_path / "cli.db")
    init_db(db)

    pages_by_lang = {
        "en": iter([(_page(2, "en"), "c1"), (_page(1, "en2"), None)]),
        "vi": iter([(_page(2, "vi"), None)]),
    }
    monkeypatch.setattr(
        gc, "_fetch_page",
        lambda package_id, lang, country, page_size, cursor: next(pages_by_lang[lang]),
    )

    saved_pages = []
    summary = crawl_package(
        "com.x", db, ["en", "vi"], count=None,
        page_callback=lambda lang, s, ins: saved_pages.append((lang, ins)),
    )

    assert summary["en"].status == "complete"
    assert summary["vi"].status == "complete"
    assert count_reviews("com.x", db) == 5
    assert saved_pages == [("en", 2), ("en", 1), ("vi", 2)]
    # Terminal statuses persisted for both languages
    assert load_crawl_state("com.x", "en", "us", db).status == "complete"
    assert load_crawl_state("com.x", "vi", "us", db).status == "complete"


def test_crawl_package_resumes_from_stored_checkpoint(monkeypatch, tmp_path, sleeps):
    db = str(tmp_path / "resume-cli.db")
    init_db(db)

    # Seed a throttled checkpoint as if a previous CLI run was rate-limited
    prior = gc.CrawlState("com.x", "en", "us")
    prior.cursor = "ckpt"
    prior.status = "throttled"
    prior.fetched = 2
    from storage.sqlite_store import save_crawl_state
    save_crawl_state(prior, db)

    received = []

    def fake_fetch(package_id, lang, country, page_size, cursor):
        received.append(cursor)
        return (_page(2, "tail"), None)

    monkeypatch.setattr(gc, "_fetch_page", fake_fetch)

    summary = crawl_package("com.x", db, ["en"], count=None)

    assert received == ["ckpt"]  # resumed, not restarted
    assert summary["en"].status == "complete"
    assert summary["en"].fetched == 4  # cumulative
    assert DEFAULT_MAX > 0  # imported constant stays wired to the CLI default
