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
    crawled_at         TEXT
);
CREATE INDEX IF NOT EXISTS idx_reviews_package_id ON reviews(package_id);
"""


def init_db(db_path: str) -> None:
    """Create reviews table and index if they don't exist."""
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        conn.executescript(SCHEMA)


def save_reviews(reviews: list[dict], package_id: str, db_path: str) -> int:
    """
    Insert reviews into DB. Skips duplicates (INSERT OR IGNORE by review_id).
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
        )
        for r in reviews
        if r.get("reviewId")  # skip rows without an ID
    ]

    sql = """
        INSERT OR IGNORE INTO reviews
            (review_id, package_id, username, user_image, content, score,
             thumbs_up, review_created_at, reply_content, reply_at, crawled_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """
    with sqlite3.connect(db_path) as conn:
        cursor = conn.executemany(sql, rows)
        return cursor.rowcount


def get_reviews(package_id: str, db_path: str) -> pd.DataFrame:
    """Return all stored reviews for a package as a DataFrame."""
    sql = """
        SELECT review_id, username, score, content, thumbs_up,
               review_created_at, reply_content, crawled_at
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


def count_reviews(package_id: str, db_path: str) -> int:
    """Return total stored review count for a package."""
    sql = "SELECT COUNT(*) FROM reviews WHERE package_id = ?"
    with sqlite3.connect(db_path) as conn:
        return conn.execute(sql, (package_id,)).fetchone()[0]
