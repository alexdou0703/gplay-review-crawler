# Mericrawler

Crawl Google Play reviews into a local SQLite workspace for product analysis. Mericrawler uses Python, Streamlit, and [google-play-scraper](https://pypi.org/project/google-play-scraper/).

## Features

- Input by Google Play URL, package ID, or app name (store country picked up from the URL's `gl` param)
- **Full-history crawls** with per-page checkpoints — interruptions and rate limits resume where they stopped, and partial results are always reported as partial, never as success
- 22-language sweep deduplicated by review ID; each review stores its `lang`, `country`, and the `app_version` it was written on
- **Incremental sync**: fetch only reviews newer than the stored dataset (**Apps → Sync reviews**, or `--sync` in the CLI) — re-fetched reviews also update thumbs-up counts and developer replies. Fast when the dataset is reasonably complete; the UI sync is budget-capped (~5000 reviews/language per click) so shallow datasets can't turn a refresh into an hours-long walk — use the CLI for unbounded catch-up
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
MERICRAWLER_EMBED_WORKER=0 streamlit run src/app.py

# In another terminal, run the local queue worker
python src/crawl_worker.py --db data/reviews.db --workers 2 --min-request-interval 1.0
```

Queue one or more apps from the UI, one per line. The browser remains available for
results and queue controls while the worker crawls. SQLite and the worker are a
single-host deployment model; they are not a distributed scheduler.

By default, `streamlit run src/app.py` starts an embedded worker with two app
slots, including on Streamlit-hosted demos. The separate-worker setup above
disables it with `MERICRAWLER_EMBED_WORKER=0` so only the dedicated worker runs.

After upgrading, restart both the UI and any separate worker. Expired running or
waiting jobs are recovered automatically (default lease: 90 seconds). Legacy jobs
incorrectly marked complete between languages are also recovered if they have no
finish timestamp. Retry keeps completed languages for the same job; queue a new
crawl or sync when you want to refresh those languages.

## Follow crawls and open results

1. In **Crawl**, add one app per line and select the language and review limit.
   Each crawl request appears as a row in the queue table. All active jobs
   remain available alongside the latest 20 past attempts.
2. When app slots are occupied, each pending row shows **Queued**, its queue
   position and next step. The shared notice names apps currently processing. It starts
   automatically when a slot opens; there is no need to submit it again.
3. In **Apps**, choose **App to manage → Open insights** to switch to **Insights**. Use **Refresh results** to load newly saved reviews. Search and
   star filters survive switching between Crawl and Insights; CSV/JSON exports
   use the filtered results.

The queue table is read-only, with no row selection or details panel.
**New reviews** counts inserts from that attempt; **Saved reviews** includes
earlier crawls of the same app.

Waiting guidance stays above the table and in its **Next step** column. It changes when
an app starts or is cancelled; they do not repeatedly open popups. The queue
refreshes automatically every five seconds.

| Queue notice | Meaning / next action |
|---|---|
| Queued | Check Next step: the app waits for another crawl or for the crawl service. It starts automatically when available. |
| Waiting for the crawl service | No recently responding active worker is visible. The job is saved; check that the worker is running. |
| Worker not responding | A claimed job has stopped reporting recently. Saved reviews are kept; recovery can occur after its lease expires. |
| Retrying request | This app already occupies a slot and is waiting before another network request. The countdown is a retry delay, not a completion estimate. |
| Partial results / Rate limited / Failed | Open **Apps** or **Insights** to view any saved reviews. |

Language progress can remain at the same fraction while pages in that language
are still being saved. Worker
visibility is inferred from active-job heartbeats; it is not a separate worker
health monitor. Pending positions exclude cancelled jobs and retries that are
not yet eligible to start.

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

## App library and analytics workspace

The light workspace has three views: **Crawl**, **Apps**, and **Insights**, with no
Saved apps sidebar.
Apps provides a searchable table of saved review counts, average ratings,
languages, and last-save times. Choose **App to manage**, then **Open insights**,
**Sync reviews**, or **Delete saved app**. Sync queues work in Crawl; deleting an
app requires **Confirm deletion** and removes its saved reviews. **Keep app**
cancels deletion. Changing the selected app clears a pending deletion confirmation.

In Insights, **Single app → Reviews** keeps search, rating filters and CSV/JSON downloads.
**Analytics** renders only when selected. Apply a date range, languages and a
daily/weekly/monthly interval together, then explore:

- **Overview:** dated-review KPIs, review volume and rating over time, rating
  distribution, language counts/shares and developer engagement.
- **Versions:** ratings by first appearance in saved reviews, for known versions
  with at least 30 reviews in the selection.
- **Signals:** unusual review-volume windows and supporting languages/phrases.

Small datasets still display their charts with a sample-size caution. All figures
refer to saved reviews. Stored language and country describe the crawl query,
not verified reviewer language or location; version dates are not verified
release dates. Analytics date bounds include the full final day in UTC.

### Compare apps

Open **Insights → Compare apps**, select **2–5 apps** with saved reviews, choose
an inclusive UTC date range and **Daily**, **Weekly** or **Monthly**, then press
**Compare**. Weekly periods run Monday–Sunday; first and last periods are clipped
to the selected dates. Ranges are limited to 500 periods: use a coarser interval
or shorter range when needed.

- **Compare trends:** switch between average rating, 1–2 star share, saved review
  count and developer reply rate. Hover a period to compare apps and sample counts.
- **Rating distribution:** compare each app's 1–5 star proportions in horizontal
  100% stacked bars.
- **Comparison summary:** sortable counts, average ratings, low/five-star shares
  and reply rates. **Trend data** exposes the period values as a table.
- **Data coverage:** inspect all saved counts, observed review dates, last-save
  time, query languages/stores, excluded rows and latest recorded crawl status.

Metrics share one denominator: saved reviews with a supported, valid calendar
date and a 1–5 star rating. Rating averages are weighted by review count, not by
day. Reply rate counts reviews with a nonblank developer reply. An app with no
eligible reviews in the range stays in the summary with a count of zero and
unavailable rates; empty chart periods remain gaps rather than inferred zero activity.

These are saved samples, not store-wide ratings, downloads or market share.
Observed date ranges do not establish complete coverage, and crawl limits or
query languages may differ between apps. No semantic classification or reviewer
country inference is performed.

Form edits apply when **Compare** is pressed. Applied filters survive switching
between Insights modes; **Refresh data** reloads saved data without crawling.
Opening an app from Apps returns to **Single app**. Comparison
tables are read-only and do not open per-row detail panels.

Use Streamlit 1.47 or newer and restart the server after upgrading or changing
`.streamlit/config.toml` so the new light theme is applied.
