"""Dravastudio brand styles and HTML components for the Streamlit app."""

# ── Dravastudio brand CSS ─────────────────────────────────────────────────────
DRAVASTUDIO_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

/* Base typography */
html, body, [class*="css"] {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif !important;
}

/* App background */
.stApp {
    background: #F5F3FF;
}

/* Hide Streamlit chrome — toolbar, header, footer */
#MainMenu, footer, header { visibility: hidden; }
[data-testid="stToolbar"] { display: none !important; }
[data-testid="stDecoration"] { display: none !important; }
[data-testid="stHeader"] { display: none !important; }

/* Content container — remove top gap left by hidden header */
.block-container {
    padding-top: 1.5rem !important;
    padding-bottom: 4rem !important;
    max-width: 1200px !important;
}

/* ── Sidebar ────────────────────────────────────────────────────────────────── */
[data-testid="stSidebar"] {
    background: #1E1B4B !important;
    border-right: none !important;
}
[data-testid="stSidebar"] * { color: #E0E7FF !important; }

[data-testid="stSidebar"] h1 {
    color: #C4B5FD !important;
    font-size: 0.75rem !important;
    font-weight: 600 !important;
    letter-spacing: 0.1em !important;
    text-transform: uppercase !important;
    margin-bottom: 0.75rem !important;
}

[data-testid="stSidebar"] .stButton > button {
    background: rgba(139, 92, 246, 0.12) !important;
    border: 1px solid rgba(139, 92, 246, 0.25) !important;
    color: #DDD6FE !important;
    border-radius: 8px !important;
    padding: 0.5rem 0.875rem !important;
    font-size: 0.825rem !important;
    font-weight: 400 !important;
    transition: all 0.2s !important;
    width: 100% !important;
    text-align: left !important;
    cursor: pointer !important;
}
[data-testid="stSidebar"] .stButton > button:hover {
    background: rgba(139, 92, 246, 0.28) !important;
    border-color: #7C3AED !important;
}

/* ── Headings ───────────────────────────────────────────────────────────────── */
h1 {
    font-size: 1.625rem !important;
    font-weight: 700 !important;
    color: #1E1B4B !important;
    letter-spacing: -0.02em !important;
    margin-bottom: 0.25rem !important;
}
h2, h3 {
    color: #1E1B4B !important;
    font-weight: 600 !important;
    letter-spacing: -0.01em !important;
}
.stCaption p {
    color: #6B7280 !important;
    font-size: 0.9rem !important;
}

/* ── Form labels ────────────────────────────────────────────────────────────── */
.stTextInput label,
.stSelectbox label,
.stMultiSelect label {
    color: #374151 !important;
    font-weight: 500 !important;
    font-size: 0.875rem !important;
}

/* ── Text input ─────────────────────────────────────────────────────────────── */
.stTextInput > div > div > input {
    border: 1.5px solid #DDD6FE !important;
    border-radius: 10px !important;
    background: #FFFFFF !important;
    color: #1E1B4B !important;
    font-size: 0.925rem !important;
    transition: border-color 0.2s, box-shadow 0.2s !important;
}
.stTextInput > div > div > input:focus {
    border-color: #7C3AED !important;
    box-shadow: 0 0 0 3px rgba(124, 58, 237, 0.12) !important;
}

/* ── Selectbox ──────────────────────────────────────────────────────────────── */
.stSelectbox > div > div {
    border: 1.5px solid #DDD6FE !important;
    border-radius: 10px !important;
    background: #FFFFFF !important;
}
/* Selected value text — force dark on white background */
.stSelectbox [data-baseweb="select"] *,
.stSelectbox [data-baseweb="select"] span,
.stSelectbox [data-baseweb="select"] div,
.stSelectbox [data-baseweb="select"] input,
[data-testid="stSelectbox"] * {
    color: #1E1B4B !important;
}
/* Dropdown popup — light theme */
[data-baseweb="popover"] [data-baseweb="menu"] {
    background: #FFFFFF !important;
    border: 1px solid #DDD6FE !important;
    border-radius: 10px !important;
    box-shadow: 0 8px 24px rgba(109,40,217,0.12) !important;
}
[data-baseweb="popover"] li {
    color: #1E1B4B !important;
    background: #FFFFFF !important;
}
[data-baseweb="popover"] li:hover,
[data-baseweb="popover"] li[aria-selected="true"] {
    background: #F5F3FF !important;
    color: #6D28D9 !important;
}

/* ── Primary button ─────────────────────────────────────────────────────────── */
.stButton > button[kind="primary"] {
    background: linear-gradient(135deg, #7C3AED, #5B21B6) !important;
    color: #FFFFFF !important;
    border: none !important;
    border-radius: 10px !important;
    padding: 0.625rem 1.5rem !important;
    font-weight: 600 !important;
    font-size: 0.925rem !important;
    box-shadow: 0 2px 8px rgba(124, 58, 237, 0.3) !important;
    transition: all 0.2s !important;
    cursor: pointer !important;
}
.stButton > button[kind="primary"]:hover {
    box-shadow: 0 4px 18px rgba(124, 58, 237, 0.45) !important;
    transform: translateY(-1px) !important;
}

/* ── Download buttons ───────────────────────────────────────────────────────── */
.stDownloadButton > button {
    background: #FFFFFF !important;
    border: 1.5px solid #DDD6FE !important;
    color: #4C1D95 !important;
    border-radius: 10px !important;
    font-weight: 500 !important;
    font-size: 0.9rem !important;
    transition: all 0.2s !important;
    cursor: pointer !important;
}
.stDownloadButton > button:hover {
    border-color: #7C3AED !important;
    background: #F5F3FF !important;
    color: #6D28D9 !important;
}

/* ── DataTable ──────────────────────────────────────────────────────────────── */
.stDataFrame {
    border-radius: 12px !important;
    overflow: hidden !important;
    border: 1px solid #EDE9FE !important;
    background: #FFFFFF !important;
}

/* ── Alerts ─────────────────────────────────────────────────────────────────── */
.stAlert { border-radius: 10px !important; }

/* ── Divider ────────────────────────────────────────────────────────────────── */
hr { border-color: #DDD6FE !important; margin: 1.5rem 0 !important; }

/* ── Progress bar ───────────────────────────────────────────────────────────── */
.stProgress > div > div > div {
    background: linear-gradient(90deg, #7C3AED, #8B5CF6) !important;
    border-radius: 4px !important;
}
</style>
"""

# ── Footer CSS (appended to main CSS block via app.py) ───────────────────────
FOOTER_CSS_EXTRA = """
<style>
.drava-footer {
    margin-top: 3rem;
    padding: 1.5rem 0 1rem;
    border-top: 1px solid #DDD6FE;
    display: flex;
    align-items: center;
    justify-content: space-between;
    flex-wrap: wrap;
    gap: 0.75rem;
}
.drava-footer-brand {
    font-size: 0.95rem;
    font-weight: 700;
    color: #1E1B4B;
    letter-spacing: -0.01em;
}
.drava-footer-brand span { color: #7C3AED; }
.drava-footer-links {
    display: flex;
    align-items: center;
    gap: 1.5rem;
    flex-wrap: wrap;
}
.drava-footer-links a {
    font-size: 0.825rem;
    color: #6B7280;
    text-decoration: none;
    transition: color 0.2s;
    display: flex;
    align-items: center;
    gap: 5px;
}
.drava-footer-links a:hover { color: #7C3AED; }
.drava-footer-copy {
    font-size: 0.775rem;
    color: #9CA3AF;
    width: 100%;
    margin-top: 0.25rem;
}
</style>
"""

# ── Brand header HTML ─────────────────────────────────────────────────────────
BRAND_HEADER_HTML = """
<div style="display:flex; align-items:center; justify-content:space-between;
            margin-bottom:1.75rem; padding-bottom:1.25rem; border-bottom:1px solid #EDE9FE;">
    <div style="display:flex; align-items:center; gap:14px;">
        <div style="width:44px; height:44px;
                    background:linear-gradient(135deg,#7C3AED,#5B21B6);
                    border-radius:12px; display:flex; align-items:center;
                    justify-content:center; flex-shrink:0;
                    box-shadow:0 4px 12px rgba(124,58,237,0.3);">
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none"
                 stroke="white" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                <circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/>
            </svg>
        </div>
        <div>
            <div style="font-size:1.25rem; font-weight:700; color:#1E1B4B;
                        letter-spacing:-0.02em; line-height:1.2;">
                Drava<span style="color:#7C3AED;">studio</span>
            </div>
            <div style="font-size:0.78rem; color:#6B7280; margin-top:2px;">
                Google Play Review Intelligence
            </div>
        </div>
    </div>
    <a href="https://drava.tech" target="_blank"
       style="font-size:0.8rem; color:#7C3AED; text-decoration:none; font-weight:500;
              border:1px solid #DDD6FE; padding:0.35rem 0.875rem; border-radius:8px;
              background:#FFFFFF; transition:all 0.2s;">
        drava.tech
    </a>
</div>
"""

FOOTER_HTML = """
<div class="drava-footer">
    <div class="drava-footer-brand">Drava<span>studio</span></div>
    <div class="drava-footer-links">
        <a href="mailto:dylannn08200@gmail.com">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor"
                 stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <rect width="20" height="16" x="2" y="4" rx="2"/>
                <path d="m22 7-8.97 5.7a1.94 1.94 0 0 1-2.06 0L2 7"/>
            </svg>
            dylannn08200@gmail.com
        </a>
        <a href="https://drava.tech" target="_blank">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor"
                 stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <circle cx="12" cy="12" r="10"/>
                <path d="M2 12h20M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/>
            </svg>
            drava.tech
        </a>
    </div>
    <div class="drava-footer-copy">© 2026 Dravastudio. All rights reserved.</div>
</div>
"""
