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
from crawler.gplay_crawler import ALL_LANGUAGES
from storage.sqlite_store import (
    init_db, get_reviews, count_reviews, save_app_name, list_packages_with_names,
    delete_package, enqueue_job, latest_package_job, app_library_summary,
)
from queue_ui import render_queue, open_reviews
from crawl_worker import run_worker
from analysis_ui import render_analysis_tab
from comparison_ui import render_comparison
from ui_styles import MERICRAWLER_CSS, FOOTER_CSS_EXTRA, BRAND_HEADER_HTML, FOOTER_HTML, info_box, success_box, warning_box, error_box

# --- Config ---
# Try local data/ dir first; fall back to /tmp on read-only cloud filesystems (Streamlit Cloud)
_local_db = os.path.abspath(os.getenv(
    "MERICRAWLER_DB_PATH", os.path.join(os.path.dirname(__file__), "..", "data", "reviews.db")
))
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


def remember_review_filters():
    """Keep preferences when Streamlit removes widgets on the Crawl screen."""
    st.session_state.review_filters = {
        "review_search": st.session_state.get("review_search", ""),
        **{f"star_filter_{star}": st.session_state.get(f"star_filter_{star}", True)
           for star in range(1, 6)},
    }


@st.cache_resource(show_spinner=False)
def start_embedded_worker(db_path: str):
    """Keep the hosted demo usable when Streamlit has no second process."""
    stop_event = threading.Event()
    worker = threading.Thread(
        target=run_worker,
        kwargs={
            "db_path": db_path,
            "workers": 2,
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


PREVIEW_MODE = os.getenv("MERICRAWLER_PREVIEW", "0") == "1"
if not PREVIEW_MODE and os.getenv("MERICRAWLER_EMBED_WORKER", "1") == "1":
    if not start_embedded_worker(DB_PATH).is_alive():
        start_embedded_worker.clear()
        start_embedded_worker(DB_PATH)

# --- Library actions run as callbacks before navigation widgets render. ---
pkg_entries = list_packages_with_names(DB_PATH)


def sync_library_app(package_id, app_name):
    if not count_reviews(package_id, DB_PATH):
        st.session_state.last_crawl_summary = ("warning", "No saved reviews to sync yet. Wait for the initial crawl to save reviews.")
        return
    enqueue_job(package_id, DB_PATH, app_name=app_name, mode="sync", langs=[])
    st.session_state.last_crawl_summary = (
        "success", f"Queued incremental sync for <strong>{html_escape(app_name)}</strong>."
    )
    st.session_state.current_package_id = package_id
    st.session_state.workspace_view = "Crawl"


def delete_library_app(package_id, app_name):
    if not count_reviews(package_id, DB_PATH):
        st.session_state.pop("confirm_delete", None)
        return
    deleted = delete_package(package_id, DB_PATH)
    if st.session_state.get("current_package_id") == package_id:
        st.session_state.pop("current_package_id", None)
        st.session_state.pop("current_df", None)
    if st.session_state.get("result_picker") == package_id:
        st.session_state.pop("result_picker", None)
    st.session_state.pop("library_picker", None)
    st.session_state.pop("confirm_delete", None)
    st.session_state.last_crawl_summary = (
        "success", f"Deleted <strong>{html_escape(app_name)}</strong> ({deleted:,} reviews)"
    )

# --- Main panel ---
st.markdown(BRAND_HEADER_HTML, unsafe_allow_html=True)
workspace_view = st.radio("Workspace", ["Crawl", "Apps", "Insights"], horizontal=True, key="workspace_view", label_visibility="collapsed")

if workspace_view == "Apps":
    st.title("Apps")
    st.caption("Manage your saved apps. Open insights, sync reviews or remove an app from your library.")
    library = app_library_summary(DB_PATH)
    query = st.text_input("Search apps", placeholder="Search by app name or package ID", key="library_search")
    if query.strip():
        library = library[library["app_name"].str.contains(query.strip(), case=False, regex=False) |
                          library["package_id"].str.contains(query.strip(), case=False, regex=False)]
    if library.empty:
        st.info("No apps match this search." if query.strip() else "Your library is empty. Add Google Play links in Crawl to get started.")
    else:
        st.caption(f"{len(library):,} apps · {int(library['reviews'].sum()):,} saved reviews")
        names = library.set_index("package_id")["app_name"].to_dict()
        if st.session_state.get("library_picker") not in names:
            st.session_state.library_picker = next(iter(names))
        selected = st.selectbox("App to manage", list(names), format_func=lambda p: f"{names[p]} · {p}", key="library_picker")
        has_reviews = bool(library.loc[library["package_id"].eq(selected), "reviews"].iloc[0])
        if st.session_state.get("confirm_delete") != selected:
            st.session_state.pop("confirm_delete", None)
        open_col, sync_col, delete_col = st.columns(3)
        open_col.button("Open insights", type="primary", on_click=open_reviews, args=(selected,), use_container_width=True)
        sync_col.button("Sync reviews", key="library_sync", on_click=sync_library_app,
                        args=(selected, names[selected]), use_container_width=True,
                        disabled=not has_reviews,
                        help="Queue a crawl to fetch reviews posted since the last sync" if has_reviews else "Available after the first reviews have been saved")
        if delete_col.button("Delete saved app", key="library_delete", use_container_width=True,
                             disabled=not has_reviews,
                             help="Delete this app's saved reviews" if has_reviews else "This app has no saved reviews to delete"):
            st.session_state.confirm_delete = selected
        if st.session_state.get("confirm_delete") == selected:
            with st.container(border=True):
                st.warning(f"Delete {names[selected]} ({selected}) and all its saved reviews? This cannot be undone.")
                confirm, cancel = st.columns(2)
                confirm.button("Confirm deletion", key="library_delete_confirm", on_click=delete_library_app,
                               args=(selected, names[selected]), use_container_width=True)
                if cancel.button("Keep app", key="library_delete_cancel", use_container_width=True):
                    st.session_state.pop("confirm_delete", None)
                    st.rerun()
        library_display = library.copy()
        library_display["last_saved"] = pd.to_datetime(library_display["last_saved"], utc=True).dt.strftime("%Y-%m-%d %H:%M")
        st.dataframe(library_display.rename(columns={"app_name": "App", "package_id": "Package ID", "reviews": "Reviews",
                     "average_rating": "Average rating", "languages": "Languages", "last_saved": "Last saved (UTC)"}),
                     column_order=["App", "Package ID", "Reviews", "Average rating", "Languages", "Last saved (UTC)"],
                     column_config={"Average rating": st.column_config.NumberColumn(format="%.2f"),
                                    "Reviews": st.column_config.NumberColumn(format="%d")},
                     hide_index=True, use_container_width=True, row_height=52, height=min(650, 56 + len(library) * 52))

if workspace_view == "Crawl":
    st.title("Crawl workspace")
    st.markdown("Add your apps below, then follow their progress in the crawl queue.")
    with st.form("queue_crawl_form"):
        st.markdown('<div class="crawl-section-heading crawl-form-heading"><span class="crawl-step">1</span>'
                    '<div><h2>Add apps to crawl</h2><p>Paste your apps, choose the review limit, then add them to the queue.</p></div></div>',
                    unsafe_allow_html=True)
        user_input = st.text_area(
            "Google Play apps",
            placeholder="com.roblox.client\nhttps://play.google.com/store/apps/details?id=com.example.app&gl=vn",
            height=120,
        )
        st.caption("One Google Play link, package ID, or app name per line.")
        col1, col2 = st.columns(2)
        with col1:
            lang_options = ["All languages"] + ALL_LANGUAGES
            lang = st.selectbox("Language", lang_options, index=0)
        with col2:
            count_choice = st.selectbox("Max reviews / language", [100, 200, 500, 1000, "Full history"], index=1)
        with st.expander("Advanced settings · request delay"):
            delay = st.number_input("Page delay (s)", min_value=0.0, value=1.0, step=0.25)
            st.caption("Pause between pages. A longer delay reduces request frequency.")
        # Form widgets only publish their values when the form is submitted. Do not
        # derive the submit button's disabled state from `user_input`, otherwise the
        # button stays disabled while the user is typing and can never submit.
        crawl_btn = st.form_submit_button("Add to crawl queue", type="primary", use_container_width=True)
        st.caption("Preview only: add apps to the sample queue; live crawling is off." if PREVIEW_MODE else
                   "Apps start automatically when a crawl slot opens. Follow their status below.")

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
                # URLs/package IDs can be queued without waiting on Google metadata.
                app_title = dict(pkg_entries).get(pkg_id, pkg_id)
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
            st.session_state.last_crawl_summary = ("success", "Added to queue: " + html_escape(", ".join(queued)))
        if errors:
            st.session_state.last_crawl_summary = ("warning", ("Added to queue: " + html_escape(", ".join(queued)) + ". " if queued else "") + "Could not queue: " + html_escape("; ".join(errors)))
        st.rerun()
    elif crawl_btn:
        st.session_state.last_crawl_summary = ("warning", "Enter at least one Google Play URL or package ID.")

# Outcome of the previous crawl run (stashed before st.rerun above)
if "last_crawl_summary" in st.session_state:
    kind, html = st.session_state.pop("last_crawl_summary")
    render_box = {"success": success_box, "warning": warning_box, "error": error_box}[kind]
    st.markdown(render_box(html), unsafe_allow_html=True)

# --- Queue monitor ----------------------------------------------------------
_fragment = st.fragment(run_every="5s") if hasattr(st, "fragment") else (lambda fn: fn)


@_fragment
def render_queue_panel():
    render_queue(DB_PATH, preview_mode=PREVIEW_MODE)


if workspace_view == "Crawl":
    with st.container(border=True):
        render_queue_panel()

if workspace_view == "Insights":
    st.title("App insights")
    insights_mode = st.radio("Insights mode", ["Single app", "Compare apps"], horizontal=True, key="insights_mode")
    if insights_mode == "Compare apps":
        render_comparison(DB_PATH, pkg_entries)

if workspace_view == "Insights" and insights_mode == "Single app":
    # --- Results ---
    options = dict(pkg_entries)
    current = st.session_state.get("current_package_id", "")
    if current:
        options.setdefault(current, current)
    picker_col, refresh_col = st.columns([5, 1], vertical_alignment="bottom")
    if options:
        if st.session_state.get("result_picker") not in options:
            st.session_state.result_picker = current or next(iter(options))
        with picker_col:
            pkg = st.selectbox("App to explore", list(options), format_func=lambda package: options[package], key="result_picker")
        st.session_state.current_package_id = pkg
    else:
        pkg = ""
    if refresh_col.button("Refresh results", key="refresh_results"):
        st.rerun()
    latest_job = latest_package_job(pkg, DB_PATH) if pkg else None
    if latest_job:
        if latest_job["status"] in {"queued", "running", "waiting", "retrying"}:
            st.info("This app has an active crawl. These results are a saved snapshot; use Refresh results to load newly saved reviews.")
        elif latest_job["status"] in {"partial", "throttled", "failed", "cancelled"}:
            st.warning("This crawl is incomplete. You can explore saved reviews now, or use Retry in Crawl to continue unfinished languages.")
    df: pd.DataFrame = get_reviews(pkg, DB_PATH) if pkg else pd.DataFrame()
    if pkg and not df.empty:

        st.divider()

        # Current-app strip: immediate feedback on which dataset is active
        app_name = dict(pkg_entries).get(pkg, pkg) if pkg_entries else pkg
        last_crawl = str(df["crawled_at"].max())[:10] if "crawled_at" in df.columns else ""
        st.subheader(app_name)
        st.caption(f"`{pkg}` · {len(df):,} reviews · last crawl {last_crawl}")

        detail_view = st.radio("Explore", ["Reviews", "Analytics"], horizontal=True, key="detail_view", label_visibility="collapsed")

        if detail_view == "Reviews":
            # Header row: title left, export buttons right
            hcol_title, hcol_csv, hcol_json = st.columns([6, 1, 1])
            with hcol_title:
                st.subheader(f"Reviews — {len(df):,} total")

            # Rating filter — 5 checkboxes always visible with counts per rating
            rating_counts = df["score"].value_counts()
            st.markdown("<p style='font-size:0.875rem;font-weight:500;color:#374151;margin-bottom:0.25rem'>Show ratings</p>", unsafe_allow_html=True)
            rc1, rc2, rc3, rc4, rc5 = st.columns(5)
            selected_stars = []
            filter_preferences = st.session_state.get("review_filters", {})
            for col, star in zip([rc1, rc2, rc3, rc4, rc5], [5, 4, 3, 2, 1]):
                cnt = int(rating_counts.get(star, 0))
                with col:
                    if st.checkbox(f"{star} stars · {cnt:,}",
                                   value=filter_preferences.get(f"star_filter_{star}", True),
                                   key=f"star_filter_{star}", on_change=remember_review_filters):
                        selected_stars.append(star)
            filtered = df[df["score"].isin(selected_stars)] if selected_stars else df

            # Keyword mining without a CSV round-trip ("ads", "crash", "quảng cáo"...)
            search_q = st.text_input(
                "Search in reviews",
                placeholder="e.g. quảng cáo, crash, ads — plain text, not regex",
                key="review_search",
                value=filter_preferences.get("review_search", ""),
                on_change=remember_review_filters,
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
                    "thumbs_up": "Helpful",
                    "review_created_at": "Date",
                    "reply_content": "Dev Reply",
                }),
                column_config={
                    "Rating": st.column_config.NumberColumn(format="%d / 5", width="small"),
                    "Review": st.column_config.TextColumn(width="large"),
                    "Date": st.column_config.TextColumn(width="small"),
                },
                use_container_width=True,
                row_height=52,
                height=560,
            )
            st.caption(f"Showing {len(filtered):,} of {len(df):,} reviews")

        else:
            render_analysis_tab(df, pkg)

    else:
        st.info("No saved reviews for this app yet. Follow its progress in Crawl and refresh results after the first page is saved." if pkg else "Add your first app in Crawl, then open its reviews from Apps.")

# --- Footer (always visible) ---
st.markdown(FOOTER_HTML, unsafe_allow_html=True)
