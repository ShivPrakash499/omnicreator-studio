#!/usr/bin/env python3
r"""
C:\OmniCreator_Studio\app.py
TopperLab 3D (@TopperLab3D) — Clean-Slate Faceless 3D STEM & Exam Strategy Studio
  Step 1: Channel Brand Assets (2560x1440 Banner + 800x800 Logo) & Official YouTube / Meta OAuth Connect
  Step 2: High-School Syllabus / Strategy Idea Engine, Dual Script & Pure 3D Thumbnails
  Step 3: 3D Video Studio Player, Scene Editor & Google Flow (Veo 3.1) Motion Clip Integration
  Step 4: 1-Page Formula PDF / Sheet Link Injector & Direct YouTube / Reels Cloud Scheduler
"""
from __future__ import annotations

import datetime
import importlib
import json
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path

import streamlit as st

ROOT_DIR = Path(__file__).resolve().parent
if str(ROOT_DIR / "services") not in sys.path:
    sys.path.insert(0, str(ROOT_DIR / "services"))

import studio_engine

importlib.reload(studio_engine)

from studio_engine import (
    SCRIPT_MODEL_PRESETS,
    build_youtube_auth_url,
    check_gemini_api_key_health,
    exchange_youtube_auth_code,
    fetch_live_youtube_channel_videos,
    generate_dual_script_and_thumbnails,
    generate_student_seo_bundle,
    generate_topperlab_branding,
    generate_veo_clip_via_api,
    generate_viral_highschool_topics,
    get_active_script_model,
    get_gemini_api_key,
    get_youtube_oauth_status,
    has_vertex_adc,
    list_publish_queue,
    load_active_channel,
    load_meta_credentials,
    load_pillars_config,
    publish_or_schedule_deliverable,
    render_full_topperlab_project,
    resolve_workspace_path,
    save_active_channel,
    save_meta_credentials,
    save_youtube_client_secret,
    set_active_script_model,
    set_runtime_gemini_api_key,
    update_single_faceless_scene,
)

st.set_page_config(
    page_title="TopperLab 3D Studio | Faceless 3D STEM & Exam Engine",
    page_icon="🔬",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ============================================================================
# GOOGLE OWNER AUTHENTICATION GATE + YOUTUBE OAUTH CALLBACK HANDLER
# ============================================================================
ALLOWED_GOOGLE_EMAILS = {
    e.strip().lower()
    for e in os.environ.get(
        "ALLOWED_GOOGLE_EMAILS",
        "jwala4work@gmail.com,jwalashiva@gmail.com,jwalasinghekcrore@gmail.com",
    ).split(",")
    if e.strip()
}
VALID_PASSCODES = {
    os.environ.get("STUDIO_ACCESS_CODE", "TopperLab2026").strip(),
    "TopperLab2026",
    "TradingTitans2026",
}
GOOGLE_OAUTH_CLIENT_ID = os.environ.get("GOOGLE_OAUTH_CLIENT_ID", "").strip()
GOOGLE_OAUTH_CLIENT_SECRET = os.environ.get("GOOGLE_OAUTH_CLIENT_SECRET", "").strip()
def _detect_default_redirect_uri() -> str:
    env_uri = os.environ.get("GOOGLE_OAUTH_REDIRECT_URI", "").strip()
    if env_uri:
        return env_uri.rstrip("/")
    try:
        host = (st.context.headers.get("Host") or "").strip()
        if host and "localhost" not in host and "127.0.0.1" not in host:
            return f"https://{host}".rstrip("/")
        if host:
            return f"http://{host}".rstrip("/")
    except Exception:
        pass
    return "https://onebillionviews.streamlit.app" if os.name != "nt" else "http://localhost:8501"


DEFAULT_REDIRECT_URI = _detect_default_redirect_uri()

if "authenticated_google_user" not in st.session_state:
    st.session_state["authenticated_google_user"] = None

# Handle YouTube Data API OAuth callback (`?code=...&state=youtube_channel_connect`)
if "code" in st.query_params and st.query_params.get("state") == "youtube_channel_connect":
    try:
        redir = st.session_state.get("yt_redirect_uri_input", "")
        tok_info = exchange_youtube_auth_code(st.query_params["code"], redirect_uri=redir)
        st.session_state["authenticated_google_user"] = st.session_state["authenticated_google_user"] or "jwala4work@gmail.com"
        st.session_state["yt_oauth_flash"] = (
            f"✅ Connected YouTube Channel: {tok_info.get('connected_channel_title', 'TopperLab 3D')} "
            f"({tok_info.get('connected_channel_id', '')})"
        )
        st.query_params.clear()
        st.rerun()
    except Exception as exc:
        st.warning(f"YouTube OAuth callback notice: {exc}")

# Handle Google Sign-In OAuth callback for app gate
if "code" in st.query_params and GOOGLE_OAUTH_CLIENT_ID and GOOGLE_OAUTH_CLIENT_SECRET:
    try:
        token_data = urllib.parse.urlencode(
            {
                "code": st.query_params["code"],
                "client_id": GOOGLE_OAUTH_CLIENT_ID,
                "client_secret": GOOGLE_OAUTH_CLIENT_SECRET,
                "redirect_uri": DEFAULT_REDIRECT_URI,
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
            st.error(f"⛔ Access Denied: `{verified_email}` is not authorized.")
    except Exception as exc:
        st.warning(f"Google OAuth verification notice: {exc}")

if not st.session_state["authenticated_google_user"]:
    st.markdown(
        """
        <div style="max-width:540px;margin:55px auto;padding:30px;background:#0F172A;border:1px solid #334155;border-top:5px solid #00E5FF;border-radius:14px;color:#F8FAFC;font-family:'Segoe UI',sans-serif;">
            <h2 style="margin-top:0;color:#F8FAFC;">🔬 TopperLab 3D — Studio Sign-In</h2>
            <p style="color:#CBD5E1;font-size:0.95rem;">Dedicated Faceless 3D STEM & Exam Strategy Studio for <b>@TopperLab3D</b>.<br/>Restricted to owner Google accounts (<b>jwala4work@gmail.com</b> / <b>jwalashiva@gmail.com</b>).</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    _, login_col, _ = st.columns([1, 1.8, 1])
    with login_col:
        with st.form("topperlab_owner_login"):
            login_email = st.text_input("Authorized Google Email:", value="jwala4work@gmail.com")
            login_code = st.text_input(
                "Studio Passcode:",
                type="password",
                placeholder="TopperLab2026 (or your existing studio passcode)",
            )
            if st.form_submit_button("🔓 Unlock TopperLab 3D Studio", type="primary", use_container_width=True):
                clean_email = login_email.strip().lower()
                if clean_email in ALLOWED_GOOGLE_EMAILS and login_code.strip() in VALID_PASSCODES:
                    st.session_state["authenticated_google_user"] = clean_email
                    st.rerun()
                else:
                    st.error("⛔ Invalid email or passcode. Default passcode: `TopperLab2026`.")
    st.stop()

# ============================================================================
# LOAD CLEAN SINGLE-CHANNEL CONFIG & SESSION DEFAULTS
# ============================================================================
channel_cfg = load_active_channel()
pillars_cfg = load_pillars_config()
pillars_by_id = {p["id"]: p for p in pillars_cfg["pillars"]}

def _load_portable_json(path: Path):
    if not path.exists():
        return None
    raw_obj = json.loads(path.read_text(encoding="utf-8"))

    def _fix(val):
        if isinstance(val, str) and ("workspaces" in val or "assets" in val):
            resolved = resolve_workspace_path(val)
            return resolved.as_posix()
        elif isinstance(val, dict):
            return {k: _fix(v) for k, v in val.items()}
        elif isinstance(val, list):
            return [_fix(x) for x in val]
        return val

    return _fix(raw_obj)


# Pre-load flagship sample project if already rendered on disk
_sample_slug = "why-spinning-gyroscopes-defy-gravity-rotational-motion-t"
_sample_dir = ROOT_DIR / "workspaces" / "topperlab_3d" / _sample_slug
_preloaded_bp = _load_portable_json(_sample_dir / "topperlab_blueprint.json")
_preloaded_draft = _load_portable_json(_sample_dir / "topperlab_draft_state.json")

for k, default_val in [
    ("ui_theme_mode", "🌙 Dark Lab Mode"),
    ("script_model_id", get_active_script_model()),
    ("voice_mode", channel_cfg.get("default_voice_mode", "Clean Indian-English (en-IN)")),
    ("visual_theme_key", channel_cfg.get("default_visual_theme", "3D_DARK_LAB_CUTAWAY")),
    ("selected_pillar_id", "3d_concept_visualizer"),
    ("selected_exam_track", pillars_cfg["exam_tracks"][0]),
    ("generated_topics", pillars_cfg["pillars"][0]["starter_topics"]),
    (
        "selected_topic_title",
        "Why Spinning Gyroscopes Defy Gravity — Rotational Motion & Torque Explained in 3D",
    ),
    ("current_blueprint", _preloaded_bp),
    ("current_draft", _preloaded_draft),
    ("resource_links", list(channel_cfg.get("default_resource_links", []))),
    ("seo_bundle", None),
    ("yt_redirect_uri_input", DEFAULT_REDIRECT_URI),
]:
    if k not in st.session_state or st.session_state[k] is None:
        st.session_state[k] = default_val

if st.session_state.get("yt_oauth_flash"):
    st.toast(st.session_state.pop("yt_oauth_flash"))

branding_assets = generate_topperlab_branding(force_regenerate=False)
yt_status = get_youtube_oauth_status()
meta_creds = load_meta_credentials()

# ============================================================================
# SIDEBAR: SINGLE-CHANNEL CONTROL BAR (100% FACELESS — ZERO MULTI-CHANNEL CLUTTER)
# ============================================================================
with st.sidebar:
    logo_file = resolve_workspace_path(branding_assets["logo_path"])
    if logo_file.exists():
        _, c_logo, _ = st.columns([0.5, 2, 0.5])
        with c_logo:
            st.image(str(logo_file), use_container_width=True)

    st.markdown(f"### 🔬 {channel_cfg['channel_name']}")
    st.caption(
        f"**Handle:** `{channel_cfg['channel_handle']}`  \n"
        f"🔗 [**Open Live YouTube Channel**]({channel_cfg['youtube_channel_url']})"
    )

    if yt_status.get("connected"):
        st.success(f"🟢 YouTube API Connected (`{yt_status.get('channel_title', 'TopperLab 3D')}`)")
    else:
        st.info("⚪ YouTube API: Not Authorized Yet (Connect in Step 1)")

    model_keys = list(SCRIPT_MODEL_PRESETS.keys())
    selected_model = st.selectbox(
        "🧠 Gemini 4 Brain:",
        options=model_keys,
        format_func=lambda mk: SCRIPT_MODEL_PRESETS[mk],
        index=model_keys.index(st.session_state["script_model_id"])
        if st.session_state["script_model_id"] in model_keys
        else 0,
    )
    st.session_state["script_model_id"] = selected_model
    set_active_script_model(selected_model)

    active_gem_key = get_gemini_api_key()
    vertex_ready = has_vertex_adc()
    key_fp = (
        f"m:{selected_model}|v:{vertex_ready}|k:{len(active_gem_key)}:{active_gem_key[:6]}:{active_gem_key[-4:]}"
        if active_gem_key
        else f"m:{selected_model}|v:{vertex_ready}|empty"
    )
    if st.session_state.get("gemini_health_fp") != key_fp:
        st.session_state["gemini_health_cache"] = check_gemini_api_key_health(
            None if vertex_ready else active_gem_key,
            preferred_model=selected_model,
        )
        st.session_state["gemini_health_fp"] = key_fp
    gem_health = st.session_state["gemini_health_cache"]

    if gem_health.get("ok"):
        st.success(f"🟢 {gem_health['summary']}")
    else:
        st.warning(f"🟠 {gem_health['summary']}")

    exp_label = "☁️ Gemini 4 & Vertex AI Credits" if gem_health.get("ok") else "🔑 Gemini / Vertex AI Setup"
    with st.expander(exp_label, expanded=not gem_health.get("ok")):
        st.caption(gem_health.get("detail", ""))
        new_gem_key = st.text_input(
            "Optional Override API Key (`AIza...`):",
            type="password",
            placeholder="Uses Vertex AI Cloud Credits automatically when VERTEX_ADC_JSON is set",
        )
        if st.button("💾 Apply & Verify Key Override", use_container_width=True) and new_gem_key.strip():
            set_runtime_gemini_api_key(new_gem_key.strip())
            st.session_state["gemini_health_fp"] = ""
            st.rerun()

    st.divider()
    st.markdown("#### 🎙️ Voice & 3D Style Lock")
    voice_options = list(channel_cfg["voice_presets"].keys())
    st.session_state["voice_mode"] = st.selectbox(
        "Narration Voice Mode:",
        options=voice_options,
        index=voice_options.index(st.session_state["voice_mode"])
        if st.session_state["voice_mode"] in voice_options
        else 0,
    )

    theme_keys = list(channel_cfg["visual_themes"].keys())
    st.session_state["visual_theme_key"] = st.selectbox(
        "Faceless 3D Visual Style:",
        options=theme_keys,
        format_func=lambda tk: channel_cfg["visual_themes"][tk]["label"],
        index=theme_keys.index(st.session_state["visual_theme_key"])
        if st.session_state["visual_theme_key"] in theme_keys
        else 0,
    )

    st.divider()
    st.session_state["ui_theme_mode"] = st.radio(
        "🎨 Studio Theme:",
        options=["🌙 Dark Lab Mode", "☀️ Clean Light Mode"],
        horizontal=True,
    )
    st.caption(f"Signed in as `{st.session_state['authenticated_google_user']}`")
    if st.button("🔒 Sign Out", use_container_width=True):
        st.session_state["authenticated_google_user"] = None
        st.rerun()

# ============================================================================
# HIGH-CONTRAST DARK & LIGHT CSS
# ============================================================================
is_dark = "Dark" in st.session_state["ui_theme_mode"]
bg_app = "#090D16" if is_dark else "#F8FAFC"
bg_side = "#0F172A" if is_dark else "#EFF6FF"
bg_card = "#131C2E" if is_dark else "#FFFFFF"
bg_inp = "#1E293B" if is_dark else "#FFFFFF"
txt_main = "#F8FAFC" if is_dark else "#0F172A"
txt_muted = "#94A3B8" if is_dark else "#475569"
bdr_col = "#2D3B55" if is_dark else "#CBD5E1"
accent_cyan = "#00E5FF" if is_dark else "#0284C7"
accent_gold = "#FACC15" if is_dark else "#D97706"

st.markdown(
    f"""
    <style>
    .stApp, [data-testid="stAppViewContainer"], [data-testid="stHeader"] {{
        background-color: {bg_app} !important;
        color: {txt_main} !important;
    }}
    [data-testid="stSidebar"] {{
        background-color: {bg_side} !important;
        border-right: 1px solid {bdr_col} !important;
    }}
    [data-testid="stSidebar"] * {{ color: {txt_main} !important; }}
    h1, h2, h3, h4, h5, p, span, label, li, div[data-testid="stWidgetLabel"] p {{
        color: {txt_main} !important;
    }}
    div[data-baseweb="select"] > div, div[data-baseweb="input"] > div,
    div[data-baseweb="textarea"] > div, input, textarea {{
        background-color: {bg_inp} !important;
        color: {txt_main} !important;
        border-color: {bdr_col} !important;
    }}
    .lab-card {{
        background-color: {bg_card} !important;
        border: 1px solid {bdr_col} !important;
        border-left: 5px solid {accent_cyan} !important;
        padding: 15px 18px !important;
        border-radius: 10px !important;
        margin-bottom: 14px !important;
    }}
    .step-badge {{
        background: {bg_card};
        color: {accent_cyan} !important;
        border: 1px solid {accent_cyan};
        padding: 3px 12px;
        border-radius: 999px;
        font-size: 0.8rem;
        font-weight: 700;
        display: inline-block;
        margin-bottom: 6px;
    }}
    </style>
    """,
    unsafe_allow_html=True,
)

# ============================================================================
# HEADER & 4 CLEAN LINEAR WORKFLOW TABS
# ============================================================================
st.title(f"🔬 {channel_cfg['channel_name']} — Faceless 3D Studio")
st.caption(
    f"**Cohort:** {channel_cfg['cohort']}  •  **Default Narration:** `{st.session_state['voice_mode']}`  •  "
    f"**100% Faceless 3D Pipeline (Long `16:9` + Shorts/Reels `9:16`)**"
)

tab1, tab2, tab3, tab4 = st.tabs(
    [
        "🎨 Step 1: Brand & YouTube/Reels Connect",
        "🧪 Step 2: Topic, Dual Script & 3D Thumbnail",
        "🎞️ Step 3: 3D Video Studio & Google Flow Clips",
        "🚀 Step 4: Formula Sheets & Cloud Schedule",
    ]
)

# ============================================================================
# STEP 1: BRANDING ASSETS & OFFICIAL OAUTH / GRAPH API CONNECTION
# ============================================================================
with tab1:
    st.markdown('<span class="step-badge">STEP 1 • ONE-TIME CHANNEL BRANDING & API SETUP</span>', unsafe_allow_html=True)
    st.markdown(
        '<div class="lab-card"><b>Ready-to-Upload Branding for @TopperLab3D + Official OAuth Publishing Setup</b><br/>'
        'Download your custom 3D Banner & Profile Badge below to upload into YouTube Studio (<i>Customise channel</i>), '
        'and connect your Google OAuth <code>client_secret.json</code> once to enable direct API uploads & cloud scheduling.</div>',
        unsafe_allow_html=True,
    )

    bcol1, bcol2 = st.columns([2.2, 1])
    with bcol1:
        st.subheader("🖼️ YouTube Safe-Zone Banner (`2560 x 1440`)")
        bpath = resolve_workspace_path(branding_assets["banner_path"])
        if bpath.exists():
            st.image(str(bpath), use_container_width=True)
            st.download_button(
                "⬇️ Download 2560x1440 YouTube Banner (.jpg)",
                data=bpath.read_bytes(),
                file_name="TopperLab3D_YouTube_Banner_2560x1440.jpg",
                mime="image/jpeg",
                use_container_width=True,
            )
    with bcol2:
        st.subheader("🔵 3D Profile Icon (`800 x 800`)")
        lpath = resolve_workspace_path(branding_assets["logo_path"])
        if lpath.exists():
            st.image(str(lpath), width=230)
            st.download_button(
                "⬇️ Download 800x800 Channel Logo (.png)",
                data=lpath.read_bytes(),
                file_name="TopperLab3D_Logo_800x800.png",
                mime="image/png",
                use_container_width=True,
            )

    with st.expander("🔄 Regenerate Banner / Logo With Custom 3D Prompt or Copy Channel SEO Bio"):
        rc1, rc2 = st.columns(2)
        with rc1:
            custom_b_p = st.text_area("Custom 3D Banner Prompt (optional):", height=80)
            custom_l_p = st.text_area("Custom 3D Logo Prompt (optional):", height=80)
            if st.button("✨ Regenerate Pure 3D Branding Assets", use_container_width=True):
                with st.spinner("Rendering pure 3D branding via Nano Banana / Imagen 3..."):
                    generate_topperlab_branding(custom_b_p, custom_l_p, force_regenerate=True)
                st.success("Updated 3D branding assets!")
                st.rerun()
        with rc2:
            st.text_area("Copy-Ready YouTube Channel Description (`Customise channel -> Basic info`):", value=branding_assets["seo_description"], height=130)
            st.text_input("Copy-Ready YouTube Channel Keywords:", value=branding_assets["channel_keywords"])

    st.divider()
    st.subheader("🔑 Connect Official YouTube Data API v3 (Direct Upload + Cloud Scheduling)")
    st.caption(
        "Tip: In YouTube Studio → **Settings → Channel → Feature eligibility → 2. Intermediate features**, click the small dropdown arrow and verify your phone OTP once so YouTube allows custom API thumbnails!"
    )

    yt_c1, yt_c2 = st.columns(2)
    with yt_c1:
        uploaded_secret = st.file_uploader("1. Upload Google Cloud OAuth `client_secret.json`:", type=["json"])
        if uploaded_secret is not None:
            try:
                save_youtube_client_secret(uploaded_secret.read())
                st.success("✅ Saved `client_secret.json` securely in `config/credentials/` (gitignored)!")
                yt_status = get_youtube_oauth_status()
            except Exception as exc:
                st.error(f"Could not parse JSON: {exc}")

        redir_val = st.text_input(
            "Authorized Redirect URI (must match Google Cloud Console):",
            value=st.session_state["yt_redirect_uri_input"],
        )
        st.session_state["yt_redirect_uri_input"] = redir_val

    with yt_c2:
        auth_url = build_youtube_auth_url(redirect_uri=redir_val)
        if auth_url:
            st.link_button(
                "🔵 2. Sign In & Authorize @TopperLab3D (Google Login + OTP Popup)",
                auth_url,
                type="primary",
                use_container_width=True,
            )
            manual_code = st.text_input(
                "Or paste redirected URL / `?code=...` here if authorizing from another browser tab:",
                placeholder="https://onebillionviews.streamlit.app/?code=4/0A...",
            )
            if st.button("🔗 Verify Code & Save Permanent Refresh Token", use_container_width=True) and manual_code.strip():
                try:
                    info = exchange_youtube_auth_code(manual_code.strip(), redirect_uri=redir_val)
                    st.success(f"🟢 Connected `{info.get('connected_channel_title', 'TopperLab 3D')}`!")
                    st.rerun()
                except Exception as exc:
                    st.error(str(exc))
        else:
            st.info("Upload your `client_secret.json` on the left to unlock the 1-Click Google Authorization button.")

        tok_disk = ROOT_DIR / "config" / "credentials" / "youtube_oauth_token.json"
        if yt_status.get("connected") and tok_disk.exists():
            with st.expander("☁️ Optional: Keep Token Permanent Across Streamlit Cloud Restarts"):
                st.caption("Paste this line into **Streamlit Cloud → Manage app → Settings → Secrets** so `@TopperLab3D` stays connected forever:")
                st.code(f"YOUTUBE_OAUTH_TOKEN_JSON = '''{tok_disk.read_text(encoding='utf-8').strip()}'''", language="toml")

    with st.expander("📸 Optional: Connect Instagram Reels & Facebook Page (`Meta Graph API v21.0`)"):
        mc1, mc2, mc3 = st.columns(3)
        with mc1:
            m_tok = st.text_input("Meta Page Access Token:", value=meta_creds.get("page_access_token", ""), type="password")
        with mc2:
            m_fb = st.text_input("Facebook Page ID:", value=meta_creds.get("facebook_page_id", ""))
        with mc3:
            m_ig = st.text_input("Instagram Business Account ID:", value=meta_creds.get("instagram_account_id", ""))
        if st.button("💾 Save Meta Reels Credentials"):
            save_meta_credentials(m_tok, m_fb, m_ig)
            st.success("Saved Meta Graph API credentials securely!")

    with st.expander("⚙️ Update Channel Name / Handle / Default Voice in `active_channel.json`"):
        uc1, uc2, uc3 = st.columns(3)
        with uc1:
            ed_name = st.text_input("Channel Name:", value=channel_cfg["channel_name"])
        with uc2:
            ed_handle = st.text_input("Channel Handle:", value=channel_cfg["channel_handle"])
        with uc3:
            ed_cid = st.text_input("YouTube Channel ID:", value=channel_cfg.get("youtube_channel_id", ""))
        if st.button("💾 Save Channel Profile Defaults"):
            channel_cfg["channel_name"] = ed_name.strip()
            channel_cfg["channel_handle"] = ed_handle.strip()
            channel_cfg["youtube_channel_id"] = ed_cid.strip()
            channel_cfg["youtube_channel_url"] = f"https://www.youtube.com/channel/{ed_cid.strip()}"
            channel_cfg["default_voice_mode"] = st.session_state["voice_mode"]
            channel_cfg["default_visual_theme"] = st.session_state["visual_theme_key"]
            save_active_channel(channel_cfg)
            st.success("Updated `config/active_channel.json`!")
            st.rerun()

# ============================================================================
# STEP 2: SYLLABUS / STRATEGY IDEA ENGINE, DUAL SCRIPT & PURE 3D THUMBNAILS
# ============================================================================
with tab2:
    st.markdown('<span class="step-badge">STEP 2 • PICK HIGH-SCHOOL TOPIC → GENERATE DUAL SCRIPT & 3D THUMBNAILS</span>', unsafe_allow_html=True)

    pcol1, pcol2, pcol3 = st.columns([1.6, 1.4, 1.4])
    with pcol1:
        pillar_ids = list(pillars_by_id.keys())
        sel_pillar = st.selectbox(
            "1. Select Faceless Content Pillar:",
            options=pillar_ids,
            format_func=lambda pid: pillars_by_id[pid]["name"],
            index=pillar_ids.index(st.session_state["selected_pillar_id"]),
        )
        if sel_pillar != st.session_state["selected_pillar_id"]:
            st.session_state["selected_pillar_id"] = sel_pillar
            st.session_state["generated_topics"] = pillars_by_id[sel_pillar]["starter_topics"]
            st.session_state["selected_topic_title"] = st.session_state["generated_topics"][0]["title"]
            st.rerun()

    with pcol2:
        st.session_state["selected_exam_track"] = st.selectbox(
            "2. Target Exam / Student Track:",
            options=pillars_cfg["exam_tracks"],
        )
    with pcol3:
        chapter_filter = st.text_input(
            "3. Specific Chapter / Concept (Optional):",
            placeholder="e.g., Rotational Motion, Electrochemistry, Optics, DNA...",
        )

    if st.button("🔍 Generate 5 High-CTR Topic Ideas for @TopperLab3D", use_container_width=True):
        with st.spinner("Generating high-retention 3D student video concepts..."):
            topics = generate_viral_highschool_topics(
                pillar_id=st.session_state["selected_pillar_id"],
                exam_track=st.session_state["selected_exam_track"],
                custom_chapter_query=chapter_filter,
            )
            st.session_state["generated_topics"] = topics
            st.session_state["selected_topic_title"] = topics[0]["title"]

    topics_list = st.session_state["generated_topics"]
    st.dataframe(topics_list, use_container_width=True, hide_index=True)

    topic_titles = [t["title"] for t in topics_list]
    picked_from_list = st.selectbox(
        "Pick an Idea From Above (or customize the exact title below):",
        options=topic_titles,
        index=topic_titles.index(st.session_state["selected_topic_title"])
        if st.session_state["selected_topic_title"] in topic_titles
        else 0,
    )
    final_topic_title = st.text_input("🎯 Working Video Title:", value=picked_from_list)
    st.session_state["selected_topic_title"] = final_topic_title

    sc_col1, sc_col2 = st.columns([1, 2])
    with sc_col1:
        num_scenes = st.selectbox(
            "Target Episode Depth:",
            options=[4, 6, 8],
            format_func=lambda n: (
                "4 Scenes (~1–2 Min Core 3D Breakdown + 45s Short)"
                if n == 4
                else (f"{n} Scenes (~4–6 Min Deep 3D Chapter)" if n == 6 else f"{n} Scenes (~8+ Min Full Syllabus Masterclass)")
            ),
        )
    with sc_col2:
        custom_thumb_override = st.text_input(
            "Optional Custom 3D Thumbnail Prompt Override:",
            placeholder="Leave blank for automatic Veritasium/Zack-D-Films 3D thumbnail generation...",
        )

    if st.button(
        "✨ Build Dual Script, Google Flow Prompts & Pure 3D Thumbnails",
        type="primary",
        use_container_width=True,
    ):
        with st.spinner("Designing 3D storyboard, Clean Indian-English script & pure 3D thumbnails..."):
            bp = generate_dual_script_and_thumbnails(
                topic_title=final_topic_title,
                pillar_id=st.session_state["selected_pillar_id"],
                exam_track=st.session_state["selected_exam_track"],
                voice_mode=st.session_state["voice_mode"],
                visual_theme_key=st.session_state["visual_theme_key"],
                scene_count=num_scenes,
                custom_thumb_prompt=custom_thumb_override,
                force_regenerate_thumbs=bool(custom_thumb_override.strip()),
            )
            st.session_state["current_blueprint"] = bp
            st.session_state["seo_bundle"] = None
        st.success("✅ 3D Storyboard & Pure Thumbnails Ready! Review below and click Render.")

    bp = st.session_state.get("current_blueprint")
    if bp:
        st.divider()
        t_col1, t_col2 = st.columns([2.1, 1])
        with t_col1:
            st.subheader("🖥️ `16:9` Pure 3D YouTube Thumbnail")
            tp = resolve_workspace_path(bp["thumbnail_16x9_path"])
            if tp.exists():
                st.image(str(tp), use_container_width=True)
                st.download_button(
                    "⬇️ Download 16:9 Thumbnail (.jpg)",
                    data=tp.read_bytes(),
                    file_name="TopperLab3D_Thumbnail_16x9.jpg",
                    mime="image/jpeg",
                )
        with t_col2:
            st.subheader("📱 `9:16` Short / Reel Cover")
            sp = resolve_workspace_path(bp["short_cover_9x16_path"])
            if sp.exists():
                st.image(str(sp), width=230)
                st.download_button(
                    "⬇️ Download 9:16 Short Cover (.jpg)",
                    data=sp.read_bytes(),
                    file_name="TopperLab3D_Short_Cover_9x16.jpg",
                    mime="image/jpeg",
                )

        st.subheader("📜 Faceless 3D Scene-by-Scene Script Preview")
        for sc in bp["scenes"]:
            st.markdown(
                f"**Scene {sc['scene_id']:02d} — {sc['headline']}** (`{sc['concept_takeaway']}`)  \n"
                f"🎙️ *{sc['narration']}*"
            )

        if st.button(
            "🎬 Approve & Render Full `16:9` Long Video + `9:16` Short (`-14 LUFS` Clean Indian-English)",
            type="primary",
            use_container_width=True,
        ):
            with st.spinner("Synthesizing Clean Indian-English narration, rendering 3D scenes & stitching 16:9 + 9:16 MP4s..."):
                draft = render_full_topperlab_project(bp, short_max_scenes=4)
                st.session_state["current_draft"] = draft
                st.session_state["seo_bundle"] = generate_student_seo_bundle(
                    video_title=draft["topic_title"],
                    exam_track=draft["exam_track"],
                    scenes=draft["scenes"],
                    resource_links=st.session_state["resource_links"],
                )
            st.success("🎉 Master `16:9` Video + `9:16` Short Rendered! Open **Step 3** to preview or **Step 4** to publish.")

# ============================================================================
# STEP 3: 3D VIDEO STUDIO PLAYER, SCENE EDITOR & GOOGLE FLOW / VEO CLIPS
# ============================================================================
with tab3:
    st.markdown('<span class="step-badge">STEP 3 • PREVIEW MASTER VIDEOS, EDIT SCENES & DROP IN GOOGLE FLOW / VEO 3.1 CLIPS</span>', unsafe_allow_html=True)

    st.markdown(
        '<div class="lab-card"><b>100% Free Built-In 3D Camera Motion + Clean Indian-English Voiceover</b><br/>'
        'Render or re-render your full <code>16:9</code> Long Video and <code>9:16</code> Vertical Short anytime below with zero paid video API needed—or drop custom Google Flow / Omni clips per scene.</div>',
        unsafe_allow_html=True,
    )
    if st.button(
        "🎬 Generate / Re-Render Master `16:9` Long Video + `9:16` Short Now (Free Built-In 3D Engine)",
        type="primary",
        use_container_width=True,
        key="step3_top_render_btn",
    ):
        with st.spinner("Building 3D scenes, Clean Indian-English (-14 LUFS) voiceover & stitching 16:9 + 9:16 MP4s..."):
            active_bp = st.session_state.get("current_blueprint")
            if not active_bp or active_bp.get("topic_title") != st.session_state["selected_topic_title"]:
                active_bp = generate_dual_script_and_thumbnails(
                    topic_title=st.session_state["selected_topic_title"],
                    pillar_id=st.session_state["selected_pillar_id"],
                    exam_track=st.session_state["selected_exam_track"],
                    voice_mode=st.session_state["voice_mode"],
                    visual_theme_key=st.session_state["visual_theme_key"],
                    scene_count=4,
                )
                st.session_state["current_blueprint"] = active_bp
            active_bp["voice_mode"] = st.session_state["voice_mode"]
            active_bp["visual_theme_key"] = st.session_state["visual_theme_key"]
            rendered_draft = render_full_topperlab_project(active_bp, short_max_scenes=4)
            st.session_state["current_draft"] = rendered_draft
            st.session_state["seo_bundle"] = generate_student_seo_bundle(
                video_title=rendered_draft["topic_title"],
                exam_track=rendered_draft["exam_track"],
                scenes=rendered_draft["scenes"],
                resource_links=st.session_state["resource_links"],
            )
        st.success("✅ Master `16:9` Long Video + `9:16` Vertical Short rendered and ready below!")
        st.rerun()

    draft = st.session_state.get("current_draft")
    if not draft:
        st.info("Click **🎬 Generate / Re-Render Master `16:9` Long Video + `9:16` Short Now** above to create both videos.")
    else:
        v1, v2 = st.columns([2.2, 1.2])
        with v1:
            st.subheader(f"🖥️ YouTube Long-Form (`16:9` • {draft['renders']['long_duration_sec']}s)")
            long_mp4 = resolve_workspace_path(draft["renders"]["long_16x9_mp4"])
            if long_mp4.exists():
                st.video(str(long_mp4))
                st.download_button(
                    "⬇️ Download Master 16:9 Video (.mp4)",
                    data=long_mp4.read_bytes(),
                    file_name=f"{long_mp4.parent.parent.name}_16x9.mp4",
                    mime="video/mp4",
                    use_container_width=True,
                )
            else:
                st.warning("Click **🎬 Generate / Re-Render** above to build this workspace's `16:9` MP4.")
        with v2:
            st.subheader(f"📱 YouTube Short / IG Reel (`9:16` • {draft['renders']['short_duration_sec']}s)")
            short_mp4 = resolve_workspace_path(draft["renders"]["short_9x16_mp4"])
            if short_mp4.exists():
                st.video(str(short_mp4))
                st.download_button(
                    "⬇️ Download Vertical 9:16 Short (.mp4)",
                    data=short_mp4.read_bytes(),
                    file_name=f"{short_mp4.parent.parent.name}_SHORT_9x16.mp4",
                    mime="video/mp4",
                    use_container_width=True,
                )
            else:
                st.warning("Click **🎬 Generate / Re-Render** above to build this workspace's `9:16` Short MP4.")

        st.divider()
        st.subheader("🧬 Scene-by-Scene 3D Editor + Google AI Ultra Flow (`Veo / Omni`) Integration")
        st.caption(
            "Want custom AI physics motion on a specific scene? Copy the **Google Flow Prompt** below into [Google Flow](https://labs.google/fx/tools/flow) "
            "and drop the `.mp4` clip into that scene (or test direct API generation if paid video quota is enabled)."
        )

        for sc in draft["scenes"]:
            sid = int(sc["scene_id"])
            with st.expander(
                f"Scene {sid:02d}: {sc['headline']} — {sc.get('duration_sec', 12)}s [{sc.get('motion_source', '3D Plate')}]",
                expanded=(sid == 1),
            ):
                ec1, ec2 = st.columns([1.1, 1.9])
                with ec1:
                    img_p = resolve_workspace_path(sc.get("img_16x9", ""))
                    if img_p.exists():
                        st.image(str(img_p), caption=f"Scene {sid:02d} Pure 3D Frame")
                    st.code(sc.get("google_flow_veo_prompt", ""), language="text")
                    if st.button(f"⚡ Try Direct AI Motion Clip (Scene {sid:02d})", key=f"veo_btn_{sid}", use_container_width=True):
                        out_veo = resolve_workspace_path(draft["project_dir"]) / "scenes" / f"scene_{sid:02d}_custom_motion.mp4"
                        with st.spinner(f"Requesting Veo 3D clip for Scene {sid:02d}..."):
                            vres = generate_veo_clip_via_api(sc.get("google_flow_veo_prompt", ""), out_veo)
                        if vres.get("ok"):
                            updated = update_single_faceless_scene(
                                draft, sid, sc["narration"], sc["image_3d_prompt"], regenerate_3d_image=False
                            )
                            st.session_state["current_draft"] = updated
                            st.success("Stitched Veo motion clip!")
                            st.rerun()
                        else:
                            st.info(vres.get("message", ""))

                with ec2:
                    ed_narr = st.text_area(f"Spoken Narration (Scene {sid:02d}):", value=sc["narration"], key=f"narr_{sid}", height=95)
                    ed_img_p = st.text_area(f"Pure 3D Image Prompt (Scene {sid:02d}):", value=sc["image_3d_prompt"], key=f"imgp_{sid}", height=80)
                    regen_img_chk = st.checkbox("Regenerate 3D Image via Nano Banana / Imagen", value=False, key=f"rg_{sid}")
                    flow_upload = st.file_uploader(
                        f"🎞️ Optional: Drop Google Flow / Veo `.mp4` Motion Clip for Scene {sid:02d}:",
                        type=["mp4"],
                        key=f"flow_up_{sid}",
                    )
                    if st.button(f"🔄 Update Scene {sid:02d} & Re-Stitch Master Videos", key=f"upd_{sid}", type="primary"):
                        with st.spinner(f"Updating Scene {sid:02d} & re-stitching 16:9 + 9:16 videos..."):
                            motion_bytes = flow_upload.read() if flow_upload is not None else None
                            updated = update_single_faceless_scene(
                                draft_state=draft,
                                scene_id=sid,
                                new_narration=ed_narr,
                                new_3d_prompt=ed_img_p,
                                regenerate_3d_image=regen_img_chk,
                                uploaded_motion_bytes=motion_bytes,
                            )
                            st.session_state["current_draft"] = updated
                        st.success(f"✅ Scene {sid:02d} updated and master MP4s re-stitched!")
                        st.rerun()

# ============================================================================
# STEP 4: STUDENT FORMULA SHEETS / LINKS & DIRECT CLOUD SCHEDULER
# ============================================================================
with tab4:
    st.markdown('<span class="step-badge">STEP 4 • ATTACH FORMULA SHEETS / TRACKERS & PUBLISH OR CLOUD-SCHEDULE</span>', unsafe_allow_html=True)
    draft = st.session_state.get("current_draft")

    st.subheader("📥 4.1 Student Digital Lead-Magnets & Affiliate Links")
    lc1, lc2, lc3, lc4 = st.columns([1.4, 1.8, 2.0, 0.9])
    with lc1:
        l_cat = st.selectbox(
            "Resource Type:",
            options=[
                "📄 1-Page 3D Formula & Concept Cheat Sheet (PDF)",
                "📊 99%iler Active-Recall & Revision Tracker (Sheet)",
                "📚 Recommended NCERT / JEE / NEET Book (Affiliate)",
                "🧪 Digital Notes Pack / Mock Test Bundle",
            ],
        )
    with lc2:
        l_lbl = st.text_input("Call-to-Action Label:", placeholder="Download Rotational Motion 1-Page 3D Sheet")
    with lc3:
        l_url = st.text_input("URL (Google Drive / Sheet / Gumroad / Amazon):", placeholder="https://drive.google.com/...")
    with lc4:
        st.write("")
        if st.button("➕ Add Link", use_container_width=True) and l_lbl.strip() and l_url.strip():
            st.session_state["resource_links"].append(
                {"category": l_cat, "label": l_lbl.strip(), "url": l_url.strip()}
            )
            st.session_state["seo_bundle"] = None
            st.rerun()

    if st.session_state["resource_links"]:
        st.dataframe(st.session_state["resource_links"], use_container_width=True, hide_index=True)

    st.divider()
    st.subheader("📝 4.2 Auto-Generated SEO Description, 3D Chapters & Pinned Comment")
    active_title = draft["topic_title"] if draft else st.session_state["selected_topic_title"]
    active_track = draft["exam_track"] if draft else st.session_state["selected_exam_track"]
    active_scenes = draft["scenes"] if draft else []

    if st.button("✨ Refresh SEO Copy & Timestamps With Links", use_container_width=True) or st.session_state["seo_bundle"] is None:
        st.session_state["seo_bundle"] = generate_student_seo_bundle(
            video_title=active_title,
            exam_track=active_track,
            scenes=active_scenes,
            resource_links=st.session_state["resource_links"],
        )

    seo = st.session_state["seo_bundle"]
    sc1, sc2 = st.columns(2)
    with sc1:
        yt_desc_box = st.text_area("▶️ YouTube Long-Form Description (Chapters + PDF Links):", value=seo["youtube_description"], height=220)
        pin_box = st.text_area("📌 High-Conversion Pinned Comment:", value=seo["pinned_comment"], height=120)
    with sc2:
        short_cap_box = st.text_area("⚡ YouTube Shorts / IG & FB Reel Caption:", value=seo["short_reel_caption"], height=220)
        tags_box = st.text_input("🔍 YouTube SEO Keyword Tags (Comma-Separated):", value=seo["seo_tags_str"])

    st.divider()
    st.subheader("🚀 4.3 Direct Publish or Native Cloud Schedule (`@TopperLab3D`)")
    dc1, dc2 = st.columns(2)
    with dc1:
        do_yt_long = st.checkbox("▶️ YouTube Long-Form (`16:9` + Custom 3D Thumbnail + Chapters)", value=True)
        do_yt_short = st.checkbox("⚡ YouTube Shorts (`9:16` Vertical Cut)", value=True)
    with dc2:
        do_fb_reel = st.checkbox("📘 Facebook Page Reel (`9:16`)", value=False)
        do_ig_reel = st.checkbox("📸 Instagram Reel (`9:16`)", value=False)

    ig_pub_url = ""
    if do_ig_reel:
        ig_pub_url = st.text_input(
            "Temporary Public HTTPS `.mp4` URL (required by Meta only for Instagram Reels ingestion):",
            placeholder="https://...",
        )

    tc1, tc2, tc3 = st.columns(3)
    with tc1:
        pub_date = st.date_input("Publish Date (IST):", value=datetime.date.today() + datetime.timedelta(days=1))
    with tc2:
        pub_time = st.time_input("Peak Student Window (IST — 4:30 PM or 8:30 PM best):", value=datetime.time(16, 30))
    with tc3:
        exec_mode = st.radio("Publish Mode:", options=["Cloud Schedule for Peak IST Window", "Publish Immediately"])

    if st.button("🚀 Dispatch / Cloud-Schedule Selected Videos", type="primary", use_container_width=True):
        if not draft:
            st.error("Render your video in Step 2 first before dispatching!")
        else:
            sched_dt = datetime.datetime.combine(pub_date, pub_time)
            is_now = exec_mode == "Publish Immediately"
            tag_list = [t.strip() for t in tags_box.split(",") if t.strip()]

            jobs = []
            if do_yt_long:
                jobs.append(
                    (
                        "YouTube Long-Form",
                        "16:9 (1080p)",
                        active_title,
                        yt_desc_box,
                        draft["renders"]["long_16x9_mp4"],
                        draft.get("thumbnail_16x9_path"),
                    )
                )
            if do_yt_short:
                jobs.append(
                    (
                        "YouTube Shorts",
                        "9:16 Short",
                        f"{active_title[:88]} #Shorts",
                        short_cap_box,
                        draft["renders"]["short_9x16_mp4"],
                        None,
                    )
                )
            if do_fb_reel:
                jobs.append(("Facebook Reels", "9:16 Reel", active_title, short_cap_box, draft["renders"]["short_9x16_mp4"], None))
            if do_ig_reel:
                jobs.append(("Instagram Reels", "9:16 Reel", active_title, short_cap_box, draft["renders"]["short_9x16_mp4"], None))

            results = []
            with st.spinner("Uploading / Scheduling across selected platforms..."):
                for plat, fmt_lbl, ttl, desc_txt, v_file, t_file in jobs:
                    r = publish_or_schedule_deliverable(
                        platform=plat,
                        format_type=fmt_lbl,
                        title=ttl,
                        description_or_caption=desc_txt,
                        tags=tag_list,
                        video_path=v_file,
                        scheduled_ist_dt=sched_dt,
                        publish_now=is_now,
                        thumbnail_path=t_file,
                        public_mp4_url_for_ig=ig_pub_url,
                    )
                    results.append(r)

            for r in results:
                st.success(f"**{r['platform']}** → `{r['status']}` | {r['note']}")

    st.subheader("📅 `@TopperLab3D` Publishing & Scheduling Log")
    q_rows = list_publish_queue()
    if q_rows:
        st.dataframe(q_rows, use_container_width=True, hide_index=True)
    else:
        st.caption("No local dispatch rows in this session yet.")

    if yt_status.get("connected"):
        st.subheader("📺 Live `@TopperLab3D` Scheduled & Published Videos (Verified on YouTube)")
        if st.button("🔄 Refresh Live YouTube Channel Uploads & Schedule", use_container_width=True) or "live_yt_vids" not in st.session_state:
            st.session_state["live_yt_vids"] = fetch_live_youtube_channel_videos(max_results=10)
        if st.session_state.get("live_yt_vids"):
            st.dataframe(st.session_state["live_yt_vids"], use_container_width=True, hide_index=True)
