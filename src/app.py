"""Google Play Review Crawler — Streamlit UI."""

import sys
import os
import threading
from html import escape as html_escape

# Ensure src/ is in path for local imports
sys.path.insert(0, os.path.dirname(__file__))

import streamlit as st
import pandas as pd

from crawler.url_parser import parse_package_id, parse_url
from crawler.gplay_crawler import ALL_LANGUAGES, fetch_app_name
from storage.sqlite_store import (
    init_db, get_reviews, count_reviews, save_app_name, list_packages_with_names,
    delete_package, enqueue_job, list_jobs, request_job_cancel, retry_job,
)
from crawl_jobs import display_status
from crawl_worker import run_worker
from analysis_ui import render_analysis_tab
from ui_styles import MERICRAWLER_CSS, FOOTER_CSS_EXTRA, BRAND_HEADER_HTML, FOOTER_HTML, info_box, success_box, warning_box, error_box

# --- Config ---
# Try local data/ dir first; fall back to /tmp on read-only cloud filesystems (Streamlit Cloud)
_local_db = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "reviews.db"))
try:
    os.makedirs(os.path.dirname(_local_db), exist_ok=True)
    DB_PATH = _local_db
except OSError:
    DB_PATH = "/tmp/reviews.db"

st.set_page_config(
    page_title="Mericrawler — Review Intelligence",
    page_icon="https://fonts.gstatic.com/s/i/short-term/release/materialsymbolsoutlined/search/default/24px.svg",
    layout="wide",
)

# Inject brand styles
st.markdown(MERICRAWLER_CSS, unsafe_allow_html=True)
st.markdown(FOOTER_CSS_EXTRA, unsafe_allow_html=True)

# Init DB on startup
init_db(DB_PATH)


@st.cache_resource(show_spinner=False)
def start_embedded_worker(db_path: str):
    """Keep the hosted demo usable when Streamlit has no second process."""
    stop_event = threading.Event()
    worker = threading.Thread(
        target=run_worker,
        kwargs={
            "db_path": db_path,
            "workers": 1,
            "min_request_interval": 1.0,
            "poll_interval": 1.0,
            "stop_event": stop_event,
            "install_signal_handlers": False,
        },
        name="mericrawler-embedded-worker",
        daemon=True,
    )
    worker.start()
    return worker


if os.getenv("MERICRAWLER_EMBED_WORKER", "1") == "1":
    start_embedded_worker(DB_PATH)

# --- Sidebar: previously crawled apps ---
st.sidebar.title("Crawled Apps")
pkg_entries = list_packages_with_names(DB_PATH)
sync_target = None  # (pkg, name) — sync runs AFTER the loop so its spinner gets full sidebar width
if pkg_entries:
    for entry_pkg, entry_name in pkg_entries:
        n = count_reviews(entry_pkg, DB_PATH)
        col_open, col_sync, col_del = st.sidebar.columns([3.2, 0.9, 0.9])
        with col_open:
            if st.button(f"{entry_name}  ({n:,})", key=f"sidebar_{entry_pkg}"):
                st.session_state.current_package_id = entry_pkg
                st.session_state.current_df = get_reviews(entry_pkg, DB_PATH)
        with col_sync:
            if st.button("↻", key=f"sync_{entry_pkg}", help="Fetch reviews posted since the last crawl"):
                sync_target = (entry_pkg, entry_name)
        with col_del:
            if st.button("🗑", key=f"del_{entry_pkg}", help="Delete this app and all its reviews"):
                st.session_state.confirm_delete = entry_pkg
                st.rerun()

        # Inline confirmation right under the row — deleting is destructive
        if st.session_state.get("confirm_delete") == entry_pkg:
            st.sidebar.markdown(f"Delete **{entry_name}** and all its reviews?")
            col_yes, col_no = st.sidebar.columns(2)
            if col_yes.button("Delete", key=f"del_yes_{entry_pkg}"):
                deleted = delete_package(entry_pkg, DB_PATH)
                if st.session_state.get("current_package_id") == entry_pkg:
                    st.session_state.pop("current_package_id", None)
                    st.session_state.pop("current_df", None)
                st.session_state.pop("confirm_delete", None)
                st.session_state.last_crawl_summary = (
                    "success", f"Deleted <strong>{entry_name}</strong> ({deleted:,} reviews)"
                )
                st.rerun()
            if col_no.button("Cancel", key=f"del_no_{entry_pkg}"):
                st.session_state.pop("confirm_delete", None)
                st.rerun()
else:
    st.sidebar.info("No apps crawled yet.")

if sync_target:
    sync_pkg, sync_name = sync_target
    enqueue_job(sync_pkg, DB_PATH, app_name=sync_name, mode="sync", langs=[])
    st.session_state.last_crawl_summary = (
        "success", f"Queued incremental sync for <strong>{sync_name}</strong>."
    )
    st.session_state.current_package_id = sync_pkg
    st.rerun()

# --- Main panel ---
st.markdown(BRAND_HEADER_HTML, unsafe_allow_html=True)
st.title("Mericrawler")
st.caption("Queue Google Play review crawls, then inspect fresh results while the worker runs.")

with st.form("queue_crawl_form"):
    user_input = st.text_area(
        "Apps to queue (one URL, package ID, or app name per line)",
        placeholder="com.roblox.client\nhttps://play.google.com/store/apps/details?id=com.example.app&gl=vn",
        height=100,
    )
    col1, col2, col3 = st.columns([4, 1, 1])
    with col1:
        lang_options = ["All languages"] + ALL_LANGUAGES
        lang = st.selectbox("Language", lang_options, index=0)
    with col2:
        count_choice = st.selectbox("Max reviews / language", [100, 200, 500, 1000, "Full history"], index=1)
    with col3:
        delay = st.number_input("Page delay (s)", min_value=0.0, value=1.0, step=0.25)
    crawl_btn = st.form_submit_button("Queue crawl", type="primary", disabled=not user_input.strip())

if crawl_btn and user_input.strip():
    queued = []
    errors = []
    selected_langs = ALL_LANGUAGES if lang == "All languages" else [lang]
    count = None if count_choice == "Full history" else count_choice
    for raw_input in [line.strip() for line in user_input.splitlines() if line.strip()]:
        try:
            detected_country = None
            if "play.google.com" in raw_input:
                pkg_id, detected_country = parse_url(raw_input)
            else:
                pkg_id = parse_package_id(raw_input)
            country = detected_country or "us"
            app_title = fetch_app_name(pkg_id, country=country)
            save_app_name(pkg_id, app_title, DB_PATH)
            job_id = enqueue_job(
                pkg_id, DB_PATH, app_name=app_title, langs=selected_langs,
                country=country, count_per_lang=count, delay=delay,
            )
            queued.append(f"{app_title} ({job_id[:8]})")
            st.session_state.current_package_id = pkg_id
        except Exception as exc:
            errors.append(f"{raw_input}: {exc}")
    if queued:
        st.session_state.last_crawl_summary = ("success", "Queued: " + ", ".join(queued))
    if errors:
        st.session_state.last_crawl_summary = ("warning", "Could not queue: " + "; ".join(errors))
    st.rerun()

# Outcome of the previous crawl run (stashed before st.rerun above)
if "last_crawl_summary" in st.session_state:
    kind, html = st.session_state.pop("last_crawl_summary")
    render_box = {"success": success_box, "warning": warning_box, "error": error_box}[kind]
    st.markdown(render_box(html), unsafe_allow_html=True)

# --- Queue monitor ----------------------------------------------------------
_fragment = st.fragment(run_every="5s") if hasattr(st, "fragment") else (lambda fn: fn)


@_fragment
def render_queue_panel():
    st.divider()
    st.subheader("Crawl queue")
    if not hasattr(st, "fragment"):
        if st.button("Refresh queue"):
            st.rerun()
    jobs = list_jobs(DB_PATH, limit=50)
    if not jobs:
        st.info("No jobs queued. Start with one or more apps above.")
    else:
        for job in jobs:
            label = job.get("app_name") or job["package_id"]
            status = display_status(job["status"])
            done = job["languages_completed"]
            total = job["total_languages"] or len(job["languages"]) or 1
            progress = min(1.0, done / total)
            left, middle, right = st.columns([4, 3, 1])
            with left:
                st.markdown(
                    f"**{label}**  \n"
                    f"`{job['package_id']}` · **{status}** · {job['last_event'] or 'queued'}"
                )
            with middle:
                st.progress(progress, text=f"{done}/{total} languages · {job['inserted_count']:,} new rows")
            with right:
                if job["status"] in {"queued", "running", "retrying", "waiting"}:
                    if st.button("Cancel", key=f"cancel_{job['job_id']}"):
                        request_job_cancel(job["job_id"], DB_PATH)
                        st.rerun()
                elif job["status"] in {"failed", "cancelled", "partial", "throttled"}:
                    if st.button("Retry", key=f"retry_{job['job_id']}"):
                        retry_job(job["job_id"], DB_PATH)
                        st.rerun()
            if job.get("error_msg"):
                st.caption(f"Reason: {job['error_msg']}")
            if job.get("next_retry_at") and job["status"] in {"throttled", "retrying"}:
                st.caption(f"Suggested next retry: {job['next_retry_at']}")


render_queue_panel()

# --- Results ---
pkg = st.session_state.get("current_package_id", "")
df: pd.DataFrame = get_reviews(pkg, DB_PATH) if pkg else pd.DataFrame()
if pkg and not df.empty:

    st.divider()

    # Current-app strip: immediate feedback on which dataset is active
    app_name = dict(pkg_entries).get(pkg, pkg) if pkg_entries else pkg
    last_crawl = str(df["crawled_at"].max())[:10] if "crawled_at" in df.columns else ""
    st.markdown(f"### {app_name}")
    st.caption(f"`{pkg}` · {len(df):,} reviews · last crawl {last_crawl}")

    tab_reviews, tab_analysis = st.tabs(["Reviews", "Analysis"])

    with tab_reviews:
        # Header row: title left, export buttons right
        hcol_title, hcol_csv, hcol_json = st.columns([6, 1, 1])
        with hcol_title:
            st.subheader(f"Reviews — {len(df):,} total")

        # Rating filter — 5 checkboxes always visible with counts per rating
        rating_counts = df["score"].value_counts()
        st.markdown("<p style='font-size:0.875rem;font-weight:500;color:#374151;margin-bottom:0.25rem'>Show ratings</p>", unsafe_allow_html=True)
        rc1, rc2, rc3, rc4, rc5 = st.columns(5)
        selected_stars = []
        for col, star in zip([rc1, rc2, rc3, rc4, rc5], [5, 4, 3, 2, 1]):
            cnt = int(rating_counts.get(star, 0))
            with col:
                if st.checkbox(f"{'⭐' * star}  {cnt:,}", value=True, key=f"star_filter_{star}"):
                    selected_stars.append(star)
        filtered = df[df["score"].isin(selected_stars)] if selected_stars else df

        # Keyword mining without a CSV round-trip ("ads", "crash", "quảng cáo"...)
        search_q = st.text_input(
            "Search in reviews",
            placeholder="e.g. quảng cáo, crash, ads — plain text, not regex",
            key="review_search",
        ).strip()
        if search_q:
            filtered = filtered[
                filtered["content"].str.contains(search_q, case=False, na=False, regex=False)
            ]

        # Export buttons — top-right, always visible before table.
        # Cached so every checkbox click doesn't re-serialize the whole dataset;
        # keyed on filter + row count + latest crawl time, _df itself is not hashed.
        @st.cache_data(max_entries=8)
        def build_exports(pkg_key, stars_key, row_count, latest_crawl, _df):
            return _df.to_csv(index=False), _df.to_json(orient="records", force_ascii=False, indent=2)

        latest_crawl = str(filtered["crawled_at"].max()) if not filtered.empty else ""
        csv, json_str = build_exports(
            pkg, (tuple(sorted(selected_stars)), search_q), len(filtered), latest_crawl, filtered
        )
        with hcol_csv:
            st.download_button(
                "Download CSV",
                data=csv,
                file_name=f"{pkg}-reviews.csv",
                mime="text/csv",
            )
        with hcol_json:
            st.download_button(
                "Download JSON",
                data=json_str,
                file_name=f"{pkg}-reviews.json",
                mime="application/json",
            )

        # Display table — dates trimmed to day precision (timestamps eat width)
        display_cols = ["username", "score", "content", "thumbs_up", "review_created_at", "reply_content"]
        display_df = filtered[display_cols].copy()
        display_df["review_created_at"] = display_df["review_created_at"].str.slice(0, 10)
        st.dataframe(
            display_df.rename(columns={
                "username": "User",
                "score": "Rating",
                "content": "Review",
                "thumbs_up": "👍",
                "review_created_at": "Date",
                "reply_content": "Dev Reply",
            }),
            column_config={
                "Rating": st.column_config.NumberColumn(format="%d ⭐", width="small"),
                "Review": st.column_config.TextColumn(width="large"),
                "Date": st.column_config.TextColumn(width="small"),
            },
            use_container_width=True,
            height=500,
        )
        st.caption(f"Showing {len(filtered):,} of {len(df):,} reviews")

    with tab_analysis:
        render_analysis_tab(df, pkg)

# --- Footer (always visible) ---
st.markdown(FOOTER_HTML, unsafe_allow_html=True)
