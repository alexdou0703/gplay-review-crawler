"""SQLite storage layer for Google Play reviews."""

import os
import sqlite3
import pandas as pd
from datetime import datetime, timezone


SCHEMA = """
CREATE TABLE IF NOT EXISTS reviews (
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
    crawled_at         TEXT,
    app_version        TEXT,
    lang               TEXT,
    country            TEXT
);
CREATE INDEX IF NOT EXISTS idx_reviews_package_id ON reviews(package_id);
CREATE TABLE IF NOT EXISTS apps (
    package_id  TEXT PRIMARY KEY,
    app_name    TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS crawl_state (
    package_id  TEXT NOT NULL,
    lang        TEXT NOT NULL,
    country     TEXT NOT NULL,
    cursor      TEXT,            -- Google pagination cursor; NULL = fresh. May stay set on
                                 -- cap-complete states; resume eligibility is gated by status

    status      TEXT NOT NULL,   -- in_progress | throttled | complete | error
    fetched     INTEGER DEFAULT 0,
    error_msg   TEXT,
    updated_at  TEXT NOT NULL,
    PRIMARY KEY (package_id, lang, country)
);
"""

# Columns added after the initial release; ALTER'd in on databases
# created before they existed.
_MIGRATED_COLUMNS = ["app_version", "lang", "country"]


def _migrate(conn: sqlite3.Connection) -> None:
    """Add missing columns to reviews on databases created with an older schema."""
    existing = {row[1] for row in conn.execute("PRAGMA table_info(reviews)")}
    for col in _MIGRATED_COLUMNS:
        if col not in existing:
            conn.execute(f"ALTER TABLE reviews ADD COLUMN {col} TEXT")


def init_db(db_path: str) -> None:
    """Create tables if they don't exist and migrate older databases."""
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        # WAL lets the Streamlit viewer read while a CLI crawl writes.
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript(SCHEMA)
        _migrate(conn)


def _upsert_reviews(conn: sqlite3.Connection, reviews: list[dict], package_id: str) -> int:
    """Upsert review rows on an open connection. Returns newly inserted count."""
    crawled_at = datetime.now(timezone.utc).isoformat()

    rows = [
        (
            r.get("reviewId", ""),
            package_id,
            r.get("userName", ""),
            r.get("userImage", ""),
            r.get("content", ""),
            r.get("score"),
            r.get("thumbsUpCount", 0),
            str(r.get("at", "")),
            r.get("replyContent", ""),
            str(r.get("repliedAt", "")) if r.get("repliedAt") else None,
            crawled_at,
            r.get("reviewCreatedVersion"),
            r.get("lang"),
            r.get("country"),
        )
        for r in reviews
        if r.get("reviewId")  # skip rows without an ID
    ]

    sql = """
        INSERT INTO reviews
            (review_id, package_id, username, user_image, content, score,
             thumbs_up, review_created_at, reply_content, reply_at, crawled_at,
             app_version, lang, country)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(review_id) DO UPDATE SET
            content       = excluded.content,
            score         = excluded.score,
            thumbs_up     = excluded.thumbs_up,
            reply_content = excluded.reply_content,
            reply_at      = excluded.reply_at,
            crawled_at    = excluded.crawled_at,
            app_version   = COALESCE(excluded.app_version, app_version)
    """
    count_sql = "SELECT COUNT(*) FROM reviews WHERE package_id = ?"
    before = conn.execute(count_sql, (package_id,)).fetchone()[0]
    conn.executemany(sql, rows)
    after = conn.execute(count_sql, (package_id,)).fetchone()[0]
    return after - before


def save_reviews(reviews: list[dict], package_id: str, db_path: str) -> int:
    """
    Upsert reviews into DB, keyed by review_id.

    Existing rows get refreshed mutable fields (content, score, thumbs_up,
    dev reply, crawled_at). `lang`/`country` keep their first-seen values:
    cross-language dedup means the same review can arrive again under a
    different query language, which must not clobber its origin market.
    Returns number of newly inserted rows.
    """
    with sqlite3.connect(db_path) as conn:
        return _upsert_reviews(conn, reviews, package_id)


def _upsert_crawl_state(conn: sqlite3.Connection, state) -> None:
    conn.execute(
        """
        INSERT INTO crawl_state
            (package_id, lang, country, cursor, status, fetched, error_msg, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(package_id, lang, country) DO UPDATE SET
            cursor     = excluded.cursor,
            status     = excluded.status,
            fetched    = excluded.fetched,
            error_msg  = excluded.error_msg,
            updated_at = excluded.updated_at
        """,
        (
            state.package_id, state.lang, state.country, state.cursor,
            state.status, state.fetched, state.error_msg,
            datetime.now(timezone.utc).isoformat(),
        ),
    )


def save_reviews_and_state(reviews: list[dict], package_id: str, state, db_path: str) -> int:
    """Persist a page of reviews and its crawl checkpoint in ONE transaction.

    The crawl cursor advances past a page as soon as it is fetched; committing
    rows and cursor together guarantees a resume never skips a page whose rows
    failed to save. Returns number of newly inserted review rows.
    """
    with sqlite3.connect(db_path) as conn:
        inserted = _upsert_reviews(conn, reviews, package_id)
        _upsert_crawl_state(conn, state)
        return inserted


def save_crawl_state(state, db_path: str) -> None:
    """Upsert a crawl checkpoint on its own (e.g. terminal status with no page)."""
    with sqlite3.connect(db_path) as conn:
        _upsert_crawl_state(conn, state)


def load_crawl_state(package_id: str, lang: str, country: str, db_path: str):
    """Return the stored CrawlState for (package, lang, country), or None."""
    from crawler.gplay_crawler import CrawlState  # deferred: avoids import cycle risk

    sql = """
        SELECT cursor, status, fetched, error_msg FROM crawl_state
        WHERE package_id = ? AND lang = ? AND country = ?
    """
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(sql, (package_id, lang, country)).fetchone()
    if row is None:
        return None
    state = CrawlState(package_id, lang, country)
    state.cursor, state.status, state.fetched, state.error_msg = row
    return state


def count_known_review_ids(review_ids: list[str], db_path: str) -> int:
    """Return how many of the given review IDs already exist in the DB.

    Chunked to stay under SQLite's bound-variable limit.
    """
    total = 0
    with sqlite3.connect(db_path) as conn:
        for i in range(0, len(review_ids), 500):
            chunk = review_ids[i:i + 500]
            placeholders = ",".join("?" * len(chunk))
            total += conn.execute(
                f"SELECT COUNT(*) FROM reviews WHERE review_id IN ({placeholders})", chunk
            ).fetchone()[0]
    return total


def list_stored_langs(package_id: str, db_path: str) -> list[str]:
    """Return distinct languages stored for a package (sync targets)."""
    sql = "SELECT DISTINCT lang FROM reviews WHERE package_id = ? AND lang IS NOT NULL"
    with sqlite3.connect(db_path) as conn:
        return [r[0] for r in conn.execute(sql, (package_id,)).fetchall()]


def get_reviews(package_id: str, db_path: str) -> pd.DataFrame:
    """Return all stored reviews for a package as a DataFrame."""
    sql = """
        SELECT review_id, username, score, content, thumbs_up,
               review_created_at, reply_content, crawled_at,
               app_version, lang, country
        FROM reviews
        WHERE package_id = ?
        ORDER BY review_created_at DESC
    """
    with sqlite3.connect(db_path) as conn:
        return pd.read_sql_query(sql, conn, params=(package_id,))


def list_packages(db_path: str) -> list[str]:
    """Return distinct package IDs stored in the DB."""
    sql = "SELECT DISTINCT package_id FROM reviews ORDER BY package_id"
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(sql).fetchall()
    return [r[0] for r in rows]


def save_app_name(package_id: str, app_name: str, db_path: str) -> None:
    """Upsert app display name for a package ID."""
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO apps (package_id, app_name) VALUES (?, ?)",
            (package_id, app_name),
        )


def list_packages_with_names(db_path: str) -> list[tuple[str, str]]:
    """Return (package_id, app_name) for all crawled apps, falling back to package_id."""
    sql = """
        SELECT r.package_id, COALESCE(a.app_name, r.package_id)
        FROM (SELECT DISTINCT package_id FROM reviews) r
        LEFT JOIN apps a ON a.package_id = r.package_id
        ORDER BY r.package_id
    """
    with sqlite3.connect(db_path) as conn:
        return conn.execute(sql).fetchall()


def count_reviews(package_id: str, db_path: str) -> int:
    """Return total stored review count for a package."""
    sql = "SELECT COUNT(*) FROM reviews WHERE package_id = ?"
    with sqlite3.connect(db_path) as conn:
        return conn.execute(sql, (package_id,)).fetchone()[0]
