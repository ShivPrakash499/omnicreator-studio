#!/usr/bin/env python3
r"""
C:\OmniCreator_Studio\app.py
OmniCreator Studio — Streamlined 4-Stage Workflow with Full Dark/Light Mode Readability:
  Tab 1 (🏢 1. Channel Onboarding Hub):
    - Onboard channels across YouTube, Instagram, Facebook & X for ANY Niche and Regional/Language Audience.
    - 1-Click Channel Banner (2560x1440), Profile Picture (800x800), SEO Bio & Companion Google Vlog Builder.
  Tab 2 (🔍 2. Select Channel -> Trending Ideas & Packaging):
    - Select ONE Onboarded Channel first -> App automatically loads that channel's Niche, Region, Language & Voice.
    - Click to initiate Competitor Analysis & Trending Idea Generation for that channel's niche.
    - Pick a Trending Idea (or type manually) -> Generate High-CTR Titles & Photorealistic Thumbnails -> Render Draft.
  Tab 3 (🎞️ 3. Video Draft Player & Scene Prompt Editor):
    - Watch Long (16:9) & Short/Reel (9:16) videos and modify any scene via prompt.
  Tab 4 (🚀 4. Publish, SEO Description/Hashtags & Product/Excel Links):
    - Add custom Product Links, Affiliate URLs, Excel Sheets / Calculators & Vlog Links.
    - 1-Click Generate SEO Description, Hashtags, Chapters, Pinned Comment & Reel Captions with all links embedded.
    - Publish or Schedule across YouTube, Instagram, Facebook, X & Google Vlog.
"""
import datetime
import importlib
import json
import os
from pathlib import Path
import sys
import urllib.parse
import urllib.request

import streamlit as st
import streamlit.components.v1 as components

ROOT_DIR = Path(__file__).resolve().parent
if str(ROOT_DIR / "services") not in sys.path:
    sys.path.insert(0, str(ROOT_DIR / "services"))

import studio_engine

importlib.reload(studio_engine)

from studio_engine import (
    add_custom_niche_to_config,
    add_multi_platform_channel,
    analyze_competitors_and_market,
    authenticate_google_account_oauth,
    ensure_master_avatar_portrait,
    generate_channel_branding_and_google_vlog,
    generate_ctr_packaging,
    generate_draft_video_project,
    generate_publish_seo_and_links_bundle,
    get_host_identity,
    list_scheduled_posts,
    load_identities_config,
    load_niche_channels_registry,
    load_niches_config,
    modify_single_scene_with_prompt,
    publish_or_schedule_post,
    regenerate_studio_image_asset,
    search_trending_topics_in_niche,
    slugify,
)

st.set_page_config(
    page_title="OmniCreator Studio | Multi-Platform AI Video Engine",
    page_icon="🎬",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ============================================================================
# GOOGLE ACCOUNT AUTHENTICATION GATE (JWALASHIVA@GMAIL.COM / TRADING TITANS)
# ============================================================================
ALLOWED_GOOGLE_EMAILS = {
    e.strip().lower()
    for e in os.environ.get(
        "ALLOWED_GOOGLE_EMAILS",
        "jwalashiva@gmail.com,jwalasinghekcrore@gmail.com",
    ).split(",")
    if e.strip()
}
STUDIO_ACCESS_CODE = os.environ.get("STUDIO_ACCESS_CODE", "TradingTitans2026").strip()
GOOGLE_OAUTH_CLIENT_ID = os.environ.get("GOOGLE_OAUTH_CLIENT_ID", "").strip()
GOOGLE_OAUTH_CLIENT_SECRET = os.environ.get("GOOGLE_OAUTH_CLIENT_SECRET", "").strip()
GOOGLE_OAUTH_REDIRECT_URI = os.environ.get(
    "GOOGLE_OAUTH_REDIRECT_URI",
    "https://omnicreator-407429854548.asia-south1.run.app",
).strip()

# Handle Google OAuth 2.0 callback if `code` is in query_params
if "code" in st.query_params and GOOGLE_OAUTH_CLIENT_ID and GOOGLE_OAUTH_CLIENT_SECRET:
    try:
        oauth_code = st.query_params["code"]
        token_data = urllib.parse.urlencode(
            {
                "code": oauth_code,
                "client_id": GOOGLE_OAUTH_CLIENT_ID,
                "client_secret": GOOGLE_OAUTH_CLIENT_SECRET,
                "redirect_uri": GOOGLE_OAUTH_REDIRECT_URI,
                "grant_type": "authorization_code",
            }
        ).encode("utf-8")
        req = urllib.request.Request(
            "https://oauth2.googleapis.com/token",
            data=token_data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            tok = json.loads(resp.read().decode("utf-8"))
        u_req = urllib.request.Request(
            "https://www.googleapis.com/oauth2/v2/userinfo",
            headers={"Authorization": f"Bearer {tok['access_token']}"},
        )
        with urllib.request.urlopen(u_req, timeout=10) as u_resp:
            u_info = json.loads(u_resp.read().decode("utf-8"))
        verified_email = u_info.get("email", "").strip().lower()
        if verified_email in ALLOWED_GOOGLE_EMAILS:
            st.session_state["authenticated_google_user"] = verified_email
            st.query_params.clear()
            st.rerun()
        else:
            st.error(f"⛔ Access Denied: `{verified_email}` is not an authorized Google account for OmniCreator Studio.")
    except Exception as exc:
        st.warning(f"Google OAuth verification notice: {exc}")

if "authenticated_google_user" not in st.session_state:
    st.session_state["authenticated_google_user"] = None

if not st.session_state["authenticated_google_user"]:
    st.markdown(
        """
        <div style="max-width:520px;margin:60px auto;padding:32px;background:#111827;border:1px solid #334155;border-top:5px solid #00E676;border-radius:14px;color:#F8FAFC;font-family:'Segoe UI',sans-serif;">
            <h2 style="margin-top:0;color:#F8FAFC;">🔐 OmniCreator Studio — Google Account Sign-In</h2>
            <p style="color:#CBD5E1;font-size:0.96rem;">Restricted to authorized Google accounts (<b>jwalashiva@gmail.com</b> / <b>Trading Titans</b>).</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    login_col1, login_col2, login_col3 = st.columns([1, 2, 1])
    with login_col2:
        if GOOGLE_OAUTH_CLIENT_ID and GOOGLE_OAUTH_CLIENT_SECRET:
            auth_url = (
                "https://accounts.google.com/o/oauth2/v2/auth?"
                + urllib.parse.urlencode(
                    {
                        "client_id": GOOGLE_OAUTH_CLIENT_ID,
                        "redirect_uri": GOOGLE_OAUTH_REDIRECT_URI,
                        "response_type": "code",
                        "scope": "openid email profile",
                        "prompt": "select_account",
                    }
                )
            )
            st.link_button("🔵 Sign in with Google (OAuth 2.0)", auth_url, use_container_width=True, type="primary")
            st.divider()

        with st.form("google_owner_login_form"):
            login_email = st.text_input(
                "Authorized Google Account Email:",
                value="jwalashiva@gmail.com",
                placeholder="jwalashiva@gmail.com",
            )
            login_code = st.text_input(
                "Studio Security Passcode:",
                type="password",
                placeholder="Enter your studio passcode...",
            )
            submit_login = st.form_submit_button("🔓 Sign In with Google Account", type="primary", use_container_width=True)
            if submit_login:
                clean_email = login_email.strip().lower()
                if clean_email in ALLOWED_GOOGLE_EMAILS and login_code.strip() == STUDIO_ACCESS_CODE:
                    st.session_state["authenticated_google_user"] = clean_email
                    st.success(f"Welcome, {clean_email}!")
                    st.rerun()
                else:
                    st.error("⛔ Invalid Google Account email or Studio Security Passcode. Access is restricted to jwalashiva@gmail.com.")
    st.stop()

niches_cfg = load_niches_config()
identities_cfg = load_identities_config()
channels_reg = load_niche_channels_registry()
regions_tree = niches_cfg.get("regions_countries_languages", {})

# Build universal niche lookup
niche_map = {n["id"]: n for n in niches_cfg["niches"]}
niche_options = {
    n["id"]: f"[{n.get('category', 'Niche')}] {n['name']} ({n['rpm_usd']})"
    for n in niches_cfg["niches"]
}

def _load_portable_json(path: Path):
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    root_posix = ROOT_DIR.as_posix()

    def _norm(v):
        if isinstance(v, str) and ("OmniCreator_Studio" in v):
            idx = v.find("OmniCreator_Studio")
            suffix = v[idx + len("OmniCreator_Studio") :].replace("\\", "/")
            return root_posix + suffix
        if isinstance(v, dict):
            return {k: _norm(val) for k, val in v.items()}
        if isinstance(v, list):
            return [_norm(x) for x in v]
        return v

    return _norm(data)


# Pre-loaded default workspace & branding bundle for India channel Trading Titans
_default_proj = ROOT_DIR / "workspaces" / "wealth_investing" / "first-1-crore-math-trap-india"
_default_pkg = _load_portable_json(_default_proj / "stage3_ctr_packaging.json")
_default_draft = _load_portable_json(_default_proj / "stage4_draft_state.json")
_default_branding_file = (
    ROOT_DIR / "workspaces" / "wealth_investing" / "_channel_branding_trading-titans" / "channel_branding_bundle.json"
)
_default_branding = _load_portable_json(_default_branding_file)

default_custom_links = [
    {
        "category": "📊 Excel Sheet / Financial Calculator",
        "label": "2026 India Wealth & ₹1 Crore SIP Compounding Excel Calculator",
        "url": "https://docs.google.com/spreadsheets/d/18qtNEuFDFYHxkLS_u60jgREIoULcobqMP29qU4lF0b0/edit",
    },
    {
        "category": "🌐 Companion Google Vlog / Executive Report",
        "label": "Full Written Research Report & SEBI / RBI Filing Breakdown",
        "url": "https://trading-titans-wealth-investing-vlog.blogspot.com/",
    },
    {
        "category": "🛍️ Product / Recommended Tool Link",
        "label": "Recommended Nifty 50 Portfolio Tracker & Tax Shield Toolkit",
        "url": "https://tradingtitans.in/tools",
    },
]

for key, default in [
    ("ui_theme_mode", "🌙 Dark Mode (High Contrast)"),
    ("active_channel_index", 0),
    ("selected_niche_id", "wealth_investing"),
    ("selected_market_id", "india_metro_global_hybrid"),
    ("selected_modality", "HYBRID_AVATAR_KEYNOTE"),
    ("channel_branding_bundle", _default_branding),
    ("competitor_report", None),
    ("trending_topics_list", None),
    ("selected_topic", "Why Your First ₹1 Crore Is a Mathematical Trap (And How to Break It in India)"),
    ("ctr_package", _default_pkg),
    ("draft_state", _default_draft),
    ("project_dir", _default_proj if _default_proj.exists() else None),
    ("custom_links_list", default_custom_links),
    ("publish_seo_bundle", None),
]:
    if key not in st.session_state or st.session_state[key] is None:
        st.session_state[key] = default

if st.session_state.get("project_dir") == _default_proj:
    if _default_pkg:
        st.session_state["ctr_package"] = _default_pkg
    if _default_draft:
        st.session_state["draft_state"] = _default_draft

is_india_active = "india" in st.session_state.get("selected_market_id", "india_metro_global_hybrid").lower()
host_profile = get_host_identity(is_india=is_india_active)

# ============================================================================
# SIDEBAR: DARK/LIGHT MODE SWITCHER, ACTIVE CHANNEL & LOCKED IDENTITY DNA
# ============================================================================
with st.sidebar:
    st.markdown("### 🎬 OmniCreator Studio")
    st.caption(f"🟢 Signed in: `{st.session_state['authenticated_google_user']}`")
    if st.button("🔒 Lock / Sign Out", key="signout_sidebar_btn", use_container_width=True):
        st.session_state["authenticated_google_user"] = None
        st.rerun()
    ui_mode = st.radio(
        "🎨 Appearance (Dark / Light Mode):",
        options=["🌙 Dark Mode (High Contrast)", "☀️ Light Mode (High Contrast)"],
        index=0 if "Dark" in st.session_state["ui_theme_mode"] else 1,
        horizontal=True,
    )
    st.session_state["ui_theme_mode"] = ui_mode
    st.divider()

    st.markdown("#### 🔐 Active Google Account Login")
    saved_accounts = [a["email"] for a in channels_reg.get("google_accounts", [])]
    if "jwalashiva@gmail.com" not in saved_accounts:
        saved_accounts.insert(0, "jwalashiva@gmail.com")
    active_google_email = st.selectbox(
        "Connected Google Account:",
        options=saved_accounts,
        help="Switch between different Google accounts to manage separate niche channels and Google Vlogs.",
    )
    with st.expander("➕ Login / Add Another Google Account"):
        new_google_email = st.text_input("New Google Account Email:", placeholder="channel.owner@gmail.com")
        oauth_secret_file = st.file_uploader(
            "Optional: Upload Google OAuth `client_secret.json`",
            type=["json"],
            key="sidebar_oauth_upload",
        )
        if st.button("🔗 Connect & Save Google Account"):
            if new_google_email.strip():
                secret_bytes = oauth_secret_file.read() if oauth_secret_file else None
                authenticate_google_account_oauth(new_google_email.strip(), secret_bytes)
                st.success(f"Connected `{new_google_email.strip()}`!")
                st.rerun()

    st.divider()
    st.markdown("#### 🔒 Locked Channel Identity DNA")
    avatar_img_path = ensure_master_avatar_portrait(is_india=is_india_active)
    exact_flow_ref = ROOT_DIR / "assets" / "identity" / "jwalashiva_exact_reference.png"
    if is_india_active and exact_flow_ref.exists():
        av_c1, av_c2 = st.columns(2)
        with av_c1:
            st.image(str(exact_flow_ref), use_container_width=True, caption="Google Flow (Shiv Prakash)")
        with av_c2:
            st.image(str(avatar_img_path), use_container_width=True, caption="Studio Render (Shiv Prakash)")
    else:
        st.image(str(avatar_img_path), width=130, caption=host_profile["display_name"])
    st.caption(f"**Host:** `{host_profile['display_name']}`")
    st.caption(f"**Seed Lock:** `{host_profile['seed_lock_tag']}`")
    uploaded_face = st.file_uploader("Upload Custom Avatar/Face (.png/.jpg)", type=["png", "jpg", "jpeg"])
    if uploaded_face is not None:
        avatar_img_path.write_bytes(uploaded_face.read())
        st.success("Updated locked channel face reference!")

    st.divider()
    st.markdown("#### ☁️ Google Drive Backup & Cloud Hub")
    st.markdown(
        "- 📁 [**OmniCreator_Studio_Trading_Titans (Root)**](https://drive.google.com/drive/folders/1vJh5qXFnEnkEcetL2qXeyYh_FWMMNHR1)\n"
        "- 💻 [**01_Source_Code_and_Deployment**](https://drive.google.com/drive/folders/1fVGZeh4W3-ZbqrcWbMgnDgpdrpDW8yG-)\n"
        "- 🖼️ [**02_Channel_Branding_and_Avatars**](https://drive.google.com/drive/folders/1CnbPsQYheLs8ZZ9Ixsyvc2rIgoXSPCfF)\n"
        "- 🎬 [**03_Videos_Thumbnails_and_Reels**](https://drive.google.com/drive/folders/1Mt9LxiBaiVOO6zYpreN3Y1fD2jF6FFLQ)\n"
        "- 📝 [**04_Scripts_SEO_and_Blueprints**](https://drive.google.com/drive/folders/1rCYEbNtPDFmIvIQQoWHDc6ZGBNWfcnuU)"
    )

# ============================================================================
# DYNAMIC DARK & LIGHT MODE HIGH-CONTRAST CSS (100% READABLE IN BOTH MODES)
# ============================================================================
is_dark = "Dark" in st.session_state["ui_theme_mode"]
if is_dark:
    bg_app = "#0B0F19"
    bg_sidebar = "#111827"
    bg_card = "#161F33"
    bg_input = "#1E293B"
    text_main = "#F8FAFC"
    text_muted = "#CBD5E1"
    border_col = "#334155"
    accent_green = "#00E676"
    accent_cyan = "#00E5FF"
    accent_yellow = "#FFE600"
    badge_bg = "#1E293B"
else:
    bg_app = "#F8FAFC"
    bg_sidebar = "#EFF6FF"
    bg_card = "#FFFFFF"
    bg_input = "#FFFFFF"
    text_main = "#0F172A"
    text_muted = "#334155"
    border_col = "#CBD5E1"
    accent_green = "#059669"
    accent_cyan = "#0284C7"
    accent_yellow = "#D97706"
    badge_bg = "#E0F2FE"

st.markdown(
    f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;700&family=JetBrains+Mono:wght@400;600&display=swap');

    /* Global App & Sidebar Containers */
    .stApp, [data-testid="stAppViewContainer"], [data-testid="stHeader"] {{
        background-color: {bg_app} !important;
        color: {text_main} !important;
        font-family: 'DM Sans', sans-serif !important;
    }}
    [data-testid="stSidebar"] {{
        background-color: {bg_sidebar} !important;
        border-right: 1px solid {border_col} !important;
    }}
    [data-testid="stSidebar"] * {{
        color: {text_main} !important;
    }}

    /* Ensure all Typography, Labels & Markdown are High-Contrast */
    h1, h2, h3, h4, h5, h6, p, span, label, li, div[data-testid="stMarkdownContainer"] p,
    div[data-testid="stWidgetLabel"] p {{
        color: {text_main} !important;
    }}
    .stCaption, small {{
        color: {text_muted} !important;
    }}

    /* Inputs, Selectboxes, TextAreas, NumberInputs */
    div[data-baseweb="select"] > div,
    div[data-baseweb="input"] > div,
    div[data-baseweb="textarea"] > div,
    input, textarea {{
        background-color: {bg_input} !important;
        color: {text_main} !important;
        border-color: {border_col} !important;
    }}

    /* Expanders & Tabs */
    [data-testid="stExpander"] {{
        background-color: {bg_card} !important;
        border: 1px solid {border_col} !important;
        border-radius: 10px !important;
    }}
    button[data-baseweb="tab"] {{
        font-size: 0.98rem !important;
        font-weight: 700 !important;
        color: {text_main} !important;
    }}

    /* Custom Studio Cards & Step Headers — Explicit Background AND Foreground Text */
    .studio-banner-box {{
        background-color: {bg_card} !important;
        color: {text_main} !important;
        border: 1px solid {border_col} !important;
        border-left: 6px solid {accent_green} !important;
        padding: 16px 20px !important;
        border-radius: 10px !important;
        margin: 12px 0 !important;
        box-shadow: 0 2px 8px rgba(0,0,0,0.12);
    }}
    .studio-banner-box b, .studio-banner-box span, .studio-banner-box div {{
        color: {text_main} !important;
    }}
    .stage-pill {{
        background-color: {badge_bg} !important;
        color: {accent_cyan} !important;
        border: 1px solid {accent_cyan} !important;
        padding: 4px 14px !important;
        border-radius: 999px !important;
        font-size: 0.82rem !important;
        font-weight: 700 !important;
        display: inline-block !important;
        margin-bottom: 6px !important;
    }}
    .platform-card {{
        background-color: {bg_card} !important;
        color: {text_main} !important;
        border: 1px solid {border_col} !important;
        border-top: 4px solid {accent_cyan} !important;
        border-radius: 10px !important;
        padding: 12px 16px !important;
        margin-bottom: 10px !important;
        font-weight: 700 !important;
    }}
    </style>
    """,
    unsafe_allow_html=True,
)

# ============================================================================
# TOP HEADER & 4 CLEAN WORKFLOW TABS
# ============================================================================
st.title("🎬 OmniCreator Studio")
st.caption("1. Onboard Channels (YT/IG/FB/X)  →  2. Select Channel & Generate Trending Ideas / Packaging  →  3. Review & Edit Video Draft  →  4. Generate SEO/Links & Publish")

tab1, tab2, tab3, tab4 = st.tabs(
    [
        "🏢 1. Channel Onboarding Hub (YT / IG / FB / X)",
        "🔍 2. Select Channel → Trending Ideas, Titles & Thumbnails",
        "🎞️ 3. Video Draft Player & Scene Prompt Editor",
        "🚀 4. Publish, SEO Description/Hashtags & Product/Excel Links",
    ]
)

# ----------------------------------------------------------------------------
# TAB 1: CHANNEL ONBOARDING HUB (YOUTUBE, INSTAGRAM, FACEBOOK, X)
# ----------------------------------------------------------------------------
with tab1:
    st.markdown('<span class="stage-pill">STEP 1 OF WORKFLOW: ONBOARD & BRAND YOUR CHANNELS</span>', unsafe_allow_html=True)
    st.markdown(
        '<div class="studio-banner-box"><b>1. Onboard One or Many Channels Across YouTube, Instagram, Facebook & X</b><br/>'
        '<span>Assign any Niche (High-RPM, Regional, Entertainment, or Custom) and any Target Region/Language Audience to your channels. '
        'Then select any onboarded channel in <b>Tab 2</b> to automatically load its niche and start generating trending ideas!</span></div>',
        unsafe_allow_html=True,
    )

    with st.expander("➕ Need a Custom Niche Not in the List? Add Any Niche Here", expanded=False):
        cn_col1, cn_col2, cn_col3 = st.columns([2, 1, 1])
        with cn_col1:
            custom_niche_title = st.text_input("New Niche Name (e.g., Standup Comedy, Astrology, UPSC Prep, Anime, Fitness):")
        with cn_col2:
            custom_niche_rpm = st.text_input("Est. RPM / Value:", value="$6.00 - $15.00")
        with cn_col3:
            st.write("")
            if st.button("➕ Add Custom Niche", use_container_width=True):
                if custom_niche_title.strip():
                    new_nid = add_custom_niche_to_config(custom_niche_title.strip(), custom_niche_rpm.strip())
                    st.session_state["selected_niche_id"] = new_nid
                    st.success(f"Added niche `{custom_niche_title.strip()}` to the dropdown!")
                    st.rerun()

    # Onboarding Form
    ob_col1, ob_col2, ob_col3, ob_col4 = st.columns([2, 1.3, 2, 1.7])
    with ob_col1:
        onboarding_niche_id = st.selectbox(
            "1. Select Channel Niche (Any Niche):",
            options=list(niche_options.keys()),
            format_func=lambda k: niche_options[k],
            key="onboard_niche_select",
        )
        new_channel_name = st.text_input(
            "Channel / Page Name:",
            value="Trading Titans",
            help="Enter your channel name. You can add multiple channels in the same niche for different languages/regions.",
        )
    with ob_col2:
        onboarding_platform = st.selectbox(
            "2. Platform Section:",
            options=["YouTube", "Instagram", "Facebook", "X"],
        )
        new_channel_handle = st.text_input(
            "Channel Handle or URL:",
            value="@tradingtitantales",
        )
    with ob_col3:
        audience_presets = [
            "India • Hinglish (Hindi + English)",
            "India • English (India)",
            "India • Hindi (हिन्दी)",
            "India • Tamil (தமிழ்)",
            "India • Telugu (తెలుగు)",
            "India • Kannada (ಕನ್ನಡ)",
            "India • Malayalam (മലയാളം)",
            "India • Marathi (मराठी)",
            "India • Gujarati (ગુજરાતી)",
            "India • Bengali (বাংলা)",
            "India • Punjabi (ਪੰਜਾਬੀ)",
            "United States • English (US)",
            "United States • Spanish (US Hispanic / Español)",
            "United Kingdom • English (UK)",
            "UAE & MENA • Arabic & Global English",
        ]
        onboarding_audience = st.selectbox(
            "3. Target Audience (Country • Language):",
            options=audience_presets,
        )
        channel_google_email = st.text_input(
            "Google Account Login (for YouTube & Google Vlog):",
            value=active_google_email,
        )
    with ob_col4:
        st.write("")
        if st.button("➕ Add Channel to Onboarding Hub", use_container_width=True):
            add_multi_platform_channel(
                platform=onboarding_platform,
                niche_id=onboarding_niche_id,
                channel_name=new_channel_name,
                channel_handle_or_url=new_channel_handle,
                target_audience_label=onboarding_audience,
                channel_type="My Managed Channel",
                google_account_email=channel_google_email,
            )
            st.success(f"Onboarded `{new_channel_name}` under **{onboarding_platform}**!")
            st.rerun()

        trigger_branding = st.button(
            "🎨 1-Click Update Banner, Profile Pic, Bio & Google Vlog",
            type="primary",
            use_container_width=True,
        )

    if trigger_branding:
        with st.spinner(
            f"Generating 2560x1440 Banner, 800x800 Profile Pic (@jwalashiva), SEO Description, Hashtags & Google Vlog for '{new_channel_name}'..."
        ):
            bundle = generate_channel_branding_and_google_vlog(
                niche_id=onboarding_niche_id,
                target_market_id=st.session_state["selected_market_id"],
                channel_name=new_channel_name,
                channel_handle=new_channel_handle,
                google_account_email=channel_google_email,
                target_audience=onboarding_audience,
            )
            st.session_state["channel_branding_bundle"] = bundle
        st.success(
            f"Updated `{new_channel_name}` with 2560x1440 Banner, Profile Picture, SEO Bio, Hashtags & Companion Google Vlog (`{bundle['google_vlog_public_url']}`)!"
        )

    st.divider()
    st.subheader("🌐 Your Onboarded Channels Across YouTube, Instagram, Facebook & X")
    plat_channels = channels_reg.get("platform_channels", {})
    p_yt, p_ig, p_fb, p_x = st.columns(4)
    for p_col, p_name, p_icon in [
        (p_yt, "YouTube", "▶️ YouTube Channels"),
        (p_ig, "Instagram", "📸 Instagram Reels / Pages"),
        (p_fb, "Facebook", "📘 Facebook Pages"),
        (p_x, "X", "𝕏 X (Twitter) Accounts"),
    ]:
        with p_col:
            rows = plat_channels.get(p_name, [])
            st.markdown(f'<div class="platform-card">{p_icon} ({len(rows)})</div>', unsafe_allow_html=True)
            if rows:
                st.dataframe(
                    [
                        {
                            "Channel": r["channel_name"],
                            "Handle": r["channel_handle"],
                            "Niche": niche_map.get(r.get("niche_id", ""), {}).get("name", r.get("niche_id", ""))[:28],
                            "Target Audience": r.get("target_audience", "Global"),
                        }
                        for r in rows
                    ],
                    use_container_width=True,
                    hide_index=True,
                )
            else:
                st.caption(f"No {p_name} channels added yet.")

    branding_bundle = st.session_state.get("channel_branding_bundle")
    if branding_bundle:
        with st.expander(
            f"🖼️ Inspect Generated Channel Banner, Profile Picture, Bio, Hashtags & Google Vlog ({branding_bundle['channel_name']})",
            expanded=True,
        ):
            br_col1, br_col2 = st.columns([3, 1])
            with br_col1:
                st.markdown("##### 1. YouTube Channel Banner (`2560x1440` Safe-Zone Aligned)")
                if Path(branding_bundle["banner_2560x1440_path"]).exists():
                    st.image(branding_bundle["banner_2560x1440_path"], use_container_width=True)
                custom_banner_prompt = st.text_input(
                    "Optional Custom Banner Prompt / Style Override:",
                    placeholder="e.g., Mumbai BKC penthouse twilight studio with 3D gold TRADING TITANS wall logo (no @ handle)...",
                    key="custom_banner_prompt_input",
                )
                if st.button("🔄 Regenerate Channel Banner Image", key="regen_banner_btn", use_container_width=True):
                    st.session_state["banner_var_idx"] = st.session_state.get("banner_var_idx", 0) + 1
                    regenerate_studio_image_asset(
                        asset_type="banner",
                        out_png=Path(branding_bundle["banner_2560x1440_path"]),
                        custom_prompt=custom_banner_prompt,
                        variation_index=st.session_state["banner_var_idx"],
                        is_india=is_india_active,
                        aspect_ratio="16:9",
                    )
                    st.success(f"Regenerated Channel Banner (Variation #{st.session_state['banner_var_idx'] + 1})!")
                    st.rerun()
            with br_col2:
                st.markdown("##### 2. Profile Picture (`800x800`)")
                if Path(branding_bundle["profile_800x800_path"]).exists():
                    st.image(branding_bundle["profile_800x800_path"], width=180)
                if st.button("🔄 Regenerate Profile Picture", key="regen_profile_btn", use_container_width=True):
                    st.session_state["profile_var_idx"] = st.session_state.get("profile_var_idx", 0) + 1
                    regenerate_studio_image_asset(
                        asset_type="profile",
                        out_png=Path(branding_bundle["profile_800x800_path"]),
                        custom_prompt=custom_banner_prompt,
                        variation_index=st.session_state["profile_var_idx"],
                        is_india=is_india_active,
                        aspect_ratio="1:1",
                    )
                    st.success(f"Regenerated Profile Picture (Variation #{st.session_state['profile_var_idx'] + 1})!")
                    st.rerun()
                st.caption(f"**Google Login:** `{branding_bundle['google_account_email']}`")
                st.caption(f"**Vlog URL:** [{branding_bundle['google_vlog_public_url']}]({branding_bundle['google_vlog_public_url']})")

            seo_col1, seo_col2 = st.columns([3, 2])
            with seo_col1:
                st.text_area(
                    "Generated Channel SEO Bio / Description:",
                    value=branding_bundle["channel_description"],
                    height=150,
                    key="ch_desc_area_tab1",
                )
                st.code(" ".join(branding_bundle["hashtags"]), language="text")
            with seo_col2:
                vlog_html_path = Path(branding_bundle["google_vlog_local_html"])
                if vlog_html_path.exists():
                    st.download_button(
                        "⬇️ Download High-SEO Google Vlog HTML (Schema.org JSON-LD)",
                        data=vlog_html_path.read_bytes(),
                        file_name=vlog_html_path.name,
                        mime="text/html",
                    )
                    components.html(vlog_html_path.read_text(encoding="utf-8"), height=220, scrolling=True)

# ----------------------------------------------------------------------------
# TAB 2: SELECT ONE CHANNEL -> AUTO-DETECT NICHE & AUDIENCE ->
#        TRENDING IDEAS & COMPETITOR ANALYSIS -> TITLES & THUMBNAILS
# ----------------------------------------------------------------------------
with tab2:
    st.markdown(
        '<span class="stage-pill">STEP 2 OF WORKFLOW: SELECT CHANNEL → TRENDING IDEAS → TITLES & THUMBNAILS</span>',
        unsafe_allow_html=True,
    )

    # Gather all onboarded channels so user selects ONE channel first
    all_onboarded_channels = []
    for plat_key in ["YouTube", "Instagram", "Facebook", "X"]:
        for ch in channels_reg.get("platform_channels", {}).get(plat_key, []):
            ch_copy = dict(ch)
            ch_copy["platform"] = plat_key
            all_onboarded_channels.append(ch_copy)

    if not all_onboarded_channels:
        st.warning("Please onboard at least one channel in Tab 1 first.")
    else:
        st.markdown(
            '<div class="studio-banner-box"><b>Step 2.1: Select Your Target Channel First</b><br/>'
            '<span>The app automatically loads your selected channel\'s Niche, Regional Language Audience, and Voice DNA.</span></div>',
            unsafe_allow_html=True,
        )

        ch_display_labels = [
            f"[{c['platform']}] {c['channel_name']} ({c['channel_handle']})  —  Niche: {niche_map.get(c.get('niche_id', 'wealth_investing'), {}).get('name', c.get('niche_id', ''))}  |  Audience: {c.get('target_audience', 'Global')}"
            for c in all_onboarded_channels
        ]
        chosen_ch_label = st.selectbox(
            "👉 Select ONE Onboarded Channel to Start Analysis & Content Generation:",
            options=ch_display_labels,
            index=0,
        )
        chosen_ch_idx = ch_display_labels.index(chosen_ch_label)
        active_channel = all_onboarded_channels[chosen_ch_idx]

        # Automatically resolve Niche, Region, Country & Language from the selected channel!
        auto_niche_id = active_channel.get("niche_id", "wealth_investing")
        if auto_niche_id not in niche_map:
            auto_niche_id = "wealth_investing"
        st.session_state["selected_niche_id"] = auto_niche_id
        current_niche = niche_map[auto_niche_id]

        aud_raw = active_channel.get("target_audience", "India • Hinglish (Hindi + English)").replace("Pan-India Metro • ", "").replace("Pan-India • ", "").replace("Pan-India Metro", "India")
        aud_parts = [p.strip() for p in aud_raw.split("•") if p.strip()]
        is_india_ch = any(
            kw in aud_raw.lower()
            for kw in ["india", "hinglish", "hindi", "tamil", "telugu", "kannada", "malayalam", "marathi", "gujarati", "bengali", "punjabi"]
        )
        if is_india_ch:
            auto_region = "India"
            auto_country = "India"
            auto_lang = aud_parts[-1] if len(aud_parts) > 1 else "Hinglish (Hindi + English)"
            st.session_state["selected_market_id"] = "india_metro_global_hybrid"
            clean_aud_display = f"India • {auto_lang}"
            niche_default_topics = current_niche.get("india_topic_ideas", current_niche["default_topic_ideas"])
        else:
            auto_region = aud_parts[0] if len(aud_parts) > 0 else "United States & North America"
            auto_country = aud_parts[1] if len(aud_parts) > 1 else "United States"
            auto_lang = aud_parts[-1] if len(aud_parts) > 1 else "English (US)"
            st.session_state["selected_market_id"] = (
                "us_hispanic_spanish" if ("spanish" in auto_lang.lower() or "español" in auto_lang.lower()) else "tier1_us_uk_global"
            )
            clean_aud_display = f"{auto_country} • {auto_lang}"
            niche_default_topics = current_niche["default_topic_ideas"]

        # Show Auto-Loaded Channel Context Card + Optional Region/Language Override
        info_c1, info_c2, info_c3 = st.columns(3)
        with info_c1:
            st.markdown(
                f'<div class="studio-banner-box"><b>Selected Channel</b><br/><span>{active_channel["channel_name"]} ({active_channel["channel_handle"]})</span></div>',
                unsafe_allow_html=True,
            )
        with info_c2:
            st.markdown(
                f'<div class="studio-banner-box"><b>Auto-Detected Channel Niche</b><br/><span>{current_niche["name"]} ({current_niche["rpm_usd"]})</span></div>',
                unsafe_allow_html=True,
            )
        with info_c3:
            st.markdown(
                f'<div class="studio-banner-box"><b>Target Country & Language</b><br/><span>{clean_aud_display}</span></div>',
                unsafe_allow_html=True,
            )

        with st.expander("🌍 Optional: Refine Region, Country, Language or Visual Format for This Run", expanded=False):
            ref_c1, ref_c2, ref_c3, ref_c4 = st.columns(4)
            with ref_c1:
                reg_keys = list(regions_tree.keys())
                def_reg_idx = 0 if is_india_ch else (1 if len(reg_keys) > 1 else 0)
                sel_region = st.selectbox("Region:", options=reg_keys, index=def_reg_idx)
            with ref_c2:
                cnt_keys = list(regions_tree.get(sel_region, {}).keys())
                sel_country = st.selectbox("Country:", options=cnt_keys, index=0)
            with ref_c3:
                lng_keys = list(regions_tree.get(sel_region, {}).get(sel_country, {}).keys())
                sel_language = st.selectbox("Language:", options=lng_keys, index=0)
            with ref_c4:
                modality_options = {k: v["name"] for k, v in niches_cfg["visual_modalities"].items()}
                sel_mod = st.selectbox(
                    "Visual Format:",
                    options=list(modality_options.keys()),
                    format_func=lambda k: modality_options[k],
                )
                st.session_state["selected_modality"] = sel_mod

        # Step 2.2: Initiate Trending Idea Generation & Competitor Analysis
        st.markdown(
            '<div class="studio-banner-box"><b>Step 2.2: Initiate Trending Idea Generation & Competitor Analysis for This Channel</b></div>',
            unsafe_allow_html=True,
        )
        tr_search_col1, tr_search_col2 = st.columns([2, 1])
        with tr_search_col1:
            optional_kw = st.text_input(
                "Optional Keyword Filter for Trending Ideas (leave blank for top niche breakouts):",
                placeholder=f"e.g., 2026 trends in {current_niche['name'].split('.', 1)[-1].strip()}...",
            )
        with tr_search_col2:
            st.write("")
            run_analysis_btn = st.button(
                "🔥 Generate Trending Ideas & Analyze Niche Competitors",
                type="primary",
                use_container_width=True,
            )

        # Auto-refresh analysis whenever the selected channel changes OR user clicks the button!
        channel_switched = st.session_state.get("last_analyzed_channel_label") != chosen_ch_label
        if run_analysis_btn or channel_switched:
            with st.spinner(f"Analyzing {auto_country} channels and generating {auto_country} ({auto_lang}) trending ideas for {active_channel['channel_name']}..."):
                rep = analyze_competitors_and_market(
                    niche_id=auto_niche_id,
                    target_market_id=st.session_state["selected_market_id"],
                    custom_topic=optional_kw or niche_default_topics[0],
                    region_name=auto_region,
                    country_name=auto_country,
                    language_name=auto_lang,
                )
                st.session_state["competitor_report"] = rep
                st.session_state["trending_topics_list"] = search_trending_topics_in_niche(
                    niche_id=auto_niche_id,
                    region_name=auto_region,
                    country_name=auto_country,
                    language_name=auto_lang,
                    selected_channels=[c["channel"] for c in rep.get("top_competitors_analyzed", [])],
                    search_keyword=optional_kw,
                )
                st.session_state["last_analyzed_channel_label"] = chosen_ch_label
                st.session_state["selected_topic"] = niche_default_topics[0]

        rep = st.session_state.get("competitor_report")
        trends_list = st.session_state.get("trending_topics_list") or []

        if rep or trends_list:
            sub_t1, sub_t2 = st.tabs(
                [
                    f"🔥 Trending Video Ideas for {active_channel['channel_name']} ({len(trends_list)})",
                    "🏆 Analyzed Niche Competitors & Top-Performing Outlier Videos",
                ]
            )
            with sub_t1:
                if trends_list:
                    st.dataframe(trends_list, use_container_width=True, hide_index=True)
            with sub_t2:
                if rep:
                    st.dataframe(rep.get("top_competitors_analyzed", []), use_container_width=True, hide_index=True)
                    st.dataframe(rep.get("top_performing_videos", []), use_container_width=True, hide_index=True)

            top_videos = rep.get("top_performing_videos", []) if rep else []
            combined_choices = (
                [f"[🔥 TRENDING {t['search_velocity']}]  {t['topic_title']}" for t in trends_list]
                + [f"[🏆 OUTLIER VIDEO • {v['channel']} • {v['views']}]  {v['video_title']}" for v in top_videos]
            )
            if combined_choices:
                picked_idea_str = st.radio(
                    "👉 Select ONE Trending Idea or Top Video Below (or type manually in the box):",
                    options=combined_choices,
                    index=0,
                )
                default_idea_text = picked_idea_str.split("]  ", 1)[-1] if "]  " in picked_idea_str else picked_idea_str
            else:
                default_idea_text = current_niche["default_topic_ideas"][0]
        else:
            default_idea_text = st.session_state["selected_topic"]

        # Step 2.3: Generate High-CTR Titles & Photorealistic Thumbnails
        st.markdown(
            '<div class="studio-banner-box"><b>Step 2.3: Confirm Topic → Generate High-CTR Titles, Photorealistic Thumbnails & Render Video</b></div>',
            unsafe_allow_html=True,
        )
        final_topic_input = st.text_input(
            "✍️ Selected Video Topic (Editable — Select from Trending Ideas above or type any custom topic):",
            value=default_idea_text,
        )

        # Auto-regenerate CTR thumbnails if channel switched or if existing package belongs to another channel/avatar
        cur_pkg = st.session_state.get("ctr_package")
        needs_channel_pkg_sync = (
            cur_pkg is None
            or cur_pkg.get("channel_name") != active_channel["channel_name"]
            or (is_india_ch and cur_pkg.get("host_avatar") not in ["Shiv Prakash", "@jwalashiva"])
        )
        gen_ctr_btn = st.button(
            "🎯 Generate High-CTR Titles & Photorealistic Thumbnails (16:9 & 9:16)",
            type="primary",
            use_container_width=True,
        )
        if gen_ctr_btn or needs_channel_pkg_sync:
            proj_dir = ROOT_DIR / "workspaces" / auto_niche_id / slugify(final_topic_input)
            st.session_state["project_dir"] = proj_dir
            st.session_state["selected_topic"] = final_topic_input
            with st.spinner(f"Generating High-CTR Titles & Photorealistic Thumbnails ({'Shiv Prakash' if is_india_ch else 'Studio Host'}) for {active_channel['channel_name']}..."):
                pkg = generate_ctr_packaging(
                    auto_niche_id,
                    st.session_state["selected_market_id"],
                    final_topic_input,
                    st.session_state["selected_modality"],
                    proj_dir,
                    channel_name=active_channel["channel_name"],
                )
                st.session_state["ctr_package"] = pkg

        pkg = st.session_state.get("ctr_package")
        if pkg:
            st.divider()
            st.subheader(
                f"🎨 Generated High-CTR Titles & Photorealistic Thumbnails — {active_channel['channel_name']} (Host: {pkg.get('host_avatar', 'Shiv Prakash').replace('@jwalashiva', 'Shiv Prakash')})"
            )
            title_choices = [f"{t['title']}  [Est. CTR: {t['predicted_ctr']} - {t['style']}]" for t in pkg["title_options"]]
            selected_title_display = st.radio("Select Winning High-CTR Title:", options=title_choices)
            final_title = st.text_input("Editable Final Video Title:", value=selected_title_display.split("  [Est. CTR:")[0])

            custom_thumb_prompt = st.text_input(
                "Optional Custom Thumbnail / Cover Prompt Override:",
                placeholder="e.g., Shiv Prakash with 3D brass scale weighing ₹1 Crore vs 44% Tax Drag and giant yellow text THE ₹1 CRORE TRAP!...",
                key="custom_thumb_prompt_input",
            )
            tcol1, tcol2 = st.columns([3, 2])
            with tcol1:
                st.markdown("##### High-CTR YouTube Thumbnail (`16:9` Photorealistic Studio)")
                if Path(pkg["thumbnail_16x9_path"]).exists():
                    st.image(pkg["thumbnail_16x9_path"], use_container_width=True)
                if st.button("🔄 Regenerate 16:9 Thumbnail", key="regen_thumb_16x9_btn", use_container_width=True):
                    st.session_state["thumb_var_idx"] = st.session_state.get("thumb_var_idx", 0) + 1
                    regenerate_studio_image_asset(
                        asset_type="thumbnail_16x9",
                        out_png=Path(pkg["thumbnail_16x9_path"]),
                        custom_prompt=custom_thumb_prompt,
                        variation_index=st.session_state["thumb_var_idx"],
                        is_india=is_india_ch,
                        aspect_ratio="16:9",
                    )
                    st.success(f"Regenerated 16:9 Thumbnail (Variation #{st.session_state['thumb_var_idx'] + 1})!")
                    st.rerun()
            with tcol2:
                st.markdown("##### Instagram / Facebook Reel Cover (`9:16`)")
                if Path(pkg["reel_cover_9x16_path"]).exists():
                    st.image(pkg["reel_cover_9x16_path"], width=265)
                if st.button("🔄 Regenerate 9:16 Reel Cover", key="regen_reel_9x16_btn", use_container_width=True):
                    st.session_state["reel_var_idx"] = st.session_state.get("reel_var_idx", 0) + 1
                    regenerate_studio_image_asset(
                        asset_type="reel_9x16",
                        out_png=Path(pkg["reel_cover_9x16_path"]),
                        custom_prompt=custom_thumb_prompt,
                        variation_index=st.session_state["reel_var_idx"],
                        is_india=is_india_ch,
                        aspect_ratio="9:16",
                    )
                    st.success(f"Regenerated 9:16 Reel Cover (Variation #{st.session_state['reel_var_idx'] + 1})!")
                    st.rerun()

            dur_col1, dur_col2 = st.columns(2)
            with dur_col1:
                long_dur_choice = st.selectbox(
                    "🖥️ Long-Form Video Target Length (`16:9`):",
                    options=[
                        "Fast Draft Preview (~1 Min / 4 Scenes — Quick 15s Render)",
                        "Standard High-Retention Explainer (4-6 Min / 8 Scenes)",
                        "Mid-Roll Ad Revenue Maximizer (8-12 Min / 8+ Chapters)",
                    ],
                    index=0,
                )
            with dur_col2:
                short_dur_choice = st.selectbox(
                    "📱 Short / Reel Target Length (`9:16`):",
                    options=[
                        "Ultra-High Completion Short (35-45s / 3 Scenes)",
                        "Viral Short / Reel (45-60s / 4 Scenes — Recommended)",
                        "Extended Deep-Dive Reel (60-90s / 5 Scenes)",
                    ],
                    index=1,
                )

            if st.button("🎬 Approve & Render Full Long Video (16:9) + Short Reel (9:16)", type="primary", use_container_width=True):
                proj_dir = st.session_state["project_dir"]
                with st.spinner("Rendering Photorealistic Studio Scenes, Locked Voiceover & Stitching 16:9 + 9:16 Reel..."):
                    draft = generate_draft_video_project(
                        niche_id=auto_niche_id,
                        target_market_id=st.session_state["selected_market_id"],
                        topic=final_title,
                        visual_modality_key=st.session_state["selected_modality"],
                        project_dir=proj_dir,
                        long_duration_mode=long_dur_choice,
                        short_duration_mode=short_dur_choice,
                        channel_name=active_channel["channel_name"],
                    )
                    st.session_state["draft_state"] = draft
                    # Also auto-generate the initial Publish SEO & Links bundle for Tab 4
                    st.session_state["publish_seo_bundle"] = generate_publish_seo_and_links_bundle(
                        channel_info=active_channel,
                        video_title=final_title,
                        custom_links=st.session_state["custom_links_list"],
                        scenes=draft.get("scenes", []),
                    )
                st.success("✅ Videos Rendered! Open **Tab 3** to preview/edit scenes or **Tab 4** to add Product/Excel Links & Publish.")

# ----------------------------------------------------------------------------
# TAB 3: INTERACTIVE DRAFT PLAYER & SCENE-BY-SCENE PROMPT MODIFIER
# ----------------------------------------------------------------------------
with tab3:
    st.markdown('<span class="stage-pill">STEP 3 OF WORKFLOW: REVIEW VIDEO DRAFT & MODIFY SCENES BY PROMPT</span>', unsafe_allow_html=True)
    draft = st.session_state.get("draft_state")
    if not draft:
        st.info("Render your video draft in Tab 2 first.")
    else:
        vcol1, vcol2 = st.columns([3, 2])
        with vcol1:
            st.subheader("🖥️ Stitched Master Video (`16:9` YouTube / Facebook / X)")
            long_mp4 = draft["renders"]["long_16x9_mp4"]
            if Path(long_mp4).exists():
                st.video(long_mp4)
                st.caption(
                    f"File: `{long_mp4}`  |  Host Identity Lock: `{draft['host_identity']}`  |  Voice Lock: `{draft['locked_voice']}`"
                )
        with vcol2:
            st.subheader("📱 Stitched Vertical Reel (`9:16` IG Reel / FB Reel / YT Short)")
            reel_mp4 = draft["renders"]["reel_9x16_mp4"]
            if Path(reel_mp4).exists():
                st.video(reel_mp4)
                st.caption(f"File: `{reel_mp4}`")

        st.divider()
        st.subheader("✏️ Modify Any Scene With Prompts (Re-Renders Scene & Re-Stitches Video)")
        for sc in draft["scenes"]:
            sid = sc["scene_id"]
            with st.expander(
                f"Scene {sid:02d}: {sc['headline']}  [{sc['visual_type']}] ({sc.get('duration_sec', 15)}s)",
                expanded=(sid == 1),
            ):
                sc_col1, sc_col2 = st.columns([1, 2])
                with sc_col1:
                    if Path(sc["png_16x9"]).exists():
                        st.image(sc["png_16x9"], caption=f"Scene {sid:02d} (16:9 Frame)")
                with sc_col2:
                    new_vtype = st.selectbox(
                        f"Scene {sid:02d} Visual Format:",
                        options=list(niches_cfg["visual_modalities"].keys()),
                        index=list(niches_cfg["visual_modalities"].keys()).index(sc["visual_type"])
                        if sc["visual_type"] in niches_cfg["visual_modalities"]
                        else 0,
                        key=f"vtype_{sid}",
                    )
                    inc_av = st.checkbox(
                        "Show Locked Channel Avatar/Presenter Badge on this Scene",
                        value=sc.get("include_avatar_badge", True),
                        key=f"av_{sid}",
                    )
                    mod_prompt = st.text_area(
                        f"Prompt Modification / Script Override for Scene {sid:02d}:",
                        value=sc["narration"],
                        key=f"mod_{sid}",
                    )
                    if st.button(f"🔄 Regenerate Scene {sid:02d} & Re-Stitch Master Videos", key=f"btn_{sid}"):
                        with st.spinner(f"Updating Scene {sid:02d} & re-stitching 16:9 + 9:16 master videos..."):
                            updated_draft = modify_single_scene_with_prompt(
                                project_dir=Path(st.session_state["project_dir"]),
                                scene_id=sid,
                                user_modification_prompt=mod_prompt,
                                new_visual_type=new_vtype,
                                include_avatar=inc_av,
                            )
                            st.session_state["draft_state"] = updated_draft
                        st.success(f"Scene {sid:02d} updated and master videos re-stitched!")
                        st.rerun()

# ----------------------------------------------------------------------------
# TAB 4: PUBLISH SECTION — GENERATE DESCRIPTION, HASHTAGS, CHAPTERS &
#        INJECT CUSTOM LINKS (PRODUCT LINKS, EXCEL SHEETS, VLOGS)
# ----------------------------------------------------------------------------
with tab4:
    st.markdown(
        '<span class="stage-pill">STEP 4 OF WORKFLOW: ADD PRODUCT/EXCEL LINKS → GENERATE SEO DESCRIPTION & HASHTAGS → PUBLISH</span>',
        unsafe_allow_html=True,
    )
    draft = st.session_state.get("draft_state")
    pkg = st.session_state.get("ctr_package")

    # ========================================================================
    # 1. CUSTOM LINKS MANAGER (PRODUCT LINKS, EXCEL SHEETS, GOOGLE SHEETS, ETC.)
    # ========================================================================
    st.markdown(
        '<div class="studio-banner-box"><b>Step 4.1: Add Product Links, Excel Sheets, Calculators & Website URLs</b><br/>'
        '<span>Add any links below (Excel sheets, Google Sheets, Amazon/Affiliate product links, courses, or your Google Vlog). '
        'They will be automatically formatted into your YouTube Description, Reel Caption, Pinned Comment, and X Thread!</span></div>',
        unsafe_allow_html=True,
    )

    lnk_c1, lnk_c2, lnk_c3, lnk_c4 = st.columns([1.4, 1.8, 2.2, 1])
    with lnk_c1:
        new_link_cat = st.selectbox(
            "Link Type:",
            options=[
                "📊 Excel Sheet / Financial Calculator",
                "🛍️ Product / Affiliate Link",
                "🌐 Companion Google Vlog / Article",
                "🎓 Course / Lead Magnet / PDF",
                "💬 Community / Telegram / Discord",
            ],
        )
    with lnk_c2:
        new_link_label = st.text_input(
            "Link Call-to-Action Label:",
            placeholder="e.g., Download Free 2026 Excel Calculator Sheet",
        )
    with lnk_c3:
        new_link_url = st.text_input(
            "URL (Excel / Google Sheet / Product / Affiliate URL):",
            placeholder="https://docs.google.com/spreadsheets/... or https://amzn.to/...",
        )
    with lnk_c4:
        st.write("")
        if st.button("➕ Add Link to Video", use_container_width=True):
            if new_link_label.strip() and new_link_url.strip():
                st.session_state["custom_links_list"].append(
                    {
                        "category": new_link_cat,
                        "label": new_link_label.strip(),
                        "url": new_link_url.strip(),
                    }
                )
                st.success(f"Added link: `{new_link_label.strip()}`!")
                st.rerun()

    if st.session_state["custom_links_list"]:
        st.dataframe(st.session_state["custom_links_list"], use_container_width=True, hide_index=True)
        if st.button("🗑️ Clear Custom Links List"):
            st.session_state["custom_links_list"] = []
            st.rerun()

    # ========================================================================
    # 2. GENERATE SEO DESCRIPTION, HASHTAGS, CHAPTERS & CAPTIONS WITH LINKS
    # ========================================================================
    st.markdown(
        '<div class="studio-banner-box"><b>Step 4.2: Generate Multi-Platform SEO Description, Hashtags, Chapters & Pinned Comment</b></div>',
        unsafe_allow_html=True,
    )

    active_ch_for_pub = (
        all_onboarded_channels[0]
        if "all_onboarded_channels" in locals() and all_onboarded_channels
        else {"channel_name": "Apex Wealth Labs", "channel_handle": "@ApexWealthLabs", "niche_id": "wealth_investing", "target_audience": "Global"}
    )
    current_video_title = draft["topic"] if draft else st.session_state["selected_topic"]

    if st.button(
        "✨ Generate / Refresh Description, Hashtags, Chapters & Captions (Including All Product & Excel Sheet Links)",
        type="primary",
        use_container_width=True,
    ) or st.session_state.get("publish_seo_bundle") is None:
        st.session_state["publish_seo_bundle"] = generate_publish_seo_and_links_bundle(
            channel_info=active_ch_for_pub,
            video_title=current_video_title,
            custom_links=st.session_state["custom_links_list"],
            scenes=draft.get("scenes", []) if draft else [],
        )

    seo_bundle = st.session_state["publish_seo_bundle"]

    d_col1, d_col2 = st.columns(2)
    with d_col1:
        final_yt_desc = st.text_area(
            "▶️ YouTube & Facebook Long SEO Description (With Excel Sheets, Product Links & Timestamps):",
            value=seo_bundle["youtube_description"],
            height=230,
        )
        final_pinned = st.text_area(
            "📌 Auto-Generated Pinned Comment (High-Conversion Link Box):",
            value=seo_bundle["pinned_comment"],
            height=130,
        )
    with d_col2:
        final_ig_caption = st.text_area(
            "📸 Instagram & Facebook Reel Caption (With Product/Excel Links & Hashtags):",
            value=seo_bundle["ig_fb_reel_caption"],
            height=230,
        )
        final_x_thread = st.text_area(
            "𝕏 X (Twitter) Video Thread:",
            value=seo_bundle["x_thread"],
            height=130,
        )

    h_col1, h_col2 = st.columns(2)
    with h_col1:
        final_hashtags = st.text_input("🔥 Generated Viral Hashtags:", value=seo_bundle["hashtags_str"])
    with h_col2:
        final_seo_tags = st.text_input("🔍 YouTube Studio SEO Keyword Tags (Comma-Separated):", value=seo_bundle["seo_tags_str"])

    st.divider()

    # ========================================================================
    # 3. MULTI-PLATFORM PUBLISH & SCHEDULE DISPATCHER
    # ========================================================================
    st.markdown(
        '<div class="studio-banner-box"><b>Step 4.3: Publish Immediately or Schedule Across Platforms</b></div>',
        unsafe_allow_html=True,
    )
    pcol1, pcol2 = st.columns(2)
    with pcol1:
        pub_yt_long = st.checkbox("▶️ YouTube Long-Form (`16:9` 1080p + SEO Chapters + Links)", value=True)
        pub_yt_short = st.checkbox("⚡ YouTube Shorts (`9:16` Vertical Cut + Pinned Link)", value=True)
        pub_ig_reel = st.checkbox("📸 Instagram Reels (`9:16` Vertical Reel + Caption Links)", value=True)
    with pcol2:
        pub_fb_reel = st.checkbox("📘 Facebook Reels & Page Video (`9:16` Reel + `16:9` Page Post)", value=True)
        pub_x_video = st.checkbox("𝕏 X (Twitter) Video + Thread (`16:9` / `9:16`)", value=True)
        pub_google_vlog = st.checkbox(f"🌐 Companion Google Vlog Post ({active_google_email})", value=True)

    dcol1, dcol2, dcol3 = st.columns(3)
    with dcol1:
        sched_date = st.date_input("Publish Date:", value=datetime.date.today())
    with dcol2:
        sched_time = st.time_input("Publish Time (Peak Window):", value=datetime.time(18, 30))
    with dcol3:
        pub_mode = st.radio("Execution Mode:", options=["Schedule for Peak Window", "Publish Immediately"])

    if st.button("🚀 Dispatch / Schedule Video, Links & Descriptions Across Selected Platforms", type="primary", use_container_width=True):
        if not draft:
            st.error("Please render a draft video in Tab 2 first!")
        else:
            sched_iso = datetime.datetime.combine(sched_date, sched_time).isoformat()
            is_now = pub_mode == "Publish Immediately"
            title_val = current_video_title

            selected_jobs = []
            if pub_yt_long:
                selected_jobs.append(("YouTube Long-Form", "16:9 (1920x1080)", title_val, final_yt_desc, draft["renders"]["long_16x9_mp4"]))
            if pub_yt_short:
                selected_jobs.append(("YouTube Shorts", "9:16 (1080x1920)", f"{title_val} #Shorts", final_ig_caption, draft["renders"]["reel_9x16_mp4"]))
            if pub_ig_reel:
                selected_jobs.append(("Instagram Reels", "9:16 Reel (1080x1920)", title_val, final_ig_caption, draft["renders"]["reel_9x16_mp4"]))
            if pub_fb_reel:
                selected_jobs.append(("Facebook Reels / Page", "9:16 Reel (1080x1920)", title_val, final_ig_caption, draft["renders"]["reel_9x16_mp4"]))
            if pub_x_video:
                selected_jobs.append(("X (Twitter)", "16:9 / 9:16 Video", title_val, final_x_thread, draft["renders"]["long_16x9_mp4"]))
            if pub_google_vlog:
                vlog_file = (
                    st.session_state["channel_branding_bundle"]["google_vlog_local_html"]
                    if st.session_state.get("channel_branding_bundle")
                    else draft["renders"]["long_16x9_mp4"]
                )
                selected_jobs.append(
                    (
                        f"Google Vlog ({active_google_email})",
                        "SEO Article + Embedded 16:9 Video + Links",
                        title_val,
                        final_yt_desc,
                        vlog_file,
                    )
                )

            for plat, fmt_str, t_str, c_str, v_path in selected_jobs:
                publish_or_schedule_post(plat, fmt_str, t_str, c_str, v_path, sched_iso, publish_now=is_now)

            st.success(f"✅ Queued/Dispatched {len(selected_jobs)} deliverables with your custom Product & Excel Sheet links!")

    st.subheader("📅 Active Multi-Platform Publishing & Scheduling Queue")
    queue_rows = list_scheduled_posts()
    if queue_rows:
        st.dataframe(queue_rows, use_container_width=True, hide_index=True)
    else:
        st.caption("No posts scheduled yet.")
