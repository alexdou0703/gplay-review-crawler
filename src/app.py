"""Google Play Review Crawler — Streamlit UI."""

import sys
import os
from html import escape as html_escape

# Ensure src/ is in path for local imports
sys.path.insert(0, os.path.dirname(__file__))

import streamlit as st
import pandas as pd

from crawler.url_parser import parse_package_id, parse_url
from crawler.gplay_crawler import (
    crawl_reviews_iter, crawl_reviews_all_languages, resume_or_fresh,
    ALL_LANGUAGES, fetch_app_name,
)
from storage.sqlite_store import (
    init_db, get_reviews, count_reviews, save_app_name, list_packages_with_names,
    save_reviews_and_state, save_crawl_state, load_crawl_state,
)
from crawl_service import sync_package
from ui_styles import DRAVASTUDIO_CSS, FOOTER_CSS_EXTRA, BRAND_HEADER_HTML, FOOTER_HTML, info_box, success_box, warning_box, error_box

# --- Config ---
# Try local data/ dir first; fall back to /tmp on read-only cloud filesystems (Streamlit Cloud)
_local_db = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "reviews.db"))
try:
    os.makedirs(os.path.dirname(_local_db), exist_ok=True)
    DB_PATH = _local_db
except OSError:
    DB_PATH = "/tmp/reviews.db"

st.set_page_config(
    page_title="Dravastudio — Review Crawler",
    page_icon="https://fonts.gstatic.com/s/i/short-term/release/materialsymbolsoutlined/search/default/24px.svg",
    layout="wide",
)

# Inject brand styles
st.markdown(DRAVASTUDIO_CSS, unsafe_allow_html=True)
st.markdown(FOOTER_CSS_EXTRA, unsafe_allow_html=True)

# Init DB on startup
init_db(DB_PATH)

# --- Sidebar: previously crawled apps ---
st.sidebar.title("Crawled Apps")
pkg_entries = list_packages_with_names(DB_PATH)
if pkg_entries:
    for pkg, app_name in pkg_entries:
        n = count_reviews(pkg, DB_PATH)
        col_open, col_sync = st.sidebar.columns([4, 1])
        with col_open:
            if st.button(f"{app_name}  ({n})", key=f"sidebar_{pkg}"):
                st.session_state.current_package_id = pkg
                st.session_state.current_df = get_reviews(pkg, DB_PATH)
        with col_sync:
            if st.button("↻", key=f"sync_{pkg}", help="Fetch reviews posted since the last crawl"):
                with st.spinner(f"Syncing {app_name}..."):
                    # Page budget keeps a shallow dataset from turning this
                    # click into a blocking full-history walk.
                    results = sync_package(pkg, DB_PATH, max_pages=25)
                total_new = sum(new for new, _ in results.values())
                throttled = [l for l, (_, s) in results.items() if s.status == "throttled"]
                partial = [l for l, (_, s) in results.items() if s.status == "partial"]
                if throttled or partial:
                    notes = []
                    if throttled:
                        notes.append(f"rate-limited on: {', '.join(throttled)} — try again later")
                    if partial:
                        notes.append(
                            f"dataset too shallow to catch up on: {', '.join(partial)} — "
                            "run <code>python src/crawl_cli.py … --sync</code> for an unbounded sync"
                        )
                    st.session_state.last_crawl_summary = (
                        "warning",
                        f"Synced <strong>{app_name}</strong>: +{total_new} new — partial; " + "; ".join(notes),
                    )
                else:
                    st.session_state.last_crawl_summary = (
                        "success", f"Synced <strong>{app_name}</strong>: +{total_new} new reviews"
                    )
                st.session_state.current_package_id = pkg
                st.session_state.current_df = get_reviews(pkg, DB_PATH)
                st.rerun()
else:
    st.sidebar.info("No apps crawled yet.")

# --- Main panel ---
st.markdown(BRAND_HEADER_HTML, unsafe_allow_html=True)
st.title("Play Store Review Crawler")
st.caption("Enter an app name, Google Play URL, or package ID to fetch reviews.")

col1, col2, col3 = st.columns([4, 1, 1])
with col1:
    user_input = st.text_input(
        "App name / URL / package ID",
        placeholder="https://play.google.com/store/apps/details?id=com.roblox.client",
    )
with col2:
    # "All languages" crawls ALL_LANGUAGES sequentially (~200 reviews each)
    lang_options = ["All languages"] + ALL_LANGUAGES
    lang = st.selectbox("Language", lang_options, index=0)
with col3:
    count = st.selectbox(
        "Max reviews",
        [100, 200, 500, 1000],
        index=1,
        help="Per language when 'All languages' is selected",
    )

crawl_btn = st.button("Search Reviews", type="primary", disabled=not user_input)
st.caption(
    "Full-history crawls can take hours — run them headless with "
    "`python src/crawl_cli.py <app> --full` (resumable; see README) and use this page to browse results."
)

# --- Crawl action ---
if crawl_btn and user_input:
    try:
        with st.spinner("Resolving package ID..."):
            detected_country = None
            if "play.google.com" in user_input:
                pkg_id, detected_country = parse_url(user_input)
            else:
                pkg_id = parse_package_id(user_input)

        # Respect the store country from the pasted URL's gl param when present
        effective_country = detected_country or "us"
        app_title = fetch_app_name(pkg_id, country=effective_country)
        save_app_name(pkg_id, app_title, DB_PATH)
        st.markdown(info_box(f"<strong>{app_title}</strong> <code>{pkg_id}</code> — crawling up to {count} reviews..."), unsafe_allow_html=True)

        # Every page is saved with its crawl checkpoint as it arrives, so an
        # interrupted crawl keeps everything fetched so far and resumes from
        # the stored cursor instead of restarting.
        inserted_counter = {"n": 0}

        def save_batch(batch_lang, batch, batch_state):
            inserted_counter["n"] += save_reviews_and_state(batch, pkg_id, batch_state, DB_PATH)

        if lang == "All languages":
            states = {
                l: resume_or_fresh(
                    load_crawl_state(pkg_id, l, effective_country, DB_PATH),
                    pkg_id, l, effective_country,
                )
                for l in ALL_LANGUAGES
            }
            resumable = sum(1 for s in states.values() if s.cursor)
            if resumable:
                st.markdown(info_box(
                    f"Previous crawl incomplete — resuming <strong>{resumable}</strong> "
                    "language(s) from checkpoint"
                ), unsafe_allow_html=True)

            progress_bar = st.progress(0, text="Starting multi-language crawl...")

            def on_progress(l, fetched, total_so_far):
                idx = ALL_LANGUAGES.index(l) + 1
                pct = idx / len(ALL_LANGUAGES)
                progress_bar.progress(
                    pct,
                    text=f"[{idx}/{len(ALL_LANGUAGES)}] {l}: +{fetched} unique | total {total_so_far}",
                )

            raw, summary = crawl_reviews_all_languages(
                pkg_id, count_per_lang=count, country=effective_country,
                progress_callback=on_progress, on_batch=save_batch, states=states,
            )
            progress_bar.progress(1.0, text=f"Done — {len(raw)} unique reviews across {len(ALL_LANGUAGES)} languages")
        else:
            state = resume_or_fresh(
                load_crawl_state(pkg_id, lang, effective_country, DB_PATH),
                pkg_id, lang, effective_country,
            )
            if state.cursor:
                st.markdown(info_box(
                    "Previous crawl incomplete — resuming from checkpoint"
                ), unsafe_allow_html=True)
            raw = []
            with st.spinner(f"Crawling reviews in [{lang}] (this may take a moment)..."):
                for batch in crawl_reviews_iter(
                    pkg_id, count=count, lang=lang, country=effective_country, state=state
                ):
                    save_batch(lang, batch, state)
                    raw.extend(batch)
            summary = {lang: state}

        # Record terminal statuses too — a throttled/complete verdict can land
        # after the last saved page (or with no page at all).
        for s in summary.values():
            save_crawl_state(s, DB_PATH)

        inserted = inserted_counter["n"]
        total_stored = count_reviews(pkg_id, DB_PATH)

        st.session_state.current_package_id = pkg_id
        st.session_state.current_df = get_reviews(pkg_id, DB_PATH)

        # Partial data must never be presented as success.
        problems = {l: s for l, s in summary.items() if s.status in ("throttled", "error")}
        counts_html = (
            f"Fetched <strong>{len(raw)}</strong> reviews — "
            f"<strong>{inserted}</strong> new added — "
            f"<strong>{total_stored}</strong> total stored"
        )
        if problems:
            detail = ", ".join(
                f"{l}: {s.status}" + (f" ({html_escape(s.error_msg)})" if s.error_msg else "")
                for l, s in problems.items()
            )
            msg = (
                "warning",
                f"{counts_html}<br><strong>Partial results</strong> — Google rate-limited or "
                f"errored on: {detail}. Run the same crawl again later to fetch the rest.",
            )
        elif len(raw) == 0:
            msg = (
                "warning",
                f"No reviews found for <strong>{pkg_id}</strong>. "
                "The app may be new, have no public reviews yet, or not available in this language.",
            )
        else:
            msg = ("success", counts_html)

        # Stash the outcome so it survives st.rerun() (rendered below).
        st.session_state.last_crawl_summary = msg
        st.rerun()

    except ValueError as e:
        st.markdown(error_box(f"Could not resolve app: {e}"), unsafe_allow_html=True)
    except Exception as e:
        st.markdown(error_box(f"Crawl failed: {e}"), unsafe_allow_html=True)

# Outcome of the previous crawl run (stashed before st.rerun above)
if "last_crawl_summary" in st.session_state:
    kind, html = st.session_state.pop("last_crawl_summary")
    render_box = {"success": success_box, "warning": warning_box, "error": error_box}[kind]
    st.markdown(render_box(html), unsafe_allow_html=True)

# --- Results ---
if "current_df" in st.session_state and not st.session_state.current_df.empty:
    df: pd.DataFrame = st.session_state.current_df
    pkg = st.session_state.get("current_package_id", "")

    st.divider()

    # Header row: title left, export buttons right
    hcol_title, hcol_csv, hcol_json = st.columns([6, 1, 1])
    with hcol_title:
        st.subheader(f"Reviews — {pkg} ({len(df)} total)")

    # Rating filter — 5 checkboxes always visible with counts per rating
    rating_counts = df["score"].value_counts()
    st.markdown("<p style='font-size:0.875rem;font-weight:500;color:#374151;margin-bottom:0.25rem'>Show ratings</p>", unsafe_allow_html=True)
    rc1, rc2, rc3, rc4, rc5 = st.columns(5)
    selected_stars = []
    for col, star in zip([rc1, rc2, rc3, rc4, rc5], [5, 4, 3, 2, 1]):
        cnt = int(rating_counts.get(star, 0))
        with col:
            if st.checkbox(f"{'⭐' * star}  {cnt}", value=True, key=f"star_filter_{star}"):
                selected_stars.append(star)
    filtered = df[df["score"].isin(selected_stars)] if selected_stars else df

    # Export buttons — top-right, always visible before table.
    # Cached so every checkbox click doesn't re-serialize the whole dataset;
    # keyed on filter + row count + latest crawl time, _df itself is not hashed.
    @st.cache_data(max_entries=8)
    def build_exports(pkg_key, stars_key, row_count, latest_crawl, _df):
        return _df.to_csv(index=False), _df.to_json(orient="records", force_ascii=False, indent=2)

    latest_crawl = str(filtered["crawled_at"].max()) if not filtered.empty else ""
    csv, json_str = build_exports(pkg, tuple(sorted(selected_stars)), len(filtered), latest_crawl, filtered)
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

    # Display table
    display_cols = ["username", "score", "content", "thumbs_up", "review_created_at", "reply_content"]
    st.dataframe(
        filtered[display_cols].rename(columns={
            "username": "User",
            "score": "Rating",
            "content": "Review",
            "thumbs_up": "👍",
            "review_created_at": "Date",
            "reply_content": "Dev Reply",
        }),
        use_container_width=True,
        height=500,
    )
    st.caption(f"Showing {len(filtered)} of {len(df)} reviews")

# --- Footer (always visible) ---
st.markdown(FOOTER_HTML, unsafe_allow_html=True)
