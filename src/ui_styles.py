"""Shared styles for Mericrawler's light, table-first workspace."""

MERICRAWLER_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Be+Vietnam+Pro:wght@400;500;600;700&display=swap');
:root {
    --mc-canvas: #F7F8FA; --mc-surface: #FFFFFF; --mc-ink: #172033;
    --mc-muted: #596579; --mc-line: #E3E7EE; --mc-blue: #2563EB;
}
html, body, [data-testid="stApp"] { font-family: 'Be Vietnam Pro', sans-serif; color: var(--mc-ink); }
input, button, textarea, select, p, h1, h2, h3, [data-testid="stMetricValue"] { font-family: 'Be Vietnam Pro', sans-serif !important; }
.stApp { background: var(--mc-canvas); }
#MainMenu, footer { visibility: hidden; }
/* App management lives in Apps; reserve the entire workspace for content. */
[data-testid="stToolbar"] { visibility: hidden; pointer-events: none !important; }
[data-testid="stDecoration"] { display: none; }
[data-testid="stHeader"] { background: transparent; pointer-events: none; }
[data-testid="stSidebar"], [data-testid="stSidebarCollapsedControl"], [data-testid="stExpandSidebarButton"] {
    display: none !important;
}
.block-container { max-width: 1720px; padding: 1.75rem clamp(20px, 3vw, 56px) 3rem; }
h1 { font-size: clamp(32px, 2.4vw, 40px) !important; line-height: 1.25 !important; letter-spacing: -.035em; font-weight: 700 !important; }
h2 { font-size: 30px !important; line-height: 1.3 !important; font-weight: 600 !important; }
h3 { font-size: 26px !important; line-height: 1.35 !important; font-weight: 600 !important; }
[data-testid="stMarkdownContainer"] p { line-height: 1.6; }
[data-testid="stCaptionContainer"] { opacity: 1 !important; }
[data-testid="stCaptionContainer"] p { color: var(--mc-muted); font-size: 20px; line-height: 1.6; }
[data-testid="stWidgetLabel"] p { font-size: 22px; font-weight: 500; }
[data-testid="stButton"] button, [data-testid="stDownloadButton"] button,
[data-testid="stFormSubmitButton"] button {
    min-height: 52px; border-radius: 8px !important;
    transition: background-color 150ms, border-color 150ms;
}
button[kind="primary"], button[kind="primaryFormSubmit"] { background: var(--mc-blue); color: white; border-color: var(--mc-blue); }
button[kind="secondary"] { background: white; border-color: var(--mc-line); color: var(--mc-ink); }
button[kind="secondary"]:hover { background: #EFF6FF; border-color: #93B4EE; color: #1D4ED8; }
button:focus-visible, input:focus-visible, textarea:focus-visible, [role="button"]:focus-visible, [role="radio"]:focus-visible {
    outline: 3px solid #2563EB !important; outline-offset: 3px !important;
}
[data-testid="stMain"] input, [data-testid="stMain"] textarea { font-size: 22px !important; }
[data-baseweb="select"] > div, [data-baseweb="input"], [data-baseweb="textarea"] { background: #FFF; border-radius: 6px; }
[data-testid="stMain"] [data-baseweb="select"] > div,
[data-testid="stMain"] [data-baseweb="input"],
[data-testid="stMain"] [data-baseweb="textarea"],
[data-testid="stMain"] [data-testid="stTextInputRootElement"],
[data-testid="stMain"] [data-testid="stTextAreaRootElement"],
[data-testid="stMain"] [data-testid="stSelectbox"] [role="group"] {
    border: 1px solid #9AA9BD; background: #FFF; border-radius: 8px;
}
[data-testid="stMain"] [data-baseweb="select"] > div,
[data-testid="stMain"] [data-baseweb="input"],
[data-testid="stMain"] [data-testid="stTextInputRootElement"],
[data-testid="stMain"] [data-testid="stSelectbox"] [role="group"] { min-height: 52px; }
[data-testid="stForm"] { background: #FFF; border: 1px solid #C4CEDC; border-radius: 10px; padding: clamp(18px, 2vw, 28px); }
[data-testid="stVerticalBlockBorderWrapper"] > div { border-color: var(--mc-line); }
[data-testid="stVerticalBlock"]:has(> [data-testid="stLayoutWrapper"] > .stAltairChart) { min-width: 0; }
[data-testid="stMetric"] { min-height: 124px; padding: 1rem 1.1rem; background: #FFF; border: 1px solid var(--mc-line); border-radius: 6px; }
[data-testid="stMetricLabel"] { color: var(--mc-muted); }
[data-testid="stMetricValue"] { font-size: 1.8rem; font-variant-numeric: tabular-nums; }
[data-testid="stDataFrame"] { border: 1px solid var(--mc-line); border-radius: 6px; background: white; }
[data-testid="stRadio"] [role="radiogroup"] { gap: .5rem 1.2rem; flex-wrap: wrap; }
[data-testid="stRadio"] label { min-height: 52px; align-items: center; }
/* Keep native radio semantics and arrow-key navigation, with a tab-like surface. */
[role="radiogroup"]:is([aria-label="Workspace"], [aria-label="Explore"], [aria-label="Insights mode"]) {
    border-bottom: 1px solid #C4CEDC; gap: .35rem; padding-bottom: .2rem;
}
[role="radiogroup"]:is([aria-label="Workspace"], [aria-label="Explore"], [aria-label="Insights mode"]) label {
    padding: .4rem 1rem; border-bottom: 3px solid transparent; border-radius: 6px 6px 0 0;
}
[role="radiogroup"]:is([aria-label="Workspace"], [aria-label="Explore"], [aria-label="Insights mode"]) label:has(input:checked) {
    color: #1D4ED8; border-bottom-color: var(--mc-blue); background: #EAF2FF;
}
[role="radiogroup"]:is([aria-label="Workspace"], [aria-label="Explore"], [aria-label="Insights mode"]) label > div > div:first-child:not([data-testid]) { display: none; }
[data-testid="stRadio"] label:has(input:focus-visible) { outline: 3px solid #2563EB; outline-offset: 2px; }
[data-testid="stCheckbox"] label { white-space: nowrap; }
hr { border-color: var(--mc-line); margin: 1rem 0; }
.mericrawler-header { display:flex; flex-wrap:wrap; gap:.75rem; align-items:center; justify-content:space-between; padding:0 0 1.1rem; margin-bottom:.8rem; border-bottom:1px solid var(--mc-line); }
.mericrawler-brand { font-size:34px; font-weight:600; letter-spacing:-.045em; color:var(--mc-blue); }
.mericrawler-brand span { font-weight:400; }
.mericrawler-header-note { font-size:20px; color:var(--mc-muted); }
.mericrawler-footer { margin-top:2.5rem; padding-top:1rem; border-top:1px solid var(--mc-line); color:var(--mc-muted); font-size:.78rem; display:flex; flex-wrap:wrap; gap:.5rem 2rem; justify-content:space-between; }
.queue-status { padding:.4rem .75rem; border-radius:5px; font-size:.95rem; font-weight:600; }
.queue-status-info { background:#EAF2FF; color:#1D4ED8; }
.queue-status-neutral { background:#F1F5F9; color:#475569; }
.queue-status-warning { background:#FFF4DB; color:#854D0E; }
.queue-status-success { background:#DCFCE7; color:#166534; }
.queue-status-error { background:#FEE2E2; color:#991B1B; }
.queue-notice, .mericrawler-info, .mericrawler-success, .mericrawler-warning, .mericrawler-error { padding:.7rem .9rem; margin:.6rem 0 .3rem; border-left:3px solid #2563EB; background:#EFF6FF; color:#1E40AF; line-height:1.6; font-size:.9rem; overflow-wrap:anywhere; }
.queue-notice-warning, .mericrawler-warning { background:#FFFBEB; color:#854D0E; border-color:#D97706; }
.queue-notice-success, .mericrawler-success { background:#F0FDF4; color:#166534; border-color:#16A34A; }
.queue-notice-error, .mericrawler-error { background:#FEF2F2; color:#991B1B; border-color:#DC2626; }
/* Crawl: distinct input and monitoring surfaces; only the submit action is filled. */
[data-testid="stForm"]:has(.crawl-form-heading) {
    padding:1.5rem; border:1px solid #BDCCE2; border-top:4px solid var(--mc-blue); border-radius:10px;
    margin-bottom:1rem;
}
.crawl-section-heading { display:flex; align-items:flex-start; gap:1rem; padding-bottom:1rem; border-bottom:1px solid #D6DEE9; margin-bottom:.25rem; }
.crawl-section-heading h2 { font-size:30px !important; line-height:1.3; padding:0 !important; margin:0 0 .45rem !important; }
.crawl-section-heading p { font-size:1rem; line-height:1.6; color:var(--mc-muted); margin:0; max-width:65ch; }
.crawl-step { display:grid; place-items:center; flex:0 0 36px; height:36px; border-radius:6px; background:#DBEAFE; color:#1D4ED8; font-size:1.15rem; font-weight:600; }
.queue-panel-heading .crawl-step { background:#E8EDF4; color:#334155; }
[data-testid="stForm"]:has(.crawl-form-heading) [data-testid="stWidgetLabel"] p { font-size:1.05rem; font-weight:600; }
[data-testid="stForm"]:has(.crawl-form-heading) [data-baseweb="textarea"],
[data-testid="stForm"]:has(.crawl-form-heading) [data-baseweb="select"] > div,
[data-testid="stForm"]:has(.crawl-form-heading) [data-baseweb="input"],
[data-testid="stForm"]:has(.crawl-form-heading) [data-testid="stTextAreaRootElement"],
[data-testid="stForm"]:has(.crawl-form-heading) [data-testid="stSelectbox"] [role="group"] { border:1px solid #8998AE; border-radius:6px; background:#FCFDFF; }
[data-testid="stForm"]:has(.crawl-form-heading) [data-baseweb="select"] { font-size:22px; }
[data-testid="stForm"]:has(.crawl-form-heading) [data-testid="stFormSubmitButton"] button { min-height:52px; }
[data-testid="stForm"]:has(.crawl-form-heading) [data-testid="stFormSubmitButton"] p { font-size:1.1rem; font-weight:600; }
[data-testid="stForm"]:has(.crawl-form-heading) [data-testid="stCaptionContainer"] p { font-size:1rem; }
.queue-notice { font-size:1rem; padding:1rem; border-left-width:4px; }
.queue-guidance { padding:1.1rem 1.25rem; background:#EFF6FF; border:1px solid #BFDBFE; border-left:4px solid #2563EB; border-radius:6px; margin:.25rem 0 .75rem; }
.queue-guidance > strong { display:block; color:#1E40AF; font-size:1.15rem; margin-bottom:.35rem; }
.queue-guidance > p { color:#334155; font-size:1rem; line-height:1.6; max-width:85ch; margin:0; }
.queue-guidance-warning { background:#FFFBEB; border-color:#F3D79A; border-left-color:#D97706; }
.queue-guidance-warning > strong { color:#854D0E; }
/* The fragment adds one inner block. Support both Streamlit container layouts. */
:is([data-testid="stVerticalBlockBorderWrapper"]:has(.queue-panel-heading),
    [data-testid="stVerticalBlock"]:has(> [data-testid="stLayoutWrapper"] > [data-testid="stVerticalBlock"] > [data-testid="stElementContainer"] .queue-panel-heading)) {
    background:#FFF; border:1px solid #BDCCE2; border-top:4px solid #64748B; border-radius:10px; padding:1.5rem;
}
@media (max-width: 768px) {
    /* Keep both ends of a range readable instead of horizontally clipping dates. */
    [data-testid="stDateInputField"] { height:auto; min-height:52px; }
    [data-testid="stDateInputFieldsScroller"]:has(> span) {
        flex-direction:column; align-items:stretch; gap:2px; overflow:visible;
    }
    [data-testid="stDateInputFieldsScroller"]:has(> span) > span { display:none; }
    .block-container { padding:1.25rem 16px 2rem; }
    h2 { font-size:28px !important; }
    h3 { font-size:24px !important; }
    .mericrawler-header-note { width:100%; }
    [data-testid="stMain"] [data-testid="stHorizontalBlock"] { flex-wrap:wrap !important; gap:.75rem; }
    [data-testid="stMain"] [data-testid="stColumn"] { min-width:min(100%, 280px) !important; flex:1 1 280px !important; }
    [data-testid="stForm"], [data-testid="stForm"]:has(.crawl-form-heading) { padding:16px; }
    .crawl-section-heading { gap:.65rem; }
    .crawl-section-heading h2 { font-size:28px !important; }
    .queue-notice { font-size:1rem; }
}
@media (prefers-reduced-motion: reduce) {
    *, *::before, *::after { animation:none !important; transition:none !important; scroll-behavior:auto !important; }
}
</style>
"""
FOOTER_CSS_EXTRA = ""
BRAND_HEADER_HTML = """
<div class="mericrawler-header">
    <div class="mericrawler-brand">meri<span>crawler</span></div>
    <div class="mericrawler-header-note">Google Play · Review intelligence</div>
</div>
"""
FOOTER_HTML = """
<div class="mericrawler-footer"><span>Mericrawler · Review intelligence</span>
<span>Your saved reviews, in one workspace.</span></div>
"""


def info_box(msg: str) -> str:
    return f'<div class="mericrawler-info">{msg}</div>'


def success_box(msg: str) -> str:
    return f'<div class="mericrawler-success">{msg}</div>'


def warning_box(msg: str) -> str:
    return f'<div class="mericrawler-warning">{msg}</div>'


def error_box(msg: str) -> str:
    return f'<div class="mericrawler-error">{msg}</div>'
