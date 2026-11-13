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

from studio_engine import (
    ALL_CURRICULUM_SUBJECTS,
    CORE_STEM_SUBJECTS,
    CURRICULUM_BOARDS,
    CURRICULUM_CLASSES,
    SCRIPT_MODEL_PRESETS,
    apply_consistent_topperlab_thumbnail_branding,
    build_youtube_auth_url,
    check_gemini_api_key_health,
    check_youtube_playlist_scope,
    exchange_youtube_auth_code,
    fetch_live_youtube_channel_videos,
    format_booster_video_title,
    format_syllabus_chapter_title,
    generate_dual_script_and_thumbnails,
    generate_student_seo_bundle,
    generate_topperlab_branding,
    generate_veo_clip_via_api,
    generate_viral_highschool_topics,
    get_active_script_model,
    get_curriculum_chapters,
    get_curriculum_subjects,
    get_gemini_api_key,
    get_youtube_oauth_status,
    has_vertex_adc,
    infer_class_badge_label,
    list_live_youtube_playlists,
    list_publish_queue,
    load_active_channel,
    load_curriculum_catalog,
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
    strip_3d_text,
    sync_cbse_icse_playlists_and_sections,
    update_single_faceless_scene,
)

st.set_page_config(
    page_title="TopperLab Studio | Complete Syllabus Chapters & Exam Boosters",
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
        st.session_state.pop("yt_pl_scope_cache", None)
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


curriculum_catalog = load_curriculum_catalog()

# Pre-load flagship sample project if already rendered on disk
_sample_dir = ROOT_DIR / "workspaces" / "topperlab_3d" / "heights-and-distances-in-6-mins-complete"
if not (_sample_dir / "topperlab_draft_state.json").exists():
    _sample_dir = ROOT_DIR / "workspaces" / "topperlab_3d" / "why-spinning-gyroscopes-defy-gravity-rotational-motion-t"
_preloaded_bp = _load_portable_json(_sample_dir / "topperlab_blueprint.json")
_preloaded_draft = _load_portable_json(_sample_dir / "topperlab_draft_state.json")

for k, default_val in [
    ("ui_theme_mode", "🌙 Dark Lab Mode"),
    ("script_model_id", get_active_script_model()),
    ("voice_mode", channel_cfg.get("default_voice_mode", "Energetic Indian Mentor — Expressive AI (en-IN)")),
    ("visual_theme_key", channel_cfg.get("default_visual_theme", "BRIGHT_CLASSROOM_3D_MODEL")),
    ("bgm_enabled", True),
    ("playlist_track_mode", "📘 Foundation Syllabus Chapter (Complete Chapter Playlist)"),
    ("selected_board", "CBSE"),
    ("target_class_label", "Class 10"),
    ("target_subject_label", "Mathematics"),
    ("selected_chapter", "Heights and Distances"),
    ("duration_badge", "6 Mins"),
    ("video_category", "syllabus_chapter"),
    ("booster_mode_key", "toppers_hack"),
    ("selected_pillar_id", "3d_concept_visualizer"),
    ("selected_exam_track", "CBSE Class 10 Mathematics"),
    ("generated_topics", pillars_cfg["pillars"][1]["starter_topics"]),
    ("selected_topic_title", "Heights and Distances in 6 Mins Complete"),
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
    st.session_state["bgm_enabled"] = st.checkbox(
        "🎵 Background Groove + Fly-In Chime SFX",
        value=bool(st.session_state.get("bgm_enabled", True)),
        help="Adds lively student-curiosity marimba music (auto-ducked under voice) + whoosh & bell chimes synced with Fly-In Formulas & Quick Tips!",
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
st.title(f"🔬 {channel_cfg['channel_name']} — Complete Chapters & Exam Booster Studio")
st.caption(
    f"**Cohort:** {channel_cfg['cohort']}  •  **Default Narration:** `{st.session_state['voice_mode']}`  •  "
    f"**Foundation Chapter Playlists + Toppers Hacks (`16:9` + Shorts `9:16`)**"
)

tab1, tab2, tab3, tab4 = st.tabs(
    [
        "🎨 Step 1: Brand, Playlists & YouTube Connect",
        "📘 Step 2: Select Syllabus Chapter or Booster",
        "🎞️ Step 3: Video Studio & Scene Editor",
        "🚀 Step 4: SEO Hashtags & Cloud Schedule",
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
                    st.session_state.pop("yt_pl_scope_cache", None)
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

    st.divider()
    st.subheader("📚 CBSE & ICSE (Class 8–12) Subject Playlists + Channel Homepage Sections")
    if yt_status.get("connected") and "yt_pl_scope_cache" not in st.session_state:
        st.session_state["yt_pl_scope_cache"] = check_youtube_playlist_scope()
    has_pl_scope = st.session_state.get("yt_pl_scope_cache", False) if yt_status.get("connected") else False
    if has_pl_scope:
        st.success("🟢 YouTube Playlist & Homepage Section Manager Unlocked (`@TopperLab3D`)")
    else:
        st.warning(
            "🟠 **One 10-Second Step Required:** Your current YouTube token was created with Upload-Only permission. "
            "Click **🔵 2. Sign In & Authorize @TopperLab3D** right above once (`jwala4work@gmail.com` → Allow) to unlock automatic Playlist & Homepage Section creation!"
        )

    pl_c1, pl_c2, pl_c3 = st.columns([1.0, 1.4, 2.0])
    with pl_c1:
        sel_pl_boards = st.multiselect("Boards:", options=CURRICULUM_BOARDS, default=CURRICULUM_BOARDS, key="arch_boards")
    with pl_c2:
        sel_pl_classes = st.multiselect("Classes (8–12):", options=CURRICULUM_CLASSES, default=CURRICULUM_CLASSES, key="arch_classes")
    with pl_c3:
        sel_pl_subjects = st.multiselect(
            "Separate Subject Playlists (per Board & Class):",
            options=ALL_CURRICULUM_SUBJECTS,
            default=CORE_STEM_SUBJECTS,
            key="arch_subjects",
        )

    planned_count = len(sel_pl_boards) * len(sel_pl_classes) * len(sel_pl_subjects)
    st.caption(
        f"Will create/verify **{planned_count} separate subject playlists** "
        f"(`{len(sel_pl_boards)} Boards × {len(sel_pl_classes)} Classes × {len(sel_pl_subjects)} Subjects`) "
        f"+ **8 Board & Class Horizontal Shelves** on `@TopperLab3D`'s Homepage, and auto-link existing videos."
    )
    if st.button(
        f"🚀 Create / Sync All {planned_count} CBSE & ICSE Playlists + Homepage Sections on @TopperLab3D",
        type="primary",
        use_container_width=True,
    ):
        with st.spinner("Creating separate CBSE & ICSE Class 8–12 subject playlists and organizing @TopperLab3D homepage shelves..."):
            st.session_state["yt_pl_scope_cache"] = check_youtube_playlist_scope()
            sync_res = sync_cbse_icse_playlists_and_sections(
                boards=sel_pl_boards,
                classes=sel_pl_classes,
                subjects=sel_pl_subjects,
                attach_existing_videos=True,
            )
        if sync_res.get("ok"):
            st.success(
                f"✅ Done! Created **{sync_res['created_playlists']}** new playlists "
                f"(reused **{sync_res['reused_playlists']}** existing • **{sync_res['total_playlists_ready']}** total ready) | "
                f"Homepage Sections: **{sync_res['sections_created']}** created, **{sync_res['sections_updated']}** updated!"
            )
            if sync_res.get("errors"):
                st.warning("Partial notices: " + " | ".join(sync_res["errors"][:3]))
            st.session_state["live_yt_playlists"] = list_live_youtube_playlists()
        else:
            st.error(sync_res.get("error", "Could not sync playlists."))

    if yt_status.get("connected"):
        with st.expander("📋 View Live `@TopperLab3D` Playlists on YouTube"):
            if st.button("🔄 Load / Refresh Live Playlists", key="btn_ref_pls"):
                st.session_state["live_yt_playlists"] = list_live_youtube_playlists()
            if st.session_state.get("live_yt_playlists"):
                st.dataframe(st.session_state["live_yt_playlists"], use_container_width=True, hide_index=True)
            else:
                st.caption("Click 'Load / Refresh Live Playlists' above (or run the Create / Sync button first)!")

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
# STEP 2: CASCADING CURRICULUM CHAPTER DROPDOWNS + POST-FOUNDATION BOOSTERS
# ============================================================================
with tab2:
    st.markdown(
        '<span class="step-badge">STEP 2 • SELECT BOARD, CLASS, SUBJECT & CHAPTER → BUILD FOUNDATION OR BOOSTER VIDEO</span>',
        unsafe_allow_html=True,
    )

    mode_options = [
        "📘 Foundation Syllabus Chapter (Complete Chapter Playlist)",
        "⚡ Post-Foundation Boosters (Toppers Hack • Exam Tricks • Super Memory)",
    ]
    sel_mode = st.radio(
        "🎯 Choose Video Production Track:",
        options=mode_options,
        index=0 if st.session_state["playlist_track_mode"].startswith("📘") else 1,
        horizontal=True,
    )
    st.session_state["playlist_track_mode"] = sel_mode
    is_foundation_mode = sel_mode.startswith("📘")

    # Cascading Curriculum Dropdowns: Board -> Class -> Subject -> Every Chapter
    board_opts = curriculum_catalog.get("boards", ["CBSE", "ICSE"])
    class_opts = curriculum_catalog.get("classes", ["Class 10", "Class 9", "Class 8", "Class 11", "Class 12"])
    dur_opts = curriculum_catalog.get("duration_badges", ["6 Mins", "5 Mins", "8 Mins", "10 Mins", "15 Mins"])

    dd1, dd2, dd3, dd4 = st.columns([0.85, 0.95, 1.25, 2.15])
    with dd1:
        sel_board = st.selectbox(
            "1. Board:",
            options=board_opts,
            index=board_opts.index(st.session_state["selected_board"])
            if st.session_state["selected_board"] in board_opts
            else 0,
        )
        st.session_state["selected_board"] = sel_board

    with dd2:
        sel_class = st.selectbox(
            "2. Class:",
            options=class_opts,
            index=class_opts.index(st.session_state["target_class_label"])
            if st.session_state["target_class_label"] in class_opts
            else 0,
        )
        st.session_state["target_class_label"] = sel_class

    subj_opts = get_curriculum_subjects(sel_board, sel_class)
    with dd3:
        sel_subject = st.selectbox(
            "3. Subject:",
            options=subj_opts,
            index=subj_opts.index(st.session_state["target_subject_label"])
            if st.session_state["target_subject_label"] in subj_opts
            else 0,
        )
        st.session_state["target_subject_label"] = sel_subject

    raw_chapters = get_curriculum_chapters(sel_board, sel_class, sel_subject)
    custom_ch_sentinel = "✍️ Type Custom Chapter / Topic..."
    chapter_choices = raw_chapters + [custom_ch_sentinel]

    default_ch_idx = 0
    if st.session_state.get("selected_chapter") in raw_chapters:
        default_ch_idx = raw_chapters.index(st.session_state["selected_chapter"])
    elif "Heights and Distances" in raw_chapters:
        default_ch_idx = raw_chapters.index("Heights and Distances")

    with dd4:
        picked_chapter = st.selectbox(
            f"4. Select {sel_board} {sel_class} {sel_subject} Chapter ({len(raw_chapters)} Chapters):",
            options=chapter_choices,
            index=default_ch_idx,
            format_func=lambda ch_nm: (
                ch_nm if ch_nm == custom_ch_sentinel else f"Ch {raw_chapters.index(ch_nm) + 1:02d}. {ch_nm}"
            ),
        )

    if picked_chapter == custom_ch_sentinel:
        active_chapter = st.text_input(
            "Enter Custom Chapter Name:",
            value=st.session_state.get("selected_chapter", "Heights and Distances"),
        ).strip() or "Heights and Distances"
    else:
        active_chapter = picked_chapter

    st.session_state["selected_chapter"] = active_chapter
    st.session_state["selected_exam_track"] = f"{sel_board} {sel_class} {sel_subject}"

    if is_foundation_mode:
        st.session_state["video_category"] = "syllabus_chapter"
        st.session_state["selected_pillar_id"] = "3d_concept_visualizer"

        fcol1, fcol2 = st.columns([1.0, 3.2])
        with fcol1:
            sel_dur = st.selectbox(
                "5. Title Time Badge:",
                options=dur_opts,
                index=dur_opts.index(st.session_state["duration_badge"])
                if st.session_state["duration_badge"] in dur_opts
                else 0,
                help="Formats foundation playlist titles cleanly like 'Heights and Distances in 6 Mins Complete'.",
            )
            st.session_state["duration_badge"] = sel_dur

        auto_title = format_syllabus_chapter_title(active_chapter, sel_dur)
        combo_fp = f"FOUND|{sel_board}|{sel_class}|{sel_subject}|{active_chapter}|{sel_dur}"
        if st.session_state.get("_last_title_combo_fp") != combo_fp:
            st.session_state["_last_title_combo_fp"] = combo_fp
            st.session_state["working_title_input"] = auto_title
            st.session_state["selected_topic_title"] = auto_title

        with fcol2:
            final_topic_title = st.text_input(
                "🎯 Foundation Playlist Video Title (Zero '3D' text — ready for YouTube):",
                key="working_title_input",
            )
            st.session_state["selected_topic_title"] = strip_3d_text(final_topic_title) or auto_title

        with st.expander(
            f"📋 View Complete {sel_board} {sel_class} {sel_subject} Foundation Playlist Roadmap ({len(raw_chapters)} Chapters)"
        ):
            roadmap_rows = [
                {
                    "Ch #": f"{idx + 1:02d}",
                    "Syllabus Chapter": ch_item,
                    "Auto Video Title": format_syllabus_chapter_title(ch_item, sel_dur),
                    "Target Playlist": f"{sel_board} {sel_class} {sel_subject}",
                }
                for idx, ch_item in enumerate(raw_chapters)
            ]
            st.dataframe(roadmap_rows, use_container_width=True, hide_index=True)

    else:
        booster_modes = curriculum_catalog.get("booster_modes", {})
        b_keys = list(booster_modes.keys()) or ["toppers_hack", "exam_tricks", "super_memory"]
        bcol1, bcol2, bcol3 = st.columns([1.35, 1.35, 1.5])
        with bcol1:
            sel_b_key = st.selectbox(
                "5. Booster Series Type:",
                options=b_keys,
                format_func=lambda bk: booster_modes.get(bk, {}).get("label", bk),
                index=b_keys.index(st.session_state["booster_mode_key"])
                if st.session_state["booster_mode_key"] in b_keys
                else 0,
            )
            st.session_state["booster_mode_key"] = sel_b_key
            st.session_state["video_category"] = sel_b_key
            st.session_state["selected_pillar_id"] = (
                "pyq_exam_traps_shorts" if sel_b_key == "exam_tricks" else "topper_brain_strategy"
            )

        with bcol2:
            booster_scope = st.selectbox(
                "6. Topic Focus:",
                options=[
                    f"🎯 Chapter Booster: {active_chapter}",
                    "🌟 General Board Topper / Memory Video",
                ],
            )

        generic_list = booster_modes.get(sel_b_key, {}).get("generic_topics", [])
        chosen_generic = ""
        with bcol3:
            if booster_scope.startswith("🌟") and generic_list:
                chosen_generic = st.selectbox("Pick Curated Booster Topic:", options=generic_list)
            else:
                if st.button("🔍 Generate 5 Fresh AI Booster Ideas", use_container_width=True):
                    with st.spinner("Generating high-CTR Toppers Hack / Exam Trick ideas..."):
                        ideas = generate_viral_highschool_topics(
                            pillar_id=st.session_state["selected_pillar_id"],
                            exam_track=f"{sel_board} {sel_class} {sel_subject}",
                            custom_chapter_query=f"{active_chapter} ({sel_b_key.replace('_', ' ')})",
                        )
                        st.session_state["generated_topics"] = ideas
                        if ideas:
                            st.session_state["working_title_input"] = strip_3d_text(ideas[0]["title"])

        auto_b_title = format_booster_video_title(
            chapter_name=active_chapter,
            booster_mode_key=sel_b_key,
            generic_topic=chosen_generic,
        )
        combo_fp = f"BOOST|{sel_board}|{sel_class}|{sel_subject}|{active_chapter}|{sel_b_key}|{booster_scope}|{chosen_generic}"
        if st.session_state.get("_last_title_combo_fp") != combo_fp:
            st.session_state["_last_title_combo_fp"] = combo_fp
            st.session_state["working_title_input"] = auto_b_title
            st.session_state["selected_topic_title"] = auto_b_title

        if st.session_state.get("generated_topics") and not booster_scope.startswith("🌟"):
            with st.expander("💡 AI-Suggested Booster Variations (Click to inspect)"):
                st.dataframe(st.session_state["generated_topics"], use_container_width=True, hide_index=True)

        final_topic_title = st.text_input(
            "🎯 Booster Video Title (Zero '3D' text — ready for YouTube):",
            key="working_title_input",
        )
        st.session_state["selected_topic_title"] = strip_3d_text(final_topic_title) or auto_b_title

    sc_col1, sc_col2 = st.columns([1.3, 2.7])
    with sc_col1:
        default_depth_idx = 1 if (is_foundation_mode and st.session_state.get("duration_badge") in ("8 Mins", "10 Mins", "15 Mins")) else 0
        num_scenes = st.selectbox(
            "Target Scene Breakdown:",
            options=[4, 6, 8],
            index=default_depth_idx,
            format_func=lambda n: (
                "4 Crisp Scenes (Fast High-Retention Chapter + Short)"
                if n == 4
                else (f"{n} Scenes (Detailed Complete Chapter)" if n == 6 else f"{n} Scenes (Deep Masterclass)")
            ),
        )
    with sc_col2:
        custom_thumb_override = st.text_input(
            "Optional Custom Visual Model Override (for Thumbnail Artwork):",
            placeholder=f"Leave blank for bright {sel_class} {sel_subject} classroom visual model + Yellow/Red '{sel_class.upper()}' badge...",
        )

    if st.button(
        f"✨ Build '{st.session_state['selected_topic_title']}' Script, Formulas & Yellow+Red Thumbnail",
        type="primary",
        use_container_width=True,
    ):
        with st.spinner(
            f"Designing '{st.session_state['selected_topic_title']}' with Gemini 4, Fly-In Formulas & {sel_class} Yellow+Red Thumbnails..."
        ):
            bp = generate_dual_script_and_thumbnails(
                topic_title=st.session_state["selected_topic_title"],
                pillar_id=st.session_state["selected_pillar_id"],
                exam_track=st.session_state["selected_exam_track"],
                voice_mode=st.session_state["voice_mode"],
                visual_theme_key=st.session_state["visual_theme_key"],
                scene_count=num_scenes,
                custom_thumb_prompt=custom_thumb_override,
                force_regenerate_thumbs=True,
                target_class_label=st.session_state["target_class_label"],
                target_subject_label=st.session_state["target_subject_label"],
                selected_board=st.session_state["selected_board"],
                selected_chapter=st.session_state["selected_chapter"],
                video_category=st.session_state["video_category"],
                duration_badge=st.session_state["duration_badge"],
            )
            st.session_state["current_blueprint"] = bp
            st.session_state["seo_bundle"] = None
        st.success(f"✅ Blueprint, Fly-In Formulas & Consistent `{bp['class_badge_text']}` Thumbnails Ready!")

    bp = st.session_state.get("current_blueprint")
    if bp:
        st.divider()
        t_col1, t_col2 = st.columns([2.1, 1])
        with t_col1:
            st.subheader("🖥️ `16:9` YouTube Thumbnail")
            tp = resolve_workspace_path(bp["thumbnail_16x9_path"])
            if tp.exists():
                st.image(str(tp), use_container_width=True)
                st.download_button(
                    "⬇️ Download 16:9 Thumbnail (.jpg)",
                    data=tp.read_bytes(),
                    file_name="TopperLab_Thumbnail_16x9.jpg",
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
                    file_name="TopperLab_Short_Cover_9x16.jpg",
                    mime="image/jpeg",
                )

        st.subheader(f"📜 4-Act Big-Channel Script + 3-Portion Formula Highlighter (`{bp['topic_title']}`)")
        for sc in bp["scenes"]:
            act_lbl = sc.get("act_badge", f"ACT {sc['scene_id']}: CONCEPT")
            f_parts = sc.get("formula_parts", [])
            parts_str = "  →  ".join(f"`{p.get('label', '')}: {p.get('expr', '')}`" for p in f_parts) if f_parts else f"`{sc.get('formula_badge', '')}`"
            st.markdown(
                f"**Scene {sc['scene_id']:02d} [{act_lbl}] — {sc['headline']}** (`{sc['concept_takeaway']}`)  \n"
                f"🎯 **Highlighted Formula Portions:** {parts_str}  \n"
                f"⚡ **Topper Exam Hack:** `{sc.get('quick_tip', 'Board Exam Hack')}`  \n"
                f"🎙️ *{sc['narration']}*"
            )

        auto_veo_step2 = st.checkbox(
            "🎥 Auto-Generate Live Google Flow / Veo 3.1 AI B-Roll Clips (Vertex AI Cloud Credits)",
            value=True,
            key="auto_veo_step2_chk",
            help="Automatically generates moving 3D classroom B-Roll clips via Veo 3.1 / Gemini Omni and composites them with live animated lines, circles, compass arcs, and highlighted formula portions!",
        )

        if st.button(
            "🎬 Approve & Render Full `16:9` Video + `9:16` Short (Live Veo B-Roll + Animated Lines/Angles/Formula Highlight + ASMR BGM)",
            type="primary",
            use_container_width=True,
        ):
            with st.spinner("Generating Google Flow / Veo 3.1 B-Roll, synthesizing expressive voiceover + ASMR geometry SFX, and drawing live lines, compass arcs & highlighted formula portions..."):
                draft = render_full_topperlab_project(
                    bp,
                    short_max_scenes=4,
                    bgm_enabled=bool(st.session_state.get("bgm_enabled", True)),
                    force_live_images=True,
                    auto_veo_broll=auto_veo_step2,
                )
                st.session_state["current_draft"] = draft
                st.session_state["seo_bundle"] = generate_student_seo_bundle(
                    video_title=draft["topic_title"],
                    exam_track=draft["exam_track"],
                    scenes=draft["scenes"],
                    resource_links=st.session_state["resource_links"],
                    board=draft.get("selected_board", st.session_state["selected_board"]),
                    class_name=draft.get("target_class_label", st.session_state["target_class_label"]),
                    subject=draft.get("target_subject_label", st.session_state["target_subject_label"]),
                    chapter_name=draft.get("selected_chapter", st.session_state["selected_chapter"]),
                    video_category=draft.get("video_category", st.session_state["video_category"]),
                )
            st.success("🎉 Master `16:9` Video + `9:16` Short Rendered! Open **Step 3** to preview or **Step 4** to publish.")

# ============================================================================
# STEP 3: 3D VIDEO STUDIO PLAYER, SCENE EDITOR & GOOGLE FLOW / VEO CLIPS
# ============================================================================
with tab3:
    st.markdown('<span class="step-badge">STEP 3 • PREVIEW MASTER VIDEOS, LIVE GEOMETRY/FORMULA CANVAS & GOOGLE FLOW / VEO 3.1 CLIPS</span>', unsafe_allow_html=True)

    st.markdown(
        '<div class="lab-card"><b>🎥 Google Flow / Veo 3.1 Live B-Roll + Real-Time Animated Lines, Compass Arcs & Formula Portion Highlighting + 4-Act Retention Format</b><br/>'
        'Inspired by top viral math & science channels (<i>8MXN6QjPJqc</i> • <i>3Blue1Brown</i> • <i>Don\'t Memorise</i> • <i>Dear Sir</i>): '
        'Every scene pairs moving <b>Google Flow / Veo 3.1 B-Roll</b> with live animated <b>Green Guide Markers (1, 2, 3), Circles, Right-Triangle Lines, Metallic Compass Arcs (θ), 3-Portion Formula Highlighting, 5-Second Boss Countdown, and an Animated YouTube Subscribe + Bell CTA</b>!</div>',
        unsafe_allow_html=True,
    )
    rc_top1, rc_top2, rc_top3 = st.columns([2.5, 1.15, 1.15])
    with rc_top2:
        auto_veo_step3_chk = st.checkbox(
            "🎥 Live Veo 3.1 B-Roll",
            value=True,
            help="Automatically generate moving 3D classroom B-Roll clips via Vertex AI Veo 3.1 (`veo-3.1-lite-generate-001` / `veo-3.1-fast-generate-001`) for each scene.",
        )
    with rc_top3:
        force_fresh_3d_chk = st.checkbox(
            "✨ Fresh AI 3D Plates",
            value=False,
            help="Check to generate brand-new bright 3D classroom images via Nano Banana 2.1 when re-rendering.",
        )
    with rc_top1:
        step3_render_clicked = st.button(
            "🎬 Generate / Re-Render Master `16:9` Video + `9:16` Short (Veo B-Roll + Live Geometry & Formula Highlight)",
            type="primary",
            use_container_width=True,
            key="step3_top_render_btn",
        )
    if step3_render_clicked:
        with st.spinner("Generating Google Flow / Veo 3.1 B-Roll, synthesizing expressive AI voiceover + ASMR geometry SFX, and animating live lines, compass arcs & formula portions..."):
            active_bp = st.session_state.get("current_blueprint")
            if not active_bp or active_bp.get("topic_title") != st.session_state["selected_topic_title"]:
                active_bp = generate_dual_script_and_thumbnails(
                    topic_title=st.session_state["selected_topic_title"],
                    pillar_id=st.session_state["selected_pillar_id"],
                    exam_track=st.session_state["selected_exam_track"],
                    voice_mode=st.session_state["voice_mode"],
                    visual_theme_key=st.session_state["visual_theme_key"],
                    scene_count=4,
                    force_regenerate_thumbs=force_fresh_3d_chk,
                    target_class_label=st.session_state["target_class_label"],
                    target_subject_label=st.session_state["target_subject_label"],
                    selected_board=st.session_state["selected_board"],
                    selected_chapter=st.session_state["selected_chapter"],
                    video_category=st.session_state["video_category"],
                    duration_badge=st.session_state["duration_badge"],
                )
                st.session_state["current_blueprint"] = active_bp
            active_bp["voice_mode"] = st.session_state["voice_mode"]
            active_bp["visual_theme_key"] = st.session_state["visual_theme_key"]
            active_bp["class_badge_text"] = infer_class_badge_label(
                exam_track=active_bp.get("exam_track", ""),
                topic_title=active_bp.get("topic_title", ""),
                class_override=st.session_state["target_class_label"],
                subject_override=st.session_state["target_subject_label"],
            )
            rendered_draft = render_full_topperlab_project(
                active_bp,
                short_max_scenes=4,
                bgm_enabled=bool(st.session_state.get("bgm_enabled", True)),
                force_live_images=force_fresh_3d_chk,
                auto_veo_broll=auto_veo_step3_chk,
            )
            st.session_state["current_draft"] = rendered_draft
            st.session_state["seo_bundle"] = generate_student_seo_bundle(
                video_title=rendered_draft["topic_title"],
                exam_track=rendered_draft["exam_track"],
                scenes=rendered_draft["scenes"],
                resource_links=st.session_state["resource_links"],
                board=rendered_draft.get("selected_board", st.session_state["selected_board"]),
                class_name=rendered_draft.get("target_class_label", st.session_state["target_class_label"]),
                subject=rendered_draft.get("target_subject_label", st.session_state["target_subject_label"]),
                chapter_name=rendered_draft.get("selected_chapter", st.session_state["selected_chapter"]),
                video_category=rendered_draft.get("video_category", st.session_state["video_category"]),
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
                    fc1, fc2 = st.columns(2)
                    with fc1:
                        ed_formula = st.text_input(
                            f"📐 Fly-In Formula Card (Scene {sid:02d}):",
                            value=sc.get("formula_badge", ""),
                            key=f"form_{sid}",
                        )
                    with fc2:
                        ed_tip = st.text_input(
                            f"⚡ Fly-In Quick Tip / Hack (Scene {sid:02d}):",
                            value=sc.get("quick_tip", ""),
                            key=f"tip_{sid}",
                        )
                    ed_narr = st.text_area(f"🎙️ Expressive Narration (Scene {sid:02d}):", value=sc["narration"], key=f"narr_{sid}", height=90)
                    ed_img_p = st.text_area(f"🎒 Friendly 3D Classroom Model Prompt (Scene {sid:02d}):", value=sc["image_3d_prompt"], key=f"imgp_{sid}", height=75)
                    regen_img_chk = st.checkbox("Regenerate Bright 3D Model Image via Nano Banana", value=False, key=f"rg_{sid}")
                    flow_upload = st.file_uploader(
                        f"🎞️ Optional: Drop Google Flow / Veo `.mp4` Motion Clip for Scene {sid:02d}:",
                        type=["mp4"],
                        key=f"flow_up_{sid}",
                    )
                    if st.button(f"🔄 Update Scene {sid:02d} & Re-Stitch Master Videos", key=f"upd_{sid}", type="primary"):
                        with st.spinner(f"Updating Scene {sid:02d} (Voice + BGM + Fly-In Cards) & re-stitching 16:9 + 9:16 videos..."):
                            motion_bytes = flow_upload.read() if flow_upload is not None else None
                            updated = update_single_faceless_scene(
                                draft_state=draft,
                                scene_id=sid,
                                new_narration=ed_narr,
                                new_3d_prompt=ed_img_p,
                                regenerate_3d_image=regen_img_chk,
                                uploaded_motion_bytes=motion_bytes,
                                new_formula_badge=ed_formula,
                                new_quick_tip=ed_tip,
                                bgm_enabled=bool(st.session_state.get("bgm_enabled", True)),
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
                "📄 1-Page Formula & Quick-Tip Cheat Sheet (PDF)",
                "📊 99%iler Active-Recall & Revision Tracker (Sheet)",
                "📚 Recommended NCERT / ICSE / JEE / NEET Book (Affiliate)",
                "🧪 Digital Notes Pack / Mock Test Bundle",
            ],
        )
    with lc2:
        l_lbl = st.text_input("Call-to-Action Label:", placeholder="Download Heights & Distances 1-Page Formula Sheet")
    with lc3:
        l_url = st.text_input("URL (Google Drive / Sheet / Gumroad / Amazon):", placeholder="https://drive.google.com/...")
    with lc4:
        st.write("")
        if st.button("➕ Add Link", use_container_width=True) and l_lbl.strip() and l_url.strip():
            st.session_state["resource_links"].append(
                {"category": strip_3d_text(l_cat), "label": strip_3d_text(l_lbl.strip()), "url": l_url.strip()}
            )
            st.session_state["seo_bundle"] = None
            st.rerun()

    if st.session_state["resource_links"]:
        st.dataframe(st.session_state["resource_links"], use_container_width=True, hide_index=True)

    st.divider()
    st.subheader("📝 4.2 Auto-Generated Clean SEO Description, Chapter Timestamps, Hashtags & Pinned Comment")
    active_title = strip_3d_text(draft["topic_title"] if draft else st.session_state["selected_topic_title"])
    active_track = strip_3d_text(draft["exam_track"] if draft else st.session_state["selected_exam_track"])
    active_scenes = draft["scenes"] if draft else []
    active_board = (draft.get("selected_board") if draft else None) or st.session_state.get("selected_board", "CBSE")
    active_class = (draft.get("target_class_label") if draft else None) or st.session_state.get("target_class_label", "Class 10")
    active_subject = (draft.get("target_subject_label") if draft else None) or st.session_state.get("target_subject_label", "Mathematics")
    active_chapter = (draft.get("selected_chapter") if draft else None) or st.session_state.get("selected_chapter", "")
    active_vid_cat = (draft.get("video_category") if draft else None) or st.session_state.get("video_category", "syllabus_chapter")

    seo_fp = f"{active_title}|{active_board}|{active_class}|{active_subject}|{active_chapter}|{active_vid_cat}|{len(st.session_state['resource_links'])}"
    if st.button("✨ Refresh Clean SEO Copy, Hashtags & Timestamps", use_container_width=True) or st.session_state["seo_bundle"] is None or st.session_state.get("_seo_fp") != seo_fp:
        st.session_state["_seo_fp"] = seo_fp
        st.session_state["seo_bundle"] = generate_student_seo_bundle(
            video_title=active_title,
            exam_track=active_track,
            scenes=active_scenes,
            resource_links=st.session_state["resource_links"],
            board=active_board,
            class_name=active_class,
            subject=active_subject,
            chapter_name=active_chapter,
            video_category=active_vid_cat,
        )

    seo = st.session_state["seo_bundle"]
    st.text_input("🎬 Final Clean Video Title (Zero '3D' text):", value=active_title, disabled=True)
    st.text_input("🏷️ Dynamic Chapter & Board Hashtags (Included in Description & Short):", value=seo["hashtags_str"])
    sc1, sc2 = st.columns(2)
    with sc1:
        yt_desc_box = st.text_area("▶️ YouTube Long-Form Description (Timestamps + PDF Links + Hashtags):", value=seo["youtube_description"], height=225)
        pin_box = st.text_area("📌 High-Conversion Pinned Comment:", value=seo["pinned_comment"], height=120)
    with sc2:
        short_cap_box = st.text_area("⚡ YouTube Shorts / IG & FB Reel Caption:", value=seo["short_reel_caption"], height=225)
        tags_box = st.text_input("🔍 YouTube SEO Keyword Tags (Comma-Separated):", value=seo["seo_tags_str"])

    st.divider()
    st.subheader("🚀 4.3 Direct Publish or Native Cloud Schedule (`@TopperLab3D`)")
    dc1, dc2 = st.columns(2)
    with dc1:
        do_yt_long = st.checkbox("▶️ YouTube Long-Form (`16:9` + Custom Thumbnail + Chapters)", value=True)
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

    plc1, plc2, plc3 = st.columns([1.2, 1.2, 1.6])
    with plc1:
        pub_boards = st.multiselect(
            "📚 Auto-Add to Board Playlists:",
            options=CURRICULUM_BOARDS,
            default=[active_board] if active_board in CURRICULUM_BOARDS else CURRICULUM_BOARDS,
            help="Automatically assigns this video to the matching Board + Class + Subject Foundation Playlist!",
        )
    with plc2:
        pub_class = st.selectbox(
            "🎓 Target Class:",
            options=CURRICULUM_CLASSES,
            index=CURRICULUM_CLASSES.index(active_class) if active_class in CURRICULUM_CLASSES else 2,
        )
    with plc3:
        pub_subject = st.selectbox(
            "🔬 Target Subject:",
            options=ALL_CURRICULUM_SUBJECTS,
            index=ALL_CURRICULUM_SUBJECTS.index(active_subject) if active_subject in ALL_CURRICULUM_SUBJECTS else 0,
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
                        target_boards=pub_boards,
                        target_class=pub_class,
                        target_subject=pub_subject,
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
