import sqlite3

from storage.sqlite_store import init_db, save_reviews, get_reviews

OLD_SCHEMA = """
CREATE TABLE reviews (
    review_id          TEXT PRIMARY KEY,
    package_id         TEXT NOT NULL,
    username           TEXT,
    user_image         TEXT,
    content            TEXT,
    score              INTEGER,
    thumbs_up          INTEGER,
    review_created_at  TEXT,
    reply_content      TEXT,
    reply_at           TEXT,
    crawled_at         TEXT
);
CREATE TABLE apps (package_id TEXT PRIMARY KEY, app_name TEXT NOT NULL);
"""


def _review(rid, **overrides):
    r = {
        "reviewId": rid,
        "userName": "user",
        "userImage": "",
        "content": "great app",
        "score": 5,
        "thumbsUpCount": 1,
        "at": "2026-07-01 10:00:00",
        "replyContent": "",
        "repliedAt": None,
        "reviewCreatedVersion": "1.2.3",
        "lang": "en",
        "country": "us",
    }
    r.update(overrides)
    return r


def test_migration_adds_columns_and_keeps_rows(tmp_path):
    db = str(tmp_path / "old.db")
    with sqlite3.connect(db) as conn:
        conn.executescript(OLD_SCHEMA)
        conn.execute(
            "INSERT INTO reviews (review_id, package_id, content) VALUES ('r1', 'com.x', 'old row')"
        )

    init_db(db)

    with sqlite3.connect(db) as conn:
        cols = {row[1] for row in conn.execute("PRAGMA table_info(reviews)")}
        assert {"app_version", "lang", "country"} <= cols
        assert conn.execute("SELECT content FROM reviews WHERE review_id='r1'").fetchone()[0] == "old row"


def test_upsert_updates_mutable_fields_preserves_first_seen_lang(tmp_path):
    db = str(tmp_path / "r.db")
    init_db(db)

    assert save_reviews([_review("r1")], "com.x", db) == 1

    # Same review re-fetched under another language, with fresher engagement + a dev reply
    updated = _review(
        "r1", thumbsUpCount=9, replyContent="thanks!", repliedAt="2026-07-02", lang="vi"
    )
    assert save_reviews([updated], "com.x", db) == 0  # no new row

    df = get_reviews("com.x", db)
    row = df.iloc[0]
    assert row["thumbs_up"] == 9
    assert row["reply_content"] == "thanks!"
    assert row["lang"] == "en"  # first-seen lang preserved
    assert row["app_version"] == "1.2.3"


def test_rows_without_review_id_are_skipped(tmp_path):
    db = str(tmp_path / "r.db")
    init_db(db)
    inserted = save_reviews([_review(""), _review("r2")], "com.x", db)
    assert inserted == 1
