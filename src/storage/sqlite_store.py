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
        conn.executescript(SCHEMA)
        _migrate(conn)


def save_reviews(reviews: list[dict], package_id: str, db_path: str) -> int:
    """
    Upsert reviews into DB, keyed by review_id.

    Existing rows get refreshed mutable fields (content, score, thumbs_up,
    dev reply, crawled_at). `lang`/`country` keep their first-seen values:
    cross-language dedup means the same review can arrive again under a
    different query language, which must not clobber its origin market.
    Returns number of newly inserted rows.
    """
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
    with sqlite3.connect(db_path) as conn:
        before = conn.execute(count_sql, (package_id,)).fetchone()[0]
        conn.executemany(sql, rows)
        after = conn.execute(count_sql, (package_id,)).fetchone()[0]
        return after - before


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
