"""Google Play Review Crawler — Streamlit UI."""

import sys
import os

# Ensure src/ is in path for local imports
sys.path.insert(0, os.path.dirname(__file__))

import streamlit as st
import pandas as pd

from crawler.url_parser import parse_package_id, parse_url
from crawler.gplay_crawler import crawl_reviews, crawl_reviews_all_languages, ALL_LANGUAGES
from storage.sqlite_store import init_db, save_reviews, get_reviews, list_packages, count_reviews
from ui_styles import DRAVASTUDIO_CSS, FOOTER_CSS_EXTRA, BRAND_HEADER_HTML, FOOTER_HTML

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
packages = list_packages(DB_PATH)
if packages:
    for pkg in packages:
        n = count_reviews(pkg, DB_PATH)
        if st.sidebar.button(f"{pkg}  ({n} reviews)", key=f"sidebar_{pkg}"):
            st.session_state.current_package_id = pkg
            st.session_state.current_df = get_reviews(pkg, DB_PATH)
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

# --- Crawl action ---
if crawl_btn and user_input:
    try:
        with st.spinner("Resolving package ID..."):
            detected_country = None
            if "play.google.com" in user_input:
                pkg_id, detected_country = parse_url(user_input)
            else:
                pkg_id = parse_package_id(user_input)

        effective_country = "us"
        st.info(f"Package ID: **{pkg_id}** — crawling up to {count} reviews...")

        if lang == "All languages":
            progress_bar = st.progress(0, text="Starting multi-language crawl...")

            def on_progress(l, fetched, total_so_far):
                idx = ALL_LANGUAGES.index(l) + 1
                pct = idx / len(ALL_LANGUAGES)
                progress_bar.progress(
                    pct,
                    text=f"[{idx}/{len(ALL_LANGUAGES)}] {l}: +{fetched} unique | total {total_so_far}",
                )

            raw = crawl_reviews_all_languages(
                pkg_id, count_per_lang=count, country=effective_country, progress_callback=on_progress
            )
            progress_bar.progress(1.0, text=f"Done — {len(raw)} unique reviews across {len(ALL_LANGUAGES)} languages")
        else:
            with st.spinner(f"Crawling reviews in [{lang}] (this may take a moment)..."):
                raw = crawl_reviews(pkg_id, count=count, lang=lang, country=effective_country)

        inserted = save_reviews(raw, pkg_id, DB_PATH)
        total_stored = count_reviews(pkg_id, DB_PATH)

        st.session_state.current_package_id = pkg_id
        st.session_state.current_df = get_reviews(pkg_id, DB_PATH)

        if len(raw) == 0:
            st.warning(
                f"No reviews found for **{pkg_id}**. "
                "The app may be new, have no public reviews yet, or not available in this language."
            )
        else:
            st.success(
                f"Fetched **{len(raw)}** reviews — "
                f"**{inserted}** new added — "
                f"**{total_stored}** total stored"
            )
            st.rerun()

    except ValueError as e:
        st.error(f"Could not resolve app: {e}")
    except Exception as e:
        st.error(f"Crawl failed: {e}")

# --- Results ---
if "current_df" in st.session_state and not st.session_state.current_df.empty:
    df: pd.DataFrame = st.session_state.current_df
    pkg = st.session_state.get("current_package_id", "")

    st.divider()
    st.subheader(f"Reviews — {pkg} ({len(df)} total)")

    # Star filter
    selected_stars = st.multiselect(
        "Filter by rating",
        options=[5, 4, 3, 2, 1],
        default=[5, 4, 3, 2, 1],
        format_func=lambda x: "⭐" * x,
    )
    filtered = df[df["score"].isin(selected_stars)] if selected_stars else df

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

    # Export
    col_csv, col_json = st.columns(2)
    with col_csv:
        csv = filtered.to_csv(index=False)
        st.download_button(
            "Download CSV",
            data=csv,
            file_name=f"{pkg}-reviews.csv",
            mime="text/csv",
        )
    with col_json:
        json_str = filtered.to_json(orient="records", force_ascii=False, indent=2)
        st.download_button(
            "Download JSON",
            data=json_str,
            file_name=f"{pkg}-reviews.json",
            mime="application/json",
        )

# --- Footer (always visible) ---
st.markdown(FOOTER_HTML, unsafe_allow_html=True)
