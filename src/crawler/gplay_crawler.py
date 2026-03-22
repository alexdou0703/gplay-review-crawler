"""Crawl reviews from Google Play Store using google-play-scraper with pagination."""

import time
from google_play_scraper import reviews, Sort, app as gplay_app

# Common language codes to use when crawling "all languages"
ALL_LANGUAGES = ["en", "vi", "zh", "ja", "ko", "fr", "de", "es", "pt", "ru", "ar", "th", "id"]


def fetch_app_name(package_id: str, lang: str = "en", country: str = "us") -> str:
    """Fetch the display title of an app from Google Play. Returns package_id on failure."""
    try:
        info = gplay_app(package_id, lang=lang, country=country)
        return info.get("title", package_id)
    except Exception:
        return package_id


def crawl_reviews(
    package_id: str,
    count: int = 500,
    lang: str = "en",
    country: str = "us",
    delay: float = 1.0,
) -> list[dict]:
    """
    Crawl up to `count` reviews for a given package ID in a single language.

    Paginates automatically using continuation_token (max 200 per request).
    Adds `delay` seconds between pages to avoid rate limiting.

    Returns list of raw review dicts from google-play-scraper.
    """
    all_reviews = []
    token = None

    while len(all_reviews) < count:
        batch_size = min(200, count - len(all_reviews))

        result, token = reviews(
            package_id,
            lang=lang,
            country=country,
            sort=Sort.NEWEST,
            count=batch_size,
            continuation_token=token,
        )

        if not result:
            break  # no more reviews available

        all_reviews.extend(result)

        if not token:
            break  # reached end of available reviews

        time.sleep(delay)

    return all_reviews


def crawl_reviews_all_languages(
    package_id: str,
    count_per_lang: int = 200,
    country: str = "us",
    delay: float = 1.0,
    progress_callback=None,
) -> list[dict]:
    """
    Crawl reviews across all major languages, deduplicated by review_id.

    Crawls ALL_LANGUAGES sequentially, merges results.
    progress_callback(lang, fetched, total_so_far) called after each language.

    Returns deduplicated list of review dicts with added 'lang' field.
    """
    seen_ids = set()
    merged = []

    for i, lang in enumerate(ALL_LANGUAGES):
        try:
            batch = crawl_reviews(
                package_id,
                count=count_per_lang,
                lang=lang,
                country=country,
                delay=delay,
            )
            new_reviews = []
            for r in batch:
                rid = r.get("reviewId", "")
                if rid and rid not in seen_ids:
                    seen_ids.add(rid)
                    r["lang"] = lang  # tag which language this came from
                    new_reviews.append(r)

            merged.extend(new_reviews)

            if progress_callback:
                progress_callback(lang, len(new_reviews), len(merged))

        except Exception:
            # Skip failed language, continue with next
            if progress_callback:
                progress_callback(lang, 0, len(merged))

        # Small delay between languages
        if i < len(ALL_LANGUAGES) - 1:
            time.sleep(delay)

    return merged
