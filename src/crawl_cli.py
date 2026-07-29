"""Headless Google Play review crawler.

Writes to the same SQLite database as the Streamlit viewer, so long-running
full-history crawls can run under nohup/cron while the UI stays a read-only
analysis surface. Every page commits with a resume checkpoint: Ctrl-C or a
crash costs nothing — re-run the same command to continue.

Examples:
  python src/crawl_cli.py com.roblox.client --langs en --max 500
  python src/crawl_cli.py "https://play.google.com/store/apps/details?id=com.roblox.client&gl=vn" --full
  python src/crawl_cli.py com.roblox.client --sync
"""

import argparse
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from crawler.url_parser import parse_package_id, parse_url
from crawler.gplay_crawler import ALL_LANGUAGES, fetch_app_name
from crawl_service import crawl_package, sync_package
from storage.sqlite_store import init_db, save_app_name, count_reviews

logger = logging.getLogger("crawl_cli")

DEFAULT_DB = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "reviews.db"))
DEFAULT_MAX = 1000


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Crawl Google Play reviews into SQLite (resumable, rate-limit aware).",
    )
    p.add_argument("app", help="Google Play URL, package ID, or app name")
    p.add_argument("--langs", default="all",
                   help="'all' or comma-separated codes, e.g. en,vi,ja "
                        "(default: all for crawls; languages already stored for --sync)")
    p.add_argument("--country", default=None,
                   help="Play Store country (default: gl param from URL, else us)")
    scope = p.add_mutually_exclusive_group()
    scope.add_argument("--max", type=int, default=None,
                       help=f"max reviews per language (default: {DEFAULT_MAX})")
    scope.add_argument("--full", action="store_true",
                       help="no cap — walk the complete review history per language")
    scope.add_argument("--sync", action="store_true",
                       help="incremental update: fetch only reviews newer than the stored dataset")
    p.add_argument("--fresh", action="store_true",
                   help="discard stored checkpoints and restart from newest "
                        "(escape hatch for expired resume cursors)")
    p.add_argument("--db", default=DEFAULT_DB, help="SQLite database path")
    p.add_argument("--delay", type=float, default=1.0, help="seconds between page requests")
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.max is not None and args.max <= 0:
        parser.error("--max must be a positive number of reviews")
    logging.basicConfig(
        level=logging.INFO, stream=sys.stdout,
        format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S",
    )

    detected_country = None
    if "play.google.com" in args.app:
        package_id, detected_country = parse_url(args.app)
    else:
        package_id = parse_package_id(args.app)
    country = args.country or detected_country or "us"

    init_db(args.db)
    app_title = fetch_app_name(package_id, country=country)
    save_app_name(package_id, app_title, args.db)

    langs = ALL_LANGUAGES if args.langs == "all" else [l.strip() for l in args.langs.split(",") if l.strip()]
    logger.info("%s (%s) — db=%s country=%s langs=%s", app_title, package_id, args.db, country, ",".join(langs))

    try:
        if args.sync:
            # Default sync scope = stored languages + stored country; --langs/--country override.
            sync_langs = langs if args.langs != "all" else None
            results = sync_package(
                package_id, args.db, langs=sync_langs,
                country=args.country or detected_country, delay=args.delay,
                progress_callback=lambda lang, new, s: logger.info("[%s] +%d new (%s)", lang, new, s.status),
            )
            states = {lang: s for lang, (_, s) in results.items()}
        else:
            count = None if args.full else (args.max or DEFAULT_MAX)
            if not args.full:
                logger.info("capped at %d reviews/language — use --full for complete history", count)
            states = crawl_package(
                package_id, args.db, langs, country=country, count=count, delay=args.delay,
                fresh=args.fresh,
                page_callback=lambda lang, s, ins: logger.info(
                    "[%s] +%d new (%d fetched, %s)", lang, ins, s.fetched, s.status
                ),
            )
    except KeyboardInterrupt:
        logger.warning("interrupted — progress is checkpointed; re-run the same command to resume")
        return 130

    total = count_reviews(package_id, args.db)
    logger.info("---- summary (%d reviews stored for %s) ----", total, package_id)
    incomplete = 0
    for lang, s in states.items():
        detail = f" — {s.error_msg}" if s.error_msg else ""
        logger.info("  %-6s %-10s %d fetched%s", lang, s.status, s.fetched, detail)
        if s.status not in ("complete",):
            incomplete += 1
    if incomplete:
        logger.warning("%d language(s) incomplete — re-run to resume from checkpoints", incomplete)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
