# Mericrawler

Crawl Google Play reviews into a local SQLite workspace for product analysis. Mericrawler uses Python, Streamlit, and [google-play-scraper](https://pypi.org/project/google-play-scraper/).

## Features

- Input by Google Play URL, package ID, or app name (store country picked up from the URL's `gl` param)
- **Full-history crawls** with per-page checkpoints — interruptions and rate limits resume where they stopped, and partial results are always reported as partial, never as success
- 22-language sweep deduplicated by review ID; each review stores its `lang`, `country`, and the `app_version` it was written on
- **Incremental sync**: fetch only reviews newer than the stored dataset (↻ button in the sidebar, or `--sync` in the CLI) — re-fetched reviews also update thumbs-up counts and developer replies. Fast when the dataset is reasonably complete; the sidebar button is budget-capped (~5000 reviews/language per click) so shallow datasets can't turn a refresh into an hours-long walk — use the CLI for unbounded catch-up
- Star-rating filter, CSV / JSON export
- Headless CLI for multi-hour crawls; the Streamlit UI reads the same database live
- Durable multi-app queue with cancellation, retry, lease recovery, and per-page checkpoints
- A separate worker keeps the Streamlit tab interactive; default worker concurrency is two apps
- Shared request pacing and typed rate-limit/network status reporting
- HTTP requests use a 20-second socket timeout, with three visible retries (2/5/10 seconds) and no nested library retries
- Queue progress shows current language, saved pages, fetched reviews, and retry countdowns; Retry skips languages already completed by that job

## Run the UI and worker

```bash
pip install -r requirements.txt
streamlit run src/app.py

# In another terminal, run the local queue worker
python src/crawl_worker.py --db data/reviews.db --workers 2 --min-request-interval 1.0
```

Queue one or more apps from the UI, one per line. The browser remains available for
results and queue controls while the worker crawls. SQLite and the worker are a
single-host deployment model; they are not a distributed scheduler.

The Streamlit-hosted demo starts an embedded worker with two app slots automatically because the
hosting service runs only the UI process. For local production-style operation,
set `MERICRAWLER_EMBED_WORKER=0` and run the separate worker command above.

After upgrading, restart both the UI and any separate worker. Expired running or
waiting jobs are recovered automatically (default lease: 90 seconds). Legacy jobs
incorrectly marked complete between languages are also recovered if they have no
finish timestamp. Retry keeps completed languages for the same job; queue a new
crawl or sync when you want to refresh those languages.

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

Interrupted or rate-limited? Re-run the same command — progress is checkpointed per page. If a checkpoint has expired on Google's side (crawl keeps ending `throttled` immediately), `--fresh` discards checkpoints and restarts from newest. Exit codes: `0` complete, `2` partial (re-run later to resume), `130` interrupted.

The queue worker exposes `--workers`, `--min-request-interval`, and `--poll-interval`.
Google availability and quota behavior vary, so increase concurrency only after
checking the worker's rate-limit and error metrics. A queued job can be cancelled
from the UI and retried after a partial or throttled result.

## Storage

SQLite at `data/reviews.db` (WAL mode, so the UI can read while a crawl writes). On read-only filesystems such as Streamlit Cloud it falls back to `/tmp/reviews.db`, which is **ephemeral and shared by every visitor of that deployment** — treat cloud deploys as demos, run real crawls locally.

Use `MERICRAWLER_DB_PATH` to override the UI database path; pass that same path as
`--db` if running a separate worker.

Back up a database by copying it while the worker is stopped, or use SQLite's
backup tooling. Migrations are additive and run automatically when the UI, CLI,
or worker starts. The old `crawl_state` checkpoints and direct CLI path remain
supported while the queue path is adopted.

## Tests

```bash
pip install -r requirements-dev.txt
pytest
```

No network needed — the Google Play pagination layer is stubbed at a single seam.
