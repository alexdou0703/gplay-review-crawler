"""Read-only comparison snapshots; aggregate before crossing into the UI."""

import sqlite3

import pandas as pd


def comparison_snapshot(packages: list[str], db_path: str):
    """Return daily rated-review totals and coverage from the same DB snapshot.

    Review identity is the existing reviews primary key. The query never loads
    comment bodies. Dates are normalized to UTC by SQLite's date function.
    """
    packages = list(dict.fromkeys(packages))
    if not 2 <= len(packages) <= 5:
        raise ValueError("Choose between 2 and 5 apps.")
    placeholders = ",".join("?" for _ in packages)
    # SQLite accepts Julian day numbers and normalizes impossible dates. Require
    # a real ISO calendar day and leave headroom for Pandas calendar bucket ends.
    valid = """date(review_created_at) BETWEEN '1678-01-01' AND '2261-12-31'
        AND date(substr(review_created_at, 1, 10), '+0 days') = substr(review_created_at, 1, 10)
        AND score IN (1, 2, 3, 4, 5)"""
    with sqlite3.connect(db_path) as conn:
        conn.execute("BEGIN")
        daily = pd.read_sql_query(f"""
            SELECT package_id, date(review_created_at) AS day,
                   COUNT(*) AS n, SUM(score) AS score_sum,
                   SUM(score <= 2) AS low, SUM(score = 5) AS five,
                   SUM(LENGTH(TRIM(COALESCE(reply_content, ''), char(9) || char(10) || char(13) || ' ')) > 0) AS replied,
                   SUM(score = 1) AS stars_1, SUM(score = 2) AS stars_2,
                   SUM(score = 3) AS stars_3, SUM(score = 4) AS stars_4,
                   SUM(score = 5) AS stars_5
            FROM reviews WHERE package_id IN ({placeholders}) AND {valid}
            GROUP BY package_id, day ORDER BY package_id, day
        """, conn, params=packages)
        coverage = pd.read_sql_query(f"""
            SELECT package_id, COUNT(*) AS saved,
                   SUM(CASE WHEN {valid} THEN 1 ELSE 0 END) AS usable,
                   MIN(CASE WHEN {valid} THEN date(review_created_at) END) AS first_day,
                   MAX(CASE WHEN {valid} THEN date(review_created_at) END) AS last_day,
                   MAX(datetime(crawled_at)) AS last_saved,
                   GROUP_CONCAT(DISTINCT NULLIF(TRIM(lang), '')) AS crawl_languages,
                   GROUP_CONCAT(DISTINCT NULLIF(TRIM(country), '')) AS crawl_stores
            FROM reviews WHERE package_id IN ({placeholders}) GROUP BY package_id
        """, conn, params=packages)
    return daily, coverage
