"""Crawl reviews from Google Play Store, paginating one page per request.

Pagination deliberately bypasses google_play_scraper.reviews() and calls the
lower-level _fetch_review_items directly. reviews() in the pinned 1.2.7:
  - swallows fetch exceptions into token=None, making network errors/throttling
    indistinguishable from genuine end-of-data (silent truncation),
  - re-fetches in a zero-delay internal loop, so the caller never sees an
    empty page and cannot back off,
  - ignores the count kwarg on continuation calls, overshooting caps.
Fetching page-by-page surfaces errors and empty pages here, where we can retry
with backoff and report honest partial/complete status. Coupled to
google-play-scraper==1.2.7 (pinned in requirements.txt) — re-verify this seam
on any version bump.
"""

import logging
import time

from google_play_scraper import Sort, app as gplay_app
from google_play_scraper.constants.element import ElementSpecs
from google_play_scraper.constants.request import Formats
from google_play_scraper.exceptions import NotFoundError
from google_play_scraper.features.reviews import _fetch_review_items

logger = logging.getLogger(__name__)

# Common language codes to use when crawling "all languages"
ALL_LANGUAGES = ["en", "vi", "zh", "ja", "ko", "fr", "de", "es", "pt", "ru", "ar", "th", "id"]

# Reviews requested per page. Google serves up to ~200 for NEWEST sort.
PAGE_SIZE = 200

# Wait times between retries when a page fetch fails or comes back empty while
# the pagination cursor still points at more data (throttling, not end-of-data).
BACKOFF_DELAYS = [5, 10, 20, 40, 60]


class CrawlState:
    """Mutable progress record for one (package, lang, country) crawl.

    status values:
      in_progress — crawl running
      complete    — reached end of available reviews (or the requested cap)
      throttled   — page fetches kept failing or returning empty despite a
                    live cursor; data is PARTIAL, resume from `cursor` later
      error       — crawl aborted on an exception (see error_msg)

    `cursor` is Google's pagination cursor (plain string), kept at the last
    unfetched page so a resumed crawl continues where this one stopped.
    """

    def __init__(self, package_id: str, lang: str, country: str):
        self.package_id = package_id
        self.lang = lang
        self.country = country
        self.status = "in_progress"
        self.cursor: str | None = None
        self.fetched = 0
        self.error_msg: str | None = None


def fetch_app_name(package_id: str, lang: str = "en", country: str = "us") -> str:
    """Fetch the display title of an app from Google Play.

    Raises ValueError when the package does not exist, so callers can show
    "app not found" instead of running a pointless crawl.
    """
    try:
        info = gplay_app(package_id, lang=lang, country=country)
    except NotFoundError:
        raise ValueError(f"App not found on Google Play: {package_id}")
    return info.get("title", package_id)


def _fetch_page(
    package_id: str, lang: str, country: str, page_size: int, cursor: str | None
) -> tuple[list[dict], str | None]:
    """Fetch a single page of parsed review dicts. Exceptions propagate.

    Returns (reviews, next_cursor); next_cursor None means no further pages.
    """
    url = Formats.Reviews.build(lang=lang, country=country)
    items, token = _fetch_review_items(
        url, package_id, Sort.NEWEST.value, page_size, None, None, cursor
    )
    # Terminal responses encode the cursor slot as a list instead of a string.
    if isinstance(token, list):
        token = None
    parsed = [
        {k: spec.extract_content(item) for k, spec in ElementSpecs.Review.items()}
        for item in items
    ]
    return parsed, token


def crawl_reviews_iter(
    package_id: str,
    count: int | None = 500,
    lang: str = "en",
    country: str = "us",
    delay: float = 1.0,
    state: CrawlState | None = None,
):
    """
    Yield pages of raw review dicts, newest first, up to `count` total
    (None = no cap, walk the full available history).

    Each review dict is tagged with the `lang`/`country` it was fetched under.
    Callers should persist every yielded page immediately — an interrupted
    crawl then loses at most one page.

    A failed or empty-but-not-final page is retried per BACKOFF_DELAYS; when
    retries are exhausted the crawl stops with status `throttled` (partial,
    resumable via state.cursor) — never falsely `complete`.
    """
    if state is None:
        state = CrawlState(package_id, lang, country)
    state.status = "in_progress"  # a resumed throttled state is live again
    state.error_msg = None  # stale failure detail must not survive a successful resume

    cursor = state.cursor  # None = start from newest; set = resume from checkpoint

    while count is None or state.fetched < count:
        page_size = PAGE_SIZE if count is None else min(PAGE_SIZE, count - state.fetched)

        # items stays None until a page yields data or a clean end-of-history;
        # None after all attempts means throttled/failing — an honest partial stop.
        items = None
        last_error = None
        for attempt, wait in enumerate([0] + BACKOFF_DELAYS):
            if wait:
                logger.warning(
                    "[%s/%s] %s: page fetch failed (%s) — retry %d/%d in %ds",
                    lang, country, package_id,
                    last_error or "empty page with live cursor",
                    attempt, len(BACKOFF_DELAYS), wait,
                )
                time.sleep(wait)
            try:
                items, next_cursor = _fetch_page(package_id, lang, country, page_size, cursor)
            except Exception as e:
                last_error = e
                items = None
                continue
            if items or next_cursor is None:
                break  # got data, or clean end of history
            items = None  # empty page but cursor says more exists → retry
            last_error = None  # this attempt didn't raise; don't report a stale exception

        if items is None:
            state.status = "throttled"
            state.error_msg = str(last_error) if last_error else "empty pages with live cursor"
            return

        if not items:  # empty page with no cursor: clean end of history
            state.status = "complete"
            return

        for r in items:
            r["lang"] = lang
            r["country"] = country
        state.fetched += len(items)
        state.cursor = next_cursor
        cursor = next_cursor

        yield items

        if cursor is None:
            state.status = "complete"
            return

        time.sleep(delay)

    state.status = "complete"


def resume_or_fresh(prior, package_id: str, lang: str, country: str) -> CrawlState:
    """Reuse a stored crawl state when it holds a resumable checkpoint.

    Resumable = interrupted or throttled with a live cursor. Completed or
    errored crawls restart from the newest reviews instead — dedup and upsert
    make a restart cheap, and it picks up reviews posted since.
    """
    if prior is not None and prior.cursor and prior.status in ("in_progress", "throttled"):
        return prior
    return CrawlState(package_id, lang, country)


def crawl_reviews(
    package_id: str,
    count: int = 500,
    lang: str = "en",
    country: str = "us",
    delay: float = 1.0,
    state: CrawlState | None = None,
) -> list[dict]:
    """Crawl up to `count` reviews in a single language, returned as one list."""
    all_reviews: list[dict] = []
    for page in crawl_reviews_iter(
        package_id, count=count, lang=lang, country=country, delay=delay, state=state
    ):
        all_reviews.extend(page)
    return all_reviews


def crawl_reviews_all_languages(
    package_id: str,
    count_per_lang: int = 200,
    country: str = "us",
    delay: float = 1.0,
    progress_callback=None,
    on_batch=None,
    states: dict[str, CrawlState] | None = None,
) -> tuple[list[dict], dict[str, CrawlState]]:
    """
    Crawl reviews across ALL_LANGUAGES sequentially, deduplicated by reviewId.

    on_batch(lang, new_reviews, state) is called with each deduplicated page as
    it arrives — persist both there so progress survives interruption. on_batch
    exceptions propagate: a broken storage sink is fatal, not a per-language
    condition.
    progress_callback(lang, fetched_new, total_so_far) is called once per language.
    states maps lang → CrawlState to start from (e.g. loaded checkpoints via
    resume_or_fresh); languages without an entry start fresh.

    Returns (deduplicated reviews, {lang: CrawlState}) so callers can tell
    complete languages apart from throttled/errored ones.
    """
    seen_ids: set[str] = set()
    merged: list[dict] = []
    summary: dict[str, CrawlState] = {}

    for i, lang in enumerate(ALL_LANGUAGES):
        state = (states or {}).get(lang) or CrawlState(package_id, lang, country)
        summary[lang] = state
        lang_new = 0

        pages = crawl_reviews_iter(
            package_id, count=count_per_lang, lang=lang,
            country=country, delay=delay, state=state,
        )
        while True:
            try:
                page = next(pages)
            except StopIteration:
                break
            except Exception as e:
                # Crawl failure is per-language: record it and move on.
                logger.exception("Crawl failed for %s lang=%s", package_id, lang)
                state.status = "error"
                state.error_msg = str(e)
                break

            new_reviews = []
            for r in page:
                rid = r.get("reviewId", "")
                if rid and rid not in seen_ids:
                    seen_ids.add(rid)
                    new_reviews.append(r)
            # Fully-deduped pages skip on_batch, so their cursor advance is not
            # checkpointed: an interrupt then re-fetches those pages (idempotent
            # upserts), it never skips data.
            if new_reviews:
                merged.extend(new_reviews)
                lang_new += len(new_reviews)
                if on_batch:
                    on_batch(lang, new_reviews, state)

        if progress_callback:
            progress_callback(lang, lang_new, len(merged))

        # Small delay between languages
        if i < len(ALL_LANGUAGES) - 1:
            time.sleep(delay)

    return merged, summary
