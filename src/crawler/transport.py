"""Typed error classification around the pinned google-play-scraper seam."""

from dataclasses import dataclass
from enum import Enum
import json
import ssl
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from google_play_scraper.constants.element import ElementSpecs
from google_play_scraper.constants.request import Formats
from google_play_scraper.constants.regex import Regex
from google_play_scraper.features.app import parse_dom
from google_play_scraper import Sort

REQUEST_TIMEOUT = 20.0


def fetch_text(url: str, data=None, headers=None) -> str:
    """One HTTP attempt, with a socket timeout and no hidden library retries."""
    request = Request(url, data=data.encode() if isinstance(data, str) else data,
                      headers=headers or {})
    # The pinned dependency changes urllib's default TLS context globally.
    with urlopen(request, timeout=REQUEST_TIMEOUT, context=ssl.create_default_context()) as response:
        body = response.read().decode("utf-8")
    if "com.google.play.gateway.proto.PlayGatewayError" in body:
        raise TransportError(Outcome.THROTTLED, "Google Play gateway rate limit", True)
    return body


def fetch_app_details(package_id: str, lang: str = "en", country: str = "us") -> dict:
    url = Formats.Detail.build(app_id=package_id, lang=lang, country=country)
    try:
        body = fetch_text(url)
    except HTTPError as exc:
        if exc.code != 404:
            raise
        url = Formats.Detail.fallback_build(app_id=package_id, lang=lang)
        try:
            body = fetch_text(url)
        except HTTPError as fallback_error:
            if fallback_error.code == 404:
                raise ValueError(f"App not found on Google Play: {package_id}") from fallback_error
            raise
    return parse_dom(body, package_id, url)


def _fetch_review_items(url, package_id, sort, count, score, device, cursor):
    """Pinned 1.2.7 response format, using our bounded single-attempt HTTP path."""
    body = fetch_text(url, Formats.Reviews.build_body(
        package_id, sort, count, "null", "null", cursor,
    ), {"content-type": "application/x-www-form-urlencoded"})
    match = json.loads(Regex.REVIEWS.findall(body)[0])
    result = json.loads(match[0][2])
    try:
        token = result[-2][-1]
    except (IndexError, TypeError):
        token = None
    return (result[0] if result and result[0] else []), token


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
    if isinstance(exc, TransportError):
        return exc.outcome
    if isinstance(exc, HTTPError):
        if exc.code in {429, 403}:
            return Outcome.THROTTLED
        if exc.code == 404:
            return Outcome.NOT_FOUND
        return Outcome.NETWORK if exc.code >= 500 else Outcome.TERMINAL
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
    if cancel_event is not None and cancel_event.is_set():
        raise InterruptedError("request cancelled")
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
    except InterruptedError:
        raise
    except Exception as exc:
        outcome = classify_exception(exc)
        if limiter and outcome == Outcome.THROTTLED:
            limiter.record_throttle()
        raise TransportError(outcome, str(exc), outcome in {Outcome.THROTTLED, Outcome.NETWORK}) from exc
    if limiter:
        limiter.record_success()
    return parsed, token, waited
