"""Table-based queue monitor with persistent status guidance."""

from datetime import datetime, timezone
from html import escape

import pandas as pd
import streamlit as st

from queue_view import PENDING, job_notice, queue_groups, queue_guidance, ready_to_start, responsive
from storage.sqlite_store import queue_snapshot


def open_reviews(package_id):
    st.session_state.insights_mode = "Single app"
    st.session_state.current_package_id = package_id
    st.session_state.result_picker = package_id
    st.session_state.workspace_view = "Insights"


def queue_row(job, processing, positions, now, saved_count, *, preview_mode=False):
    notice = job_notice(job, processing, positions, now)
    status, message, tone = notice.label, notice.message, notice.tone
    if job["status"] in PENDING and ready_to_start(job, now):
        status, tone = "Queued", "info"
        if preview_mode:
            message = "Preview only · live crawling is off"
        elif any(responsive(item, now) for item in processing):
            message = "Wait for running apps to finish · starts automatically"
        else:
            message = "Waiting for crawl service · do not submit again"
    elif job["status"] in {"failed", "cancelled", "partial", "throttled"}:
        message = "Crawl incomplete · saved reviews are available in Apps" if saved_count else "Crawl incomplete · no saved reviews"
        if job["status"] == "cancelled":
            tone = "neutral"
    elif job["status"] == "complete":
        message = "View saved reviews in Apps" if saved_count else "Finished · no saved reviews"
    total = job["total_languages"] or len(job["languages"]) or 1
    done = job["languages_completed"]
    return {
        "App": job.get("app_name") or job["package_id"],
        "Status": status,
        "Queue #": positions.get(job["job_id"]),
        "Progress": min(100, max(0, round(done / total * 100))),
        "Languages": f"{done}/{total}" + (f" · {job['last_lang']}" if job["last_lang"] else ""),
        "New reviews": job["inserted_count"],
        "Saved reviews": saved_count,
        "Next step": message,
        "Package ID": job["package_id"],
        "Store": job["country"].upper(),
        "Submitted (UTC)": pd.to_datetime(job["created_at"], utc=True).strftime("%Y-%m-%d %H:%M"),
    }, tone


def render_queue(db_path, *, preview_mode=False):
    st.markdown('<div class="crawl-section-heading queue-panel-heading"><span class="crawl-step">2</span>'
                '<div><h2 id="crawl-queue">Crawl queue</h2>'
                '<p>One row per crawl request. Track status, progress and saved reviews.</p></div></div>',
                unsafe_allow_html=True)
    snapshot = queue_snapshot(db_path)
    now = datetime.now(timezone.utc)
    processing, pending, positions = queue_groups(snapshot["active"], now)
    guidance = queue_guidance(processing, pending, now, preview_mode=preview_mode)
    if guidance and not preview_mode:
        st.markdown(f'<div class="queue-guidance queue-guidance-{guidance.tone}" role="status">'
                    f'<strong>{escape(guidance.label)}</strong><p>{escape(guidance.message)}</p></div>',
                    unsafe_allow_html=True)
    if not snapshot["active"] and not snapshot["history"]:
        st.info("Your queue is empty. Add Google Play links above to start collecting reviews.")
        return
    jobs = snapshot["active"] + snapshot["history"]
    presented = [queue_row(job, processing, positions, now, snapshot["review_counts"].get(job["package_id"], 0),
                           preview_mode=preview_mode) for job in jobs]
    frame = pd.DataFrame([row for row, _ in presented])
    frame["Queue #"] = pd.array(frame["Queue #"], dtype="Int64")
    colors = {"neutral": ("#F1F5F9", "#475569"), "info": ("#EFF6FF", "#1D4ED8"), "warning": ("#FFFBEB", "#854D0E"),
              "success": ("#F0FDF4", "#166534"), "error": ("#FEF2F2", "#991B1B")}
    styles = [f"background-color: {colors[tone][0]}; color: {colors[tone][1]}; font-weight: 600" for _, tone in presented]
    styled = frame.style.apply(lambda _: styles, subset=["Status"])
    st.dataframe(styled,
                         hide_index=True, use_container_width=True, row_height=52, height=min(700, 56 + 52 * len(jobs)),
                         column_config={
                             "App": st.column_config.TextColumn(width="medium"),
                             "Status": st.column_config.TextColumn(width="medium"),
                             "Progress": st.column_config.ProgressColumn(min_value=0, max_value=100, format="%d%%",
                                 help="Languages completed, not percentage of all Google Play reviews."),
                             "Queue #": st.column_config.NumberColumn(format="%d", help="Position among eligible waiting apps."),
                             "New reviews": st.column_config.NumberColumn(format="%d", help="New reviews inserted by this crawl attempt."),
                             "Saved reviews": st.column_config.NumberColumn(format="%d", help="All saved reviews for this app, including earlier crawls."),
                             "Next step": st.column_config.TextColumn(width="large"),
                         })
    st.caption(f"{len(jobs):,} shown · {len(snapshot['active']):,} active requests · "
               f"latest {len(snapshot['history'])} of {snapshot['history_count']} past attempts available. "
               "Progress counts completed languages; pages may still be saving within a language.")
