# Google Play Review Crawler

Crawl the review history of any Google Play app into SQLite for product analysis. Python + Streamlit + [google-play-scraper](https://pypi.org/project/google-play-scraper/).

## Features

- Input by Google Play URL, package ID, or app name (store country picked up from the URL's `gl` param)
- **Full-history crawls** with per-page checkpoints — interruptions and rate limits resume where they stopped, and partial results are always reported as partial, never as success
- 22-language sweep deduplicated by review ID; each review stores its `lang`, `country`, and the `app_version` it was written on
- **Incremental sync**: refresh an existing dataset in seconds (↻ button in the sidebar, or `--sync` in the CLI) — re-fetched reviews also update thumbs-up counts and developer replies
- Star-rating filter, CSV / JSON export
- Headless CLI for multi-hour crawls; the Streamlit UI reads the same database live

## Run the UI

```bash
pip install -r requirements.txt
streamlit run src/app.py
```

Good for quick looks (up to 1000 reviews per language per run). For complete histories use the CLI.

## Full crawls (CLI)

```bash
# Complete history, all 22 languages — hours for big apps, safe to interrupt
python src/crawl_cli.py "https://play.google.com/store/apps/details?id=com.roblox.client&gl=vn" --full

# Capped crawl of specific languages
python src/crawl_cli.py com.roblox.client --langs en,vi --max 500

# Update an existing dataset with reviews posted since
python src/crawl_cli.py com.roblox.client --sync

# Run unattended
nohup python src/crawl_cli.py com.example.app --full > crawl.log 2>&1 &
```

Interrupted or rate-limited? Re-run the same command — progress is checkpointed per page. Exit codes: `0` complete, `2` partial (re-run later to resume), `130` interrupted.

## Storage

SQLite at `data/reviews.db` (WAL mode, so the UI can read while a crawl writes). On read-only filesystems such as Streamlit Cloud it falls back to `/tmp/reviews.db`, which is **ephemeral and shared by every visitor of that deployment** — treat cloud deploys as demos, run real crawls locally.

## Tests

```bash
pip install -r requirements-dev.txt
pytest
```

No network needed — the Google Play pagination layer is stubbed at a single seam.
