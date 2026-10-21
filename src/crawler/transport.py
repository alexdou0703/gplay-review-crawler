"""Typed error classification around the pinned google-play-scraper seam."""

from dataclasses import dataclass
from enum import Enum

from google_play_scraper.constants.element import ElementSpecs
from google_play_scraper.constants.request import Formats
from google_play_scraper.features.reviews import _fetch_review_items
from google_play_scraper import Sort


class Outcome(str, Enum):
    SUCCESS = "success"
    THROTTLED = "throttled"
    NETWORK = "network"
    NOT_FOUND = "not_found"
    PARSE = "parse"
    TERMINAL = "terminal"


@dataclass
class TransportError(Exception):
    outcome: Outcome
    message: str
    retryable: bool = False

    def __str__(self) -> str:
        return self.message


def classify_exception(exc: Exception) -> Outcome:
    text = str(exc).lower()
    name = type(exc).__name__.lower()
    if any(token in text for token in ("429", "403", "gateway", "rate", "too many")):
        return Outcome.THROTTLED
    if "notfound" in name or "not found" in text:
        return Outcome.NOT_FOUND
    if isinstance(exc, (TimeoutError, ConnectionError, OSError)):
        return Outcome.NETWORK
    return Outcome.PARSE


def fetch_reviews_page(package_id: str, lang: str, country: str,
                       page_size: int, cursor: str | None, *,
                       limiter=None, cancel_event=None) -> tuple[list[dict], str | None, float]:
    """Fetch and parse one page, returning (items, cursor, limiter_wait)."""
    waited = limiter.acquire(cancel_event) if limiter else 0.0
    try:
        url = Formats.Reviews.build(lang=lang, country=country)
        items, token = _fetch_review_items(
            url, package_id, Sort.NEWEST.value, page_size, None, None, cursor
        )
        if isinstance(token, list):
            token = None
        parsed = [
            {k: spec.extract_content(item) for k, spec in ElementSpecs.Review.items()}
            for item in items
        ]
    except Exception as exc:
        outcome = classify_exception(exc)
        if limiter and outcome == Outcome.THROTTLED:
            limiter.record_throttle()
        raise TransportError(outcome, str(exc), outcome in {Outcome.THROTTLED, Outcome.NETWORK}) from exc
    if limiter:
        limiter.record_success()
    return parsed, token, waited
