"""Parse user input (URL, package ID, or app name) into a Google Play package ID."""

from urllib.parse import urlparse, parse_qs
from google_play_scraper import search


def parse_url(user_input: str) -> tuple[str, str | None]:
    """
    Parse a Google Play URL and return (package_id, country_code).
    country_code is the `gl` param if present, else None.
    """
    parsed = urlparse(user_input.strip())
    params = parse_qs(parsed.query)
    if "id" not in params:
        raise ValueError(f"Could not find package ID in URL: {user_input}")
    package_id = params["id"][0]
    country = params.get("gl", [None])[0]
    return package_id, country


def parse_package_id(user_input: str) -> str:
    """
    Resolve user input to a Google Play package ID only.

    Accepts:
    - Full Google Play URL (e.g. https://play.google.com/store/apps/details?id=com.roblox.client&gl=ch)
    - Plain package ID (e.g. com.roblox.client)
    - App name (e.g. "Roblox") — resolved via search
    """
    user_input = user_input.strip()

    # URL: extract `id` query param (ignore gl — use parse_url for full info)
    if "play.google.com" in user_input:
        pkg, _ = parse_url(user_input)
        return pkg

    # Plain package ID: contains dots, no spaces (e.g. com.roblox.client)
    if "." in user_input and " " not in user_input:
        return user_input

    # App name: search Google Play
    # Note: library bug — featured apps may return appId=None in search results.
    # Workaround: prefer exact title match among valid results; warn if best match is ambiguous.
    results = search(user_input, n_hits=10, lang="en", country="us")

    # Detect case where exact match exists but has appId=None (library parsing bug)
    query_lower = user_input.lower()
    for r in results:
        if r.get("title", "").lower() == query_lower and not r.get("appId"):
            raise ValueError(
                f"Found '{r['title']}' but could not extract package ID (library limitation). "
                f"Please use the Google Play URL or package ID directly."
            )

    valid = [r for r in results if r.get("appId")]
    if not valid:
        raise ValueError(
            f"No app found for: '{user_input}'. "
            "Try the Google Play URL or package ID (e.g. com.roblox.client)."
        )

    # Prefer exact title match first, then substring match, then first result
    exact = [r for r in valid if r.get("title", "").lower() == query_lower]
    if exact:
        return exact[0]["appId"]

    partial = [r for r in valid if query_lower in r.get("title", "").lower()]
    if partial:
        return partial[0]["appId"]

    return valid[0]["appId"]
