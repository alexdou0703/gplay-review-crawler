# UI/UX Review — Google Play Review Crawler (Streamlit, Dravastudio)

Reviewed live at http://localhost:8501 (agent-browser headless Chromium, 1440×900 + 375×812), with source: `src/app.py`, `src/ui_styles.py`, `src/analysis_ui.py`, `.streamlit/config.toml`. Dataset: Block Blast 39.6k reviews / 22 langs, Character AI 31k. Screenshots captured for landing, Reviews tab, star filters + table, Analysis tab (Weekly + Monthly), expanded spike window, market mix, version scatter, dev-engagement metrics, mobile 375px.

## Verdict

Brand layer (`ui_styles.py`) is genuinely good: coherent purple identity, polished sidebar, input/button/pill styling, sensible footer. Information architecture is right for the job — crawl form → 2 tabs, analysis ordered volume→spikes→market→version→replies matches how a strategy person actually reads a competitor.

The app is undermined by one structural defect: **`.streamlit/config.toml` has no `[theme]` block**, so Streamlit runs its *dark* base theme underneath the forced-light brand CSS. Every native component the custom CSS doesn't reach renders dark-theme colors on the lavender page: captions and radio/expander/metric text are near-white-on-near-white (measured `rgb(250,250,250)` text on `rgb(245,243,255)` bg ≈ **1.02:1 contrast — invisible**), while dataframe, Altair charts, expander bodies, and `st.write(dict)` JSON render as black slabs. Roughly 8 of the worst symptoms below share this single root cause; fixing it is a 5-line config change. Second structural defect: hiding `stHeader` also hides the sidebar expand control → **crawled-apps list is unreachable on mobile** (verified: toggle exists in DOM but `display:none`, sidebar width 0). Third theme: the analysis charts carry real insight but leak signal — red rating line vs red spike bars collide, 22-language stacked area is unreadable rainbow, spike header count contradicts the rendered list.

---

## Findings

### P1 — broken or blocking

**P1.1 — No `[theme]` in config → dark base under light brand CSS (root cause of ~8 symptoms)**
- Symptoms observed: page captions invisible ("Enter an app name…", CLI hint, "Red bars = volume spike…", "Showing X of Y reviews", market-mix caption, worst-versions caption); "Granularity" label + Weekly/Monthly radio labels invisible; inactive tab label invisible, active tab red `#FF4B4B` (off-brand); dataframe = black table on lavender; all Altair charts = black canvases; expander body text invisible + expanded header black; `st.metric` values ("32.9%") near-white on lavender; checkbox/radio accent red not purple; `st.write(dict)` renders dark JSON block.
- Why it matters: this user scans for insight; half the explanatory text and all chart chrome is illegible. The captions are the parts that explain *how to read* the analysis (spike semantics, language-as-market caveat) — currently invisible.
- Fix (`.streamlit/config.toml`):
  ```toml
  [theme]
  base = "light"
  primaryColor = "#7C3AED"
  backgroundColor = "#F5F3FF"
  secondaryBackgroundColor = "#FFFFFF"
  textColor = "#1E1B4B"
  ```
  This flips dataframe/charts/expanders/metrics/captions to light, and turns every native accent (radio dot, checkbox tick, tab underline, toggle, focus ring, spinner) brand purple. Then *delete* now-redundant defensive CSS in `ui_styles.py` (selectbox text force-dark block, progress-text catch-alls) — less CSS fighting the framework. Note `.stCaption` selector in `ui_styles.py:78` doesn't match current Streamlit DOM (`[data-testid="stCaptionContainer"]`) — after theme fix it can go entirely.

**P1.2 — Sidebar cannot be reopened once collapsed; unreachable on mobile**
- `[data-testid="stHeader"] { display:none }` (`ui_styles.py:22`) removes the expand/collapse control. On ≤~1000px viewports Streamlit auto-collapses the sidebar → app list + sync buttons gone, no way back (verified in DOM: toggle present, header `display:none`, sidebar width 0).
- Why it matters: sidebar is the only navigation between crawled apps; on a laptop split-screen or phone the tool degrades to crawl-form-only.
- Fix (`ui_styles.py`): stop nuking the whole header. Keep hiding toolbar/menu/decoration but re-show the collapse control:
  ```css
  [data-testid="stHeader"] { display:block !important; background:transparent !important; height:auto !important; }
  [data-testid="stToolbar"], [data-testid="stDecoration"], #MainMenu { display:none !important; }
  [data-testid="stSidebarCollapsedControl"] { display:flex !important; color:#1E1B4B; }
  ```
  (Exact testids vary by Streamlit version — verify against the running version's DOM.)

**P1.3 — Dual-axis chart: signal collision + volume crushed**
- Observed: avg-rating line is red `#e45756`; spike bars are red `#d62728` — same hue encodes two unrelated meanings ("rating trend" and "anomalous volume"). Normal volume bars at 0.35 opacity on (currently dark) canvas are ghosts; the red line dominates so the eye reads "volume trend" from the *rating* line. No legend distinguishes line vs bars; right axis title "avg ⭐" renders as a rotated overlapping emoji glyph.
- Why it matters: this is the money chart — campaign/backlash detection. Miscolored encoding actively misleads (a rating dip reads like a volume crash).
- Fix (`analysis_ui.py`): rating line → brand purple `#7C3AED` (or dark indigo `#1E1B4B`), keep spikes red, normal bars `#A5B4FC` at 0.7 opacity; axis titles "reviews / period" and plain "avg rating" (no emoji in axis title — Vega renders emoji poorly rotated); add a 2-item legend or a one-line colored-key caption above the chart. All pure Altair encoding changes, ~30 min.

### P2 — significant friction

**P2.1 — Spike list contradicts its own header**
- Monthly granularity: header "Spike windows (20)" but list renders `spikes[-10:]` → 10 rows. User counts 10, header says 20 — trust hit on the exact feature meant to build trust in the data.
- Fix (`analysis_ui.py:50-52`): `st.subheader(f"Spike windows — latest {min(10, len(spikes))} of {len(spikes)}")`, or make the cutoff a "Show all" toggle.

**P2.2 — Spike tone encoded by emoji only; everything is ❓**
- All 10 visible Block Blast spikes show ❓ (mixed). 📈/🔥/❓ is not self-explanatory; the verdict sentence explaining it is *inside* the collapsed expander (and currently invisible per P1.1).
- Fix (`analysis_ui.py`): word badge in the label — `❓ Organic/mixed`, `🔥 Backlash?`, `📈 Campaign?` — so the collapsed list is scannable without expanding. Separately worth checking why tone thresholds never fire for a 4.4⭐-avg app (analytics, not UI — flagging only).

**P2.3 — Spike detail: `st.write(dict)` renders raw JSON code block**
- "Markets (lang)" shows `{ "en": 1361, "es": 651 … }` as a dark code block with copy icons — developer artifact in an analyst view.
- Fix (`analysis_ui.py:67`): render as markdown lines (`en — 1,361`) or tiny `st.dataframe`; same for versions/phrases columns which are currently unstyled comma strings.

**P2.4 — Market mix: 22-color stacked area is unreadable**
- Rainbow of 22 languages, legend clipped mid-list at chart edge, minor languages = 1px noise bands. The stated purpose ("which market is being pushed") can't be answered.
- Fix (`analysis_ui.py`): compute top-N langs (e.g. 8) by total volume, bucket rest as "other" before charting (small helper in analysis layer or inline groupby); explicit color scheme (`tableau10`); `alt.selection_point(fields=['lang'], bind='legend')` for click-to-highlight; height 280+. This is the one P2 that needs a touch of data code, still small.

**P2.5 — Selecting an app gives no above-fold feedback; results header shows package id**
- Clicking "Block Blast! (39603)" leaves the viewport visually unchanged (crawl form still dominates); results start below the fold. Reviews header says `Reviews — com.block.juggle (39603 total)` — package id, though the app name is in the DB.
- Fix (`app.py`): after selection render a compact "current app" strip above the tabs — app name + package id + review count + last-crawl date (all already available); pass app name to the reviews subheader; optionally wrap the crawl form in `st.expander("Crawl new app", expanded=False)` once results exist. Streamlit-native, no CSS needed.

**P2.6 — Reviews table: noisy defaults, no text search**
- Full timestamps (`2026-07-28 18:08:29`) eat width; 👍 column ~all zeros; no keyword filter — for review mining ("ads", "crash", "quảng cáo") the user must export to CSV first.
- Fix (`app.py`): `st.dataframe(column_config={"Date": st.column_config.DatetimeColumn(format="YYYY-MM-DD"), "Review": st.column_config.TextColumn(width="large"), "Rating": st.column_config.NumberColumn(format="%d ⭐")})`; add `st.text_input("Search in reviews")` → `df[df.content.str.contains(q, case=False, na=False)]` next to the star pills. Highest insight-per-hour item in this list.

**P2.7 — Star-filter pills: wrapping + raw counts + off-brand check**
- 5⭐ pill wraps "28779" onto a second line (uneven pill heights); counts lack thousands separators; checkmark is Streamlit red inside the purple pill (fixed by P1.1 primaryColor).
- Fix: format `f"{cnt:,}"` in `app.py:267`; in `ui_styles.py` add `white-space:nowrap` on pill label. Consider fewer stars in label (`5⭐ 28,779`) so all 5 pills stay one-line at laptop widths.

**P2.8 — No app management in sidebar; junk entry lives forever**
- "Block Blast! (158)" (clone/junk package) sits beside the real one; no delete, no package-id disambiguation, no last-synced info. At 10+ apps this list becomes unmanageable; identical display names would be indistinguishable.
- Fix (`app.py` + small `sqlite_store` delete helper): per-app "🗑" behind an expander or a "Manage apps" expander at sidebar bottom with delete buttons + confirm via `st.session_state` flag; show package id as second line (CSS: smaller, 60% opacity) and last-crawl date.

### P3 — polish

**P3.1 — "Search Reviews" button mislabeled** — it crawls (network, minutes), not searches. Rename "Crawl reviews" + keep spinner copy honest. (`app.py:114`)
**P3.2 — Weekly default over 3.5-year history = noise** — jagged line, spikes flagged on tiny baselines (57-review "spikes" in 2025-03). Default to Monthly, or auto: Monthly if span > 12 months; consider a date-range slider for the analysis tab. (`analysis_ui.py:26`)
**P3.3 — Version scatter red-yellow-green scale** — red-green is the classic colorblind trap and duplicates the y-axis (position already encodes score). Use `viridis`/`purbl` or single brand hue by size only; move "Worst versions" from invisible caption into 3 `st.metric`-style chips. (`analysis_ui.py:103`)
**P3.4 — Dev engagement metrics lack context** — three bare percentages; add one caption line ("healthy dev teams reply to most 1-2⭐") or delta vs other crawled apps later. (`analysis_ui.py:121`)
**P3.5 — Sidebar ↻ feedback** — spinner renders in main area while eyes are on sidebar; success toast appears after rerun at top. Consider `st.toast()` for sync results; disable button during sync happens implicitly. (`app.py:60-87`)
**P3.6 — Emoji tab labels** ("📋", "📈") render as low-contrast monochrome glyphs in this font stack; after theme fix they'll look fine, but plain "Reviews / Analysis" with the purple active underline is cleaner.
**P3.7 — Focus visibility** — custom pills/buttons rely on Streamlit default focus ring; after P1.1 the ring goes purple, acceptable. Verify `:focus-visible` outline isn't killed by `!important` rules for keyboard use.
**P3.8 — `prefers-reduced-motion`** — hover transforms/transitions are subtle; low priority, wrap `transform` hover in a media query if desired.
**P3.9 — Vietnamese rendering** — Inter import includes Vietnamese subset (Google Fonts serves `vietnamese` unicode-range automatically); multi-script review content (Arabic RTL, Cyrillic, Indonesian) renders correctly in the table per screenshots. No action. UI copy is English — fine for single VN operator, no change proposed.

---

## Quick wins (≤1h each)

1. Add `[theme]` block to `.streamlit/config.toml` (P1.1) — **the** fix; ~10 min + visual pass to prune redundant CSS.
2. Restore sidebar collapse control CSS (P1.2) — ~30 min incl. cross-viewport check.
3. Recolor rating line purple, fix axis titles, bump bar opacity (P1.3) — ~30 min.
4. Spike header count wording (P2.1) — 5 min.
5. Tone word-badges in expander labels (P2.2) — 15 min.
6. Markets dict → markdown lines (P2.3) — 15 min.
7. Thousands separators + `nowrap` pills (P2.7) — 15 min.
8. Rename crawl button (P3.1) — 2 min.
9. Monthly default granularity (P3.2 partial) — 5 min.
10. Date column format via `column_config` (P2.6 partial) — 15 min.
11. App-name-in-results-header + current-app strip (P2.5) — ~45 min.
12. Keyword search input on Reviews tab (P2.6) — ~45 min.

## Larger items

- Top-N + "other" language grouping w/ legend selection (P2.4) — touches analysis helpers, ~2-3h.
- Sidebar app management: delete/confirm + last-synced metadata (P2.8) — needs storage helper, ~half day.
- Date-range filter for analysis tab (P3.2 full) — ~2-3h.
- Spike tone threshold tuning so 📈/🔥 ever fire (analytics, not UI) — investigate separately.

## Unresolved questions

1. Streamlit version in use — exact `data-testid` names for header/collapse control vary across versions; P1.2 CSS must be verified against the running DOM.
2. Is dark base theme intentional for anyone (e.g. deployed Streamlit Cloud instance with different config)? Assumed no — brand CSS is unambiguously light.
3. Spike tone: is "all mixed" a threshold bug or genuinely mixed data for these two apps? Needs a look at `detect_spikes`/`spike_details` tone logic with a known backlash app.
4. Should the junk "Block Blast! (158)" entry be deleted from DB now, or kept as the test case for the app-management feature?
