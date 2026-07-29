"""Drivers that tie the crawler to SQLite storage, shared by the UI and the CLI."""

import logging

from crawler.gplay_crawler import (
    CrawlState, crawl_reviews_iter, sync_reviews_iter, resume_or_fresh,
)
from storage.sqlite_store import (
    save_reviews, save_reviews_and_state, save_crawl_state, load_crawl_state,
    count_known_review_ids, list_stored_langs,
)

logger = logging.getLogger(__name__)


def sync_package(
    package_id: str,
    db_path: str,
    langs: list[str] | None = None,
    country: str = "us",
    delay: float = 1.0,
    progress_callback=None,
) -> dict[str, tuple[int, CrawlState]]:
    """Incrementally sync a package: fetch newest reviews per language until
    the stored dataset is caught up.

    Defaults to the languages already present in the DB. Deliberately does NOT
    touch crawl_state — a throttled deep-history checkpoint stays intact for
    the next full crawl to resume, and sync interruptions are cheap to redo.

    Returns {lang: (new_review_count, CrawlState)}.
    """
    langs = langs or list_stored_langs(package_id, db_path)
    results: dict[str, tuple[int, CrawlState]] = {}

    for lang in langs:
        state = CrawlState(package_id, lang, country)
        new_count = 0
        for page in sync_reviews_iter(
            package_id, lang=lang, country=country,
            known_count_fn=lambda ids: count_known_review_ids(ids, db_path),
            delay=delay, state=state,
        ):
            new_count += save_reviews(page, package_id, db_path)
        results[lang] = (new_count, state)
        if progress_callback:
            progress_callback(lang, new_count, state)

    return results


def crawl_package(
    package_id: str,
    db_path: str,
    langs: list[str],
    country: str = "us",
    count: int | None = None,
    delay: float = 1.0,
    page_callback=None,
) -> dict[str, CrawlState]:
    """Crawl each language with checkpoint persistence, resuming partial work.

    Every page commits with its checkpoint; terminal statuses are recorded
    even when a language yields no pages. count=None walks full history.
    page_callback(lang, state, inserted) is called after each saved page.

    Returns {lang: CrawlState}.
    """
    summary: dict[str, CrawlState] = {}

    for lang in langs:
        state = resume_or_fresh(
            load_crawl_state(package_id, lang, country, db_path),
            package_id, lang, country,
        )
        if state.cursor:
            logger.info("[%s] resuming from checkpoint (%d fetched so far)", lang, state.fetched)

        for page in crawl_reviews_iter(
            package_id, count=count, lang=lang, country=country, delay=delay, state=state
        ):
            inserted = save_reviews_and_state(page, package_id, state, db_path)
            if page_callback:
                page_callback(lang, state, inserted)

        save_crawl_state(state, db_path)
        summary[lang] = state

    return summary
