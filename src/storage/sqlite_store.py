"""SQLite storage layer for Google Play reviews."""

import os
import sqlite3
import json
import uuid
import pandas as pd
from datetime import datetime, timezone, timedelta


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
CREATE TABLE IF NOT EXISTS crawl_jobs (
    job_id              TEXT PRIMARY KEY,
    package_id          TEXT NOT NULL,
    app_name            TEXT,
    country             TEXT NOT NULL,
    languages_json      TEXT NOT NULL,
    count_per_lang      INTEGER,
    delay               REAL NOT NULL DEFAULT 1.0,
    mode                TEXT NOT NULL DEFAULT 'crawl',
    status              TEXT NOT NULL DEFAULT 'queued',
    pages_completed     INTEGER NOT NULL DEFAULT 0,
    fetched_count       INTEGER NOT NULL DEFAULT 0,
    inserted_count      INTEGER NOT NULL DEFAULT 0,
    languages_completed INTEGER NOT NULL DEFAULT 0,
    total_languages     INTEGER NOT NULL DEFAULT 0,
    last_lang           TEXT,
    last_event          TEXT,
    error_class         TEXT,
    error_msg           TEXT,
    next_retry_at       TEXT,
    retry_count         INTEGER NOT NULL DEFAULT 0,
    cancel_requested    INTEGER NOT NULL DEFAULT 0,
    worker_id           TEXT,
    heartbeat_at        TEXT,
    lease_expires_at    TEXT,
    created_at          TEXT NOT NULL,
    started_at          TEXT,
    finished_at         TEXT,
    updated_at          TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_crawl_jobs_status_updated
    ON crawl_jobs(status, updated_at);
CREATE INDEX IF NOT EXISTS idx_crawl_jobs_lease
    ON crawl_jobs(lease_expires_at);
CREATE UNIQUE INDEX IF NOT EXISTS idx_crawl_jobs_active_target
    ON crawl_jobs(package_id, country)
    WHERE status IN ('queued', 'running', 'retrying', 'waiting');
CREATE TABLE IF NOT EXISTS crawl_job_languages (
    job_id TEXT NOT NULL,
    lang TEXT NOT NULL,
    status TEXT NOT NULL,
    PRIMARY KEY (job_id, lang)
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
        # WAL lets the Streamlit viewer read while a CLI crawl writes; the
        # busy timeout makes a second writer wait instead of failing instantly.
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
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


def save_reviews_and_state(
    reviews: list[dict], package_id: str, state, db_path: str,
    *, job_id: str | None = None, worker_id: str | None = None,
    save_checkpoint: bool = True,
) -> int:
    """Persist a page of reviews and its crawl checkpoint in ONE transaction.

    The crawl cursor advances past a page as soon as it is fetched; committing
    rows and cursor together guarantees a resume never skips a page whose rows
    failed to save. Returns number of newly inserted review rows.
    """
    with sqlite3.connect(db_path) as conn:
        if job_id:
            conn.execute("BEGIN IMMEDIATE")
            _require_job_owner(conn, job_id, worker_id)
        inserted = _upsert_reviews(conn, reviews, package_id)
        if save_checkpoint:
            _upsert_crawl_state(conn, state)
        if job_id:
            where = "job_id=?" + (" AND worker_id=?" if worker_id else "")
            args = [1, len(reviews), inserted, state.lang, "writing", _now(), job_id]
            if worker_id:
                args.append(worker_id)
            conn.execute(
                f"""UPDATE crawl_jobs SET pages_completed=pages_completed+?,
                    fetched_count=fetched_count+?, inserted_count=inserted_count+?,
                    last_lang=?, last_event=?, updated_at=? WHERE {where}""", args
            )
        return inserted


def save_crawl_state(state, db_path: str) -> None:
    """Upsert a crawl checkpoint on its own (e.g. terminal status with no page)."""
    with sqlite3.connect(db_path) as conn:
        _upsert_crawl_state(conn, state)


def _require_job_owner(conn, job_id, worker_id):
    row = conn.execute(
        "SELECT worker_id, status FROM crawl_jobs WHERE job_id=?", (job_id,),
    ).fetchone()
    if not row or row[1] not in {"running", "waiting"} or (worker_id and row[0] != worker_id):
        raise InterruptedError("job lease no longer owned by this worker")


def completed_job_languages(job_id: str, db_path: str) -> set[str]:
    with sqlite3.connect(db_path) as conn:
        return {row[0] for row in conn.execute(
            "SELECT lang FROM crawl_job_languages WHERE job_id=? AND status='complete'",
            (job_id,),
        )}


def finish_job_language(job_id, state, db_path, worker_id, *, save_checkpoint=True):
    """Checkpoint language completion and its progress exactly once per job."""
    with sqlite3.connect(db_path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        _require_job_owner(conn, job_id, worker_id)
        if save_checkpoint:
            _upsert_crawl_state(conn, state)
        conn.execute(
            "INSERT OR REPLACE INTO crawl_job_languages (job_id, lang, status) VALUES (?, ?, ?)",
            (job_id, state.lang, state.status),
        )
        conn.execute(
            """UPDATE crawl_jobs SET languages_completed=(
                SELECT COUNT(*) FROM crawl_job_languages WHERE job_id=? AND status='complete'
            ), last_lang=?, last_event=?, status='running', updated_at=? WHERE job_id=?""",
            (job_id, state.lang, state.status, _now(), job_id),
        )


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


def count_known_review_ids(review_ids: list[str], package_id: str, db_path: str) -> int:
    """Return how many of the given review IDs already exist for this package.

    Package-scoped so the invariant is local rather than relying on Google's
    review IDs being globally unique. Chunked to stay under SQLite's
    bound-variable limit.
    """
    total = 0
    with sqlite3.connect(db_path) as conn:
        for i in range(0, len(review_ids), 500):
            chunk = review_ids[i:i + 500]
            placeholders = ",".join("?" * len(chunk))
            total += conn.execute(
                f"SELECT COUNT(*) FROM reviews WHERE package_id = ? AND review_id IN ({placeholders})",
                [package_id, *chunk],
            ).fetchone()[0]
    return total


def get_stored_country(package_id: str, db_path: str) -> str | None:
    """Return the dominant store country of a package's stored reviews."""
    sql = """
        SELECT country FROM reviews
        WHERE package_id = ? AND country IS NOT NULL
        GROUP BY country ORDER BY COUNT(*) DESC LIMIT 1
    """
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(sql, (package_id,)).fetchone()
    return row[0] if row else None


def delete_package(package_id: str, db_path: str) -> int:
    """Remove a package entirely — reviews, crawl checkpoints, and app name —
    in one transaction. Returns the number of review rows deleted."""
    with sqlite3.connect(db_path) as conn:
        cur = conn.execute("DELETE FROM reviews WHERE package_id = ?", (package_id,))
        conn.execute("DELETE FROM crawl_state WHERE package_id = ?", (package_id,))
        conn.execute("DELETE FROM apps WHERE package_id = ?", (package_id,))
        return cur.rowcount


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
        conn.execute("UPDATE crawl_jobs SET app_name=? WHERE package_id=?", (app_name, package_id))


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


def app_library_summary(db_path: str) -> pd.DataFrame:
    """One aggregate query for the app table, including apps awaiting reviews."""
    sql = """
        WITH packages AS (
            SELECT package_id FROM apps UNION SELECT package_id FROM reviews
        ), totals AS (
            SELECT package_id, COUNT(*) AS reviews, AVG(score) AS average_rating,
                   COUNT(DISTINCT NULLIF(TRIM(lang), '')) AS languages,
                   MAX(crawled_at) AS last_saved
            FROM reviews GROUP BY package_id
        )
        SELECT p.package_id, COALESCE(a.app_name, p.package_id) AS app_name,
               COALESCE(t.reviews, 0) AS reviews, t.average_rating,
               COALESCE(t.languages, 0) AS languages, t.last_saved
        FROM packages p LEFT JOIN apps a USING(package_id)
        LEFT JOIN totals t USING(package_id)
        ORDER BY app_name COLLATE NOCASE, p.package_id
    """
    with sqlite3.connect(db_path) as conn:
        return pd.read_sql_query(sql, conn)


# --- Durable crawl queue ---------------------------------------------------

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _job_from_row(row: sqlite3.Row) -> dict:
    result = dict(row)
    result["languages"] = json.loads(result.pop("languages_json") or "[]")
    result["cancel_requested"] = bool(result["cancel_requested"])
    return result


def enqueue_job(
    package_id: str,
    db_path: str,
    *,
    app_name: str | None = None,
    langs: list[str] | None = None,
    country: str = "us",
    count_per_lang: int | None = 1000,
    delay: float = 1.0,
    mode: str = "crawl",
) -> str:
    """Create an idempotent job; one active target may exist at a time."""
    job_id = str(uuid.uuid4())
    now = _now()
    if not langs:
        from crawler.gplay_crawler import ALL_LANGUAGES
        languages = list_stored_langs(package_id, db_path) if mode == "sync" else []
        languages = languages or ALL_LANGUAGES
    else:
        languages = list(dict.fromkeys(langs))
    try:
        with sqlite3.connect(db_path) as conn:
            conn.execute(
                """INSERT INTO crawl_jobs
                (job_id, package_id, app_name, country, languages_json,
                 count_per_lang, delay, mode, status, total_languages,
                 created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'queued', ?, ?, ?)""",
                (job_id, package_id, app_name, country, json.dumps(languages),
                 count_per_lang, delay, mode, len(languages), now, now),
            )
    except sqlite3.IntegrityError:
        with sqlite3.connect(db_path) as conn:
            row = conn.execute(
                "SELECT job_id FROM crawl_jobs WHERE package_id=? AND country=? "
                "AND status IN ('queued','running','retrying','waiting')",
                (package_id, country),
            ).fetchone()
        if row:
            return row[0]
        raise
    return job_id


def get_job(job_id: str, db_path: str) -> dict | None:
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM crawl_jobs WHERE job_id=?", (job_id,)).fetchone()
    return _job_from_row(row) if row else None


def list_jobs(db_path: str, *, limit: int = 100) -> list[dict]:
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM crawl_jobs ORDER BY updated_at DESC LIMIT ?", (limit,)
        ).fetchall()
    return [_job_from_row(row) for row in rows]


def queue_snapshot(db_path: str, *, history_limit: int = 20) -> dict:
    """Read all active jobs and bounded history from the same SQLite snapshot."""
    active_statuses = "('queued','running','retrying','waiting')"
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("BEGIN")
        active = conn.execute(
            f"SELECT * FROM crawl_jobs WHERE status IN {active_statuses} ORDER BY created_at, job_id"
        ).fetchall()
        history = conn.execute(
            f"""SELECT * FROM crawl_jobs WHERE status NOT IN {active_statuses}
                ORDER BY COALESCE(finished_at, updated_at) DESC, job_id LIMIT ?""",
            (max(0, history_limit),),
        ).fetchall()
        history_count = conn.execute(
            f"SELECT COUNT(*) FROM crawl_jobs WHERE status NOT IN {active_statuses}"
        ).fetchone()[0]
        review_counts = dict(conn.execute(
            f"""SELECT package_id, COUNT(*) FROM reviews WHERE package_id IN (
                SELECT package_id FROM crawl_jobs WHERE status IN {active_statuses}
                UNION SELECT package_id FROM (
                    SELECT package_id FROM crawl_jobs WHERE status NOT IN {active_statuses}
                    ORDER BY COALESCE(finished_at, updated_at) DESC, job_id LIMIT ?
                )
            ) GROUP BY package_id""", (max(0, history_limit),),
        ).fetchall())
    return {"active": [_job_from_row(row) for row in active],
            "history": [_job_from_row(row) for row in history], "history_count": history_count,
            "review_counts": review_counts}


def latest_package_job(package_id: str, db_path: str) -> dict | None:
    """Prefer current work, including retries of an older attempt, for Insights."""
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            """SELECT * FROM crawl_jobs WHERE package_id=?
               ORDER BY CASE WHEN status IN ('queued','running','retrying','waiting') THEN 0 ELSE 1 END,
                        COALESCE(finished_at, updated_at) DESC, created_at DESC, job_id DESC LIMIT 1""",
            (package_id,),
        ).fetchone()
    return _job_from_row(row) if row else None


def claim_job(db_path: str, worker_id: str, lease_seconds: int = 90) -> dict | None:
    """Atomically claim the oldest queued or lease-expired job."""
    now = datetime.now(timezone.utc)
    now_text = now.isoformat()
    lease_text = (now + timedelta(seconds=lease_seconds)).isoformat()
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("BEGIN IMMEDIATE")
        expired = conn.execute(
            """SELECT * FROM crawl_jobs WHERE lease_expires_at < ? AND (
                status IN ('running','waiting') OR
                (status IN ('complete','throttled','error') AND finished_at IS NULL)
            )""", (now_text,),
        ).fetchall()
        for prior in expired:
            # Older workers published a language's terminal state on the job
            # itself. finished_at=NULL distinguishes that bug from a finished job.
            conflict = conn.execute(
                """SELECT 1 FROM crawl_jobs WHERE package_id=? AND country=? AND job_id!=?
                   AND status IN ('queued','running','retrying','waiting')""",
                (prior["package_id"], prior["country"], prior["job_id"]),
            ).fetchone()
            if conflict:
                continue
            has_ledger = conn.execute(
                "SELECT 1 FROM crawl_job_languages WHERE job_id=?", (prior["job_id"],),
            ).fetchone()
            if not has_ledger and prior["mode"] == "crawl":
                # Adopt only checkpoints written during this legacy job, never
                # completion records belonging to an earlier or later crawl.
                langs = json.loads(prior["languages_json"] or "[]")
                for checkpoint in conn.execute(
                    """SELECT lang FROM crawl_state WHERE package_id=? AND country=?
                       AND status='complete' AND updated_at>=? AND updated_at<=?""",
                    (prior["package_id"], prior["country"], prior["started_at"] or prior["created_at"], prior["updated_at"]),
                ).fetchall():
                    if not langs or checkpoint["lang"] in langs:
                        conn.execute(
                            "INSERT INTO crawl_job_languages VALUES (?, ?, 'complete')",
                            (prior["job_id"], checkpoint["lang"]),
                        )
            conn.execute(
                """UPDATE crawl_jobs SET status='queued', worker_id=NULL,
                   lease_expires_at=NULL, heartbeat_at=NULL, updated_at=? WHERE job_id=?""",
                (now_text, prior["job_id"]),
            )
        row = conn.execute(
            """SELECT job_id FROM crawl_jobs
               WHERE status IN ('queued','retrying')
                 AND (next_retry_at IS NULL OR next_retry_at <= ?)
               ORDER BY created_at LIMIT 1""", (now_text,)
        ).fetchone()
        if not row:
            return None
        conn.execute(
            """UPDATE crawl_jobs SET status='running', worker_id=?,
               heartbeat_at=?, lease_expires_at=?, started_at=COALESCE(started_at,?),
               updated_at=?, last_event='running', finished_at=NULL, next_retry_at=NULL,
               languages_completed=(SELECT COUNT(*) FROM crawl_job_languages
                   WHERE job_id=crawl_jobs.job_id AND status='complete')
               WHERE job_id=?""",
            (worker_id, now_text, lease_text, now_text, now_text, row[0]),
        )
        claimed = conn.execute("SELECT * FROM crawl_jobs WHERE job_id=?", (row[0],)).fetchone()
    return _job_from_row(claimed)


def heartbeat_job(job_id: str, db_path: str, worker_id: str, lease_seconds: int = 90) -> bool:
    now = datetime.now(timezone.utc)
    with sqlite3.connect(db_path) as conn:
        cur = conn.execute(
            """UPDATE crawl_jobs SET heartbeat_at=?, lease_expires_at=?, updated_at=?
               WHERE job_id=? AND worker_id=? AND status IN ('running','waiting')""",
            (now.isoformat(), (now + timedelta(seconds=lease_seconds)).isoformat(),
             now.isoformat(), job_id, worker_id),
        )
    return cur.rowcount == 1


def update_job_progress(
    job_id: str, db_path: str, *, worker_id: str | None = None,
    lang: str | None = None, pages: int = 0, fetched: int = 0,
    inserted: int = 0, languages_completed: int = 0, event: str = "writing",
    status: str = "running", error_class: str | None = None,
    error_msg: str | None = None, next_retry_at: str | None = None,
) -> None:
    now = _now()
    where = "job_id=?" + (" AND worker_id=? AND status IN ('running','waiting')" if worker_id else "")
    args = [pages, fetched, inserted, languages_completed, lang, event, status,
            error_class, error_msg, next_retry_at, now, job_id]
    if worker_id:
        args.append(worker_id)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            f"""UPDATE crawl_jobs SET pages_completed=pages_completed+?,
                fetched_count=fetched_count+?, inserted_count=inserted_count+?,
                languages_completed=languages_completed+?, last_lang=COALESCE(?,last_lang),
                last_event=?, status=?, error_class=?, error_msg=?, next_retry_at=?,
                updated_at=? WHERE {where}""", args
        )


def set_job_status(job_id: str, db_path: str, status: str, *, error_class=None,
                   error_msg=None, event=None, next_retry_at=None, worker_id=None) -> None:
    now = _now()
    finished = now if status in {"complete", "failed", "cancelled", "partial", "throttled"} else None
    if status == "throttled" and next_retry_at is None:
        next_retry_at = (datetime.now(timezone.utc) + timedelta(seconds=300)).isoformat()
    with sqlite3.connect(db_path) as conn:
        where = "job_id=?" + (" AND worker_id=? AND status IN ('running','waiting')" if worker_id else "")
        args = [status, error_class, error_msg, event, next_retry_at, finished, now, job_id]
        if worker_id:
            args.append(worker_id)
        conn.execute(
            f"""UPDATE crawl_jobs SET status=?, error_class=?, error_msg=?,
               last_event=COALESCE(?, last_event), next_retry_at=?,
               finished_at=COALESCE(?, finished_at), updated_at=? WHERE {where}""", args,
        )


def request_job_cancel(job_id: str, db_path: str) -> bool:
    with sqlite3.connect(db_path) as conn:
        cur = conn.execute(
            """UPDATE crawl_jobs SET cancel_requested=1,
               status=CASE WHEN status IN ('queued','retrying') THEN 'cancelled' ELSE status END,
               last_event=CASE WHEN status IN ('queued','retrying') THEN 'cancelled' ELSE 'cancelling' END,
               finished_at=CASE WHEN status IN ('queued','retrying') THEN ? ELSE finished_at END,
               updated_at=? WHERE job_id=? AND status IN ('queued','running','retrying','waiting')""",
            (_now(), _now(), job_id),
        )
    return cur.rowcount == 1


def retry_job(job_id: str, db_path: str) -> bool:
    with sqlite3.connect(db_path) as conn:
        cur = conn.execute(
            """UPDATE crawl_jobs SET status='queued', cancel_requested=0,
               error_class=NULL, error_msg=NULL, next_retry_at=NULL,
               worker_id=NULL, lease_expires_at=NULL, heartbeat_at=NULL, finished_at=NULL,
               retry_count=retry_count+1, updated_at=?, last_event='queued'
               WHERE job_id=? AND status IN ('failed','cancelled','partial','throttled')
               AND NOT EXISTS (SELECT 1 FROM crawl_jobs active
                   WHERE active.package_id=crawl_jobs.package_id AND active.country=crawl_jobs.country
                   AND active.status IN ('queued','running','retrying','waiting'))""",
            (_now(), job_id),
        )
    return cur.rowcount == 1


def is_job_cancel_requested(job_id: str, db_path: str) -> bool:
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT cancel_requested FROM crawl_jobs WHERE job_id=?", (job_id,)
        ).fetchone()
    return bool(row and row[0])
