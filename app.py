"""
OMNI STUDIO — Generic Multi-Niche Multi-Agent AI Video Engine on Streamlit (`app.py`)
=====================================================================================
Mobile- and tablet-responsive, sequential 4-step multi-agent studio:
  1. SEO & Hooks  ➔  2. Scene Scripting  ➔  3. Media Rendering  ➔  4. YT Publish

State is strictly preserved in `st.session_state` and persisted to SQLite (`storage/omni_studio.db`),
with heavy rendering & resumable YouTube uploads executed asynchronously via `worker.py`.
"""

from __future__ import annotations

import datetime
import hashlib
import hmac
import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import streamlit as st

from backend.agent1_seo_storyboard import run_agent1_seo_and_storyboard
from backend.agent2_scene_scripter import enhance_all_scenes_to_cinema, run_agent2_scene_scripting
from backend.agent3_media_composer import (
    estimate_render_cost_usd,
    regenerate_single_scene_frame,
    run_agent3_keyframe_preview_batch,
    run_agent3_media_pipeline,
    select_hybrid_hero_scene_indices,
)
from backend.agent4_youtube_publisher import (
    attach_thumbnail_to_published_video,
    build_short_funnel_description,
    build_youtube_oauth_url,
    create_youtube_playlist,
    exchange_oauth_code_and_store,
    format_channel_streamlit_secret_toml,
    get_valid_youtube_credentials,
    import_youtube_token_json,
    list_connected_youtube_channels,
    list_user_youtube_playlists,
    run_agent4_youtube_publish,
)
from backend.config import (
    BGM_SCORE_PRESETS,
    CINEMA_STYLE_PRESETS,
    DEFAULT_BGM_PRESET,
    DEFAULT_CINEMA_PRESET,
    SUPPORTED_LANGUAGES,
    SUPPORTED_NICHES,
    OmniStudioConfig,
    format_flow_prompts_export_txt,
    format_timestamp,
    sanitize_slug,
    sync_streamlit_secrets_to_env,
)
from backend.schemas import Agent1Output, Agent2Output, Agent3Output, Agent4Output, SceneClipSpec
from render_engine.thumbnail_studio import generate_high_ctr_thumbnail
from storage.cloud_sync import (
    ensure_project_renders_local,
    is_cloud_sync_enabled,
    restore_projects_from_gcs_once,
)
from storage.db import get_db
from worker import BudgetLimitExceededError, get_worker_manager

# ==============================================================================
# PAGE CONFIG & MODERN HIGH-CONTRAST 3D STUDIO STYLING
# ==============================================================================
st.set_page_config(
    page_title="OMNI STUDIO — AI Video Studio",
    page_icon="🎬",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown(
    """
    <style>
    /* Modern high-contrast dark studio theme with tactile 3D buttons & solid status panels */
    .stApp {
        background: radial-gradient(circle at 18% 0%, #111c36 0%, #090d16 55%, #070a12 100%);
    }
    .block-container {
        padding-top: 1.05rem !important;
        padding-bottom: 2.8rem !important;
        max-width: 1120px !important;
    }

    /* Elevated Studio Header */
    .omni-header {
        background: linear-gradient(135deg, #111b33 0%, #172542 52%, #0f2744 100%);
        border: 1px solid rgba(96, 165, 250, 0.34);
        border-radius: 18px;
        padding: 18px 22px;
        margin-bottom: 14px;
        box-shadow: 0 10px 28px rgba(0, 0, 0, 0.42), inset 0 1px 0 rgba(255, 255, 255, 0.10);
    }
    .omni-header-top {
        display: flex;
        justify-content: space-between;
        align-items: center;
        flex-wrap: wrap;
        gap: 10px;
    }
    .omni-header h1 {
        margin: 0;
        font-size: 1.62rem;
        font-weight: 800;
        letter-spacing: 0.35px;
        color: #FFFFFF;
    }
    .omni-meta-chips {
        display: flex;
        flex-wrap: wrap;
        gap: 8px;
        margin-top: 10px;
    }
    .omni-chip {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        padding: 4px 12px;
        border-radius: 999px;
        background: rgba(15, 23, 42, 0.82);
        border: 1px solid rgba(148, 163, 184, 0.28);
        color: #E2E8F0;
        font-size: 0.84rem;
        font-weight: 600;
    }
    .omni-chip-cloud {
        background: rgba(14, 116, 144, 0.28);
        border-color: rgba(56, 189, 248, 0.45);
        color: #BAE6FD;
    }

    /* Sleek Thin Step Progress Track */
    .omni-step-track {
        height: 6px;
        width: 100%;
        background: #162033;
        border-radius: 999px;
        overflow: hidden;
        margin: 4px 0 12px 0;
        box-shadow: inset 0 1px 3px rgba(0, 0, 0, 0.65);
    }
    .omni-step-fill {
        height: 100%;
        border-radius: 999px;
        background: linear-gradient(90deg, #2563EB 0%, #0EA5E9 55%, #14B8A6 100%);
        transition: width 0.35s ease;
    }

    /* High-Contrast Tactile 3D Primary Buttons (Pure White on Deep Royal Blue -> WCAG AAA!) */
    div.stButton > button[kind="primary"],
    div.stButton > button[data-testid="stBaseButton-primary"],
    div[data-testid="stFormSubmitButton"] > button {
        background: linear-gradient(180deg, #3B82F6 0%, #2563EB 58%, #1D4ED8 100%) !important;
        color: #FFFFFF !important;
        border: 1px solid #60A5FA !important;
        border-radius: 12px !important;
        font-weight: 700 !important;
        letter-spacing: 0.2px !important;
        padding: 0.58rem 1.05rem !important;
        text-shadow: 0 1px 2px rgba(15, 23, 42, 0.55) !important;
        box-shadow: 0 4px 0 #1E3A8A, 0 8px 18px rgba(37, 99, 235, 0.38), inset 0 1px 0 rgba(255, 255, 255, 0.30) !important;
        transition: transform 0.10s ease, box-shadow 0.10s ease, filter 0.15s ease !important;
    }
    div.stButton > button[kind="primary"]:hover:not(:disabled),
    div.stButton > button[data-testid="stBaseButton-primary"]:hover:not(:disabled),
    div[data-testid="stFormSubmitButton"] > button:hover:not(:disabled) {
        filter: brightness(1.09) !important;
        transform: translateY(-1px) !important;
        box-shadow: 0 5px 0 #1E3A8A, 0 10px 22px rgba(59, 130, 246, 0.48), inset 0 1px 0 rgba(255, 255, 255, 0.35) !important;
    }
    div.stButton > button[kind="primary"]:active:not(:disabled),
    div.stButton > button[data-testid="stBaseButton-primary"]:active:not(:disabled),
    div[data-testid="stFormSubmitButton"] > button:active:not(:disabled) {
        transform: translateY(3px) !important;
        box-shadow: 0 1px 0 #1E3A8A, 0 2px 6px rgba(37, 99, 235, 0.30) !important;
    }

    /* High-Contrast Tactile 3D Secondary Buttons (Crisp White-Slate on Elevated Dark Navy) */
    div.stButton > button[kind="secondary"],
    div.stButton > button[data-testid="stBaseButton-secondary"] {
        background: linear-gradient(180deg, #243247 0%, #172133 100%) !important;
        color: #F8FAFC !important;
        border: 1px solid #3B4E6B !important;
        border-radius: 12px !important;
        font-weight: 600 !important;
        padding: 0.55rem 0.95rem !important;
        box-shadow: 0 3px 0 #0B1120, 0 5px 12px rgba(0, 0, 0, 0.42), inset 0 1px 0 rgba(255, 255, 255, 0.12) !important;
        transition: transform 0.10s ease, box-shadow 0.10s ease, border-color 0.15s ease !important;
    }
    div.stButton > button[kind="secondary"]:hover:not(:disabled),
    div.stButton > button[data-testid="stBaseButton-secondary"]:hover:not(:disabled) {
        background: linear-gradient(180deg, #2D3F59 0%, #1C2940 100%) !important;
        border-color: #60A5FA !important;
        color: #FFFFFF !important;
        transform: translateY(-1px) !important;
        box-shadow: 0 4px 0 #0B1120, 0 7px 16px rgba(15, 23, 42, 0.55), inset 0 1px 0 rgba(255, 255, 255, 0.18) !important;
    }
    div.stButton > button[kind="secondary"]:active:not(:disabled),
    div.stButton > button[data-testid="stBaseButton-secondary"]:active:not(:disabled) {
        transform: translateY(2px) !important;
        box-shadow: 0 1px 0 #0B1120 !important;
    }

    /* Tactile 3D Download Buttons (Pure White on Deep Emerald-Teal) */
    div.stDownloadButton > button {
        background: linear-gradient(180deg, #0D9488 0%, #0F766E 100%) !important;
        color: #FFFFFF !important;
        border: 1px solid #2DD4BF !important;
        border-radius: 12px !important;
        font-weight: 700 !important;
        text-shadow: 0 1px 2px rgba(4, 47, 46, 0.55) !important;
        box-shadow: 0 4px 0 #115E59, 0 7px 16px rgba(13, 148, 136, 0.32), inset 0 1px 0 rgba(255, 255, 255, 0.25) !important;
        transition: transform 0.10s ease, box-shadow 0.10s ease !important;
    }
    div.stDownloadButton > button:hover {
        filter: brightness(1.08) !important;
        transform: translateY(-1px) !important;
    }
    div.stDownloadButton > button:active {
        transform: translateY(3px) !important;
        box-shadow: 0 1px 0 #115E59 !important;
    }

    /* Disabled Buttons: Cleanly Muted & Unmistakably Distinct */
    div.stButton > button:disabled {
        background: #111827 !important;
        color: #64748B !important;
        border: 1px solid #1E293B !important;
        box-shadow: none !important;
        transform: none !important;
        opacity: 0.72 !important;
    }
    div.stButton > button p, div.stDownloadButton > button p {
        color: inherit !important;
        font-weight: inherit !important;
    }

    /* Solid Structured Processing Deck & Stage Cards */
    .omni-process-deck {
        background: linear-gradient(180deg, #111b31 0%, #0d1526 100%);
        border: 1px solid rgba(96, 165, 250, 0.38);
        border-radius: 16px;
        padding: 18px 20px;
        margin: 14px 0 18px 0;
        box-shadow: 0 10px 26px rgba(0, 0, 0, 0.45), inset 0 1px 0 rgba(255, 255, 255, 0.08);
    }
    .omni-process-hdr {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 12px;
        flex-wrap: wrap;
        gap: 8px;
    }
    .omni-process-title {
        font-size: 1.08rem;
        font-weight: 800;
        color: #FFFFFF;
        display: inline-flex;
        align-items: center;
        gap: 9px;
    }
    .omni-live-dot {
        width: 10px;
        height: 10px;
        border-radius: 50%;
        background: #38BDF8;
        box-shadow: 0 0 10px #38BDF8;
        display: inline-block;
        animation: omniPulse 1.4s ease-in-out infinite;
    }
    .omni-done-dot {
        width: 10px;
        height: 10px;
        border-radius: 50%;
        background: #10B981;
        display: inline-block;
    }
    @keyframes omniPulse {
        0%, 100% { opacity: 1; transform: scale(1); }
        50% { opacity: 0.45; transform: scale(1.25); }
    }
    .omni-stage-row {
        display: flex;
        justify-content: space-between;
        align-items: center;
        gap: 12px;
        padding: 10px 14px;
        border-radius: 12px;
        background: #0F172A;
        border: 1px solid #1E293B;
        margin-bottom: 8px;
        font-size: 0.90rem;
    }
    .omni-stage-row-active {
        background: linear-gradient(90deg, rgba(37, 99, 235, 0.22) 0%, rgba(15, 23, 42, 0.95) 100%);
        border-color: rgba(59, 130, 246, 0.55);
    }
    .omni-stage-row-done {
        border-color: rgba(16, 185, 129, 0.35);
    }
    .omni-stage-name {
        color: #F8FAFC;
        font-weight: 700;
    }
    .omni-stage-detail {
        color: #CBD5E1;
        font-size: 0.85rem;
        text-align: right;
        display: inline-flex;
        align-items: center;
        gap: 8px;
    }
    .omni-badge {
        padding: 2px 10px;
        border-radius: 999px;
        font-size: 0.76rem;
        font-weight: 700;
        white-space: nowrap;
    }
    .omni-badge-done { background: #065F46; color: #ECFDF5; border: 1px solid #10B981; }
    .omni-badge-run  { background: #1D4ED8; color: #EFF6FF; border: 1px solid #60A5FA; }
    .omni-badge-wait { background: #1E293B; color: #94A3B8; border: 1px solid #334155; }
    .omni-badge-err  { background: #991B1B; color: #FEF2F2; border: 1px solid #F87171; }

    /* Live Cost Estimator Strip */
    .omni-cost-card {
        display: flex;
        justify-content: space-between;
        align-items: center;
        flex-wrap: wrap;
        gap: 10px;
        padding: 12px 16px;
        margin: 8px 0 12px 0;
        border-radius: 14px;
        background: linear-gradient(90deg, rgba(16, 185, 129, 0.14) 0%, rgba(15, 23, 42, 0.92) 60%);
        border: 1px solid rgba(52, 211, 153, 0.40);
        box-shadow: 0 4px 14px rgba(0, 0, 0, 0.28);
    }
    .omni-cost-main {
        color: #ECFDF5;
        font-size: 0.96rem;
        font-weight: 700;
    }
    .omni-cost-sub {
        color: #CBD5E1;
        font-size: 0.84rem;
    }
    .omni-cost-save {
        padding: 3px 10px;
        border-radius: 999px;
        background: #065F46;
        color: #ECFDF5;
        border: 1px solid #34D399;
        font-size: 0.78rem;
        font-weight: 700;
    }

    /* Elevated Metric Tiles & Section Headings */
    div[data-testid="stMetric"] {
        background: linear-gradient(180deg, #141E33 0%, #0E1627 100%);
        border: 1px solid #24334D;
        border-radius: 14px;
        padding: 12px 16px;
        box-shadow: 0 4px 14px rgba(0, 0, 0, 0.28);
    }
    div[data-testid="stExpander"] {
        border: 1px solid #22304A !important;
        border-radius: 14px !important;
        background: rgba(15, 23, 42, 0.58) !important;
    }

    /* Matching 3D Studio Lock Screen Card */
    .omni-lock-hero {
        text-align: center;
        padding: 26px 24px 18px 24px;
        background: linear-gradient(155deg, #121e38 0%, #0f172a 60%, #0b1324 100%);
        border: 1px solid rgba(96, 165, 250, 0.38);
        border-radius: 20px 20px 6px 6px;
        box-shadow: 0 14px 36px rgba(0, 0, 0, 0.52), inset 0 1px 0 rgba(255, 255, 255, 0.12);
        margin-bottom: -10px;
    }
    .omni-lock-emblem {
        width: 68px;
        height: 68px;
        margin: 0 auto 14px auto;
        border-radius: 18px;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 2rem;
        background: linear-gradient(180deg, #3B82F6 0%, #1D4ED8 100%);
        border: 1px solid #60A5FA;
        box-shadow: 0 5px 0 #1E3A8A, 0 12px 26px rgba(37, 99, 235, 0.45), inset 0 1px 0 rgba(255, 255, 255, 0.35);
    }
    .omni-lock-hero h2 {
        margin: 0;
        color: #FFFFFF;
        font-size: 1.55rem;
        font-weight: 800;
        letter-spacing: 0.4px;
    }
    .omni-lock-hero p {
        margin: 6px 0 0 0;
        color: #94A3B8;
        font-size: 0.92rem;
    }
    div[data-testid="stForm"] {
        background: linear-gradient(180deg, #0f172a 0%, #0b1222 100%) !important;
        border: 1px solid rgba(96, 165, 250, 0.32) !important;
        border-top: none !important;
        border-radius: 0 0 20px 20px !important;
        padding: 18px 24px 24px 24px !important;
        box-shadow: 0 18px 38px rgba(0, 0, 0, 0.50) !important;
    }
    @media (max-width: 768px) {
        .block-container {
            padding-left: 0.75rem !important;
            padding-right: 0.75rem !important;
        }
        .omni-header h1 {
            font-size: 1.28rem;
        }
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# ==============================================================================
# ISOLATED SESSION STATE INITIALIZATION & SQLITE SYNC
# ==============================================================================
def _init_session_state() -> None:
    defaults: Dict[str, Any] = {
        "omni_step": 0,
        "omni_project_id": None,
        "omni_topic": "",
        "omni_niche": SUPPORTED_NICHES[2],  # AI & Future Tech default
        "omni_language": SUPPORTED_LANGUAGES[0],
        "omni_cinema_preset": DEFAULT_CINEMA_PRESET,
        "omni_bgm_preset": DEFAULT_BGM_PRESET,
        "omni_custom_bgm_path": None,
        "omni_target_minutes": 6.0,
        "omni_channel_id": "",
        "omni_channel_title": "",
        "omni_playlist_id": "NONE",
        "omni_playlist_title": "(No Playlist)",
        "newly_connected_secret_toml": "",
        "agent1_output": None,      # Dict matching Agent1Output
        "agent2_output": None,      # Dict matching Agent2Output
        "agent3_output": None,      # Dict matching Agent3Output
        "agent4_output": None,      # Dict matching Agent4Output
        "render_task_key": None,
        "publish_task_key": None,
        "publish_balloons_shown": False,
        "scene_page": 1,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


def _clear_step1_widget_keys() -> None:
    """Clears cached Step 1 form widget state when switching/regenerating a project."""
    for k in list(st.session_state.keys()):
        if k.startswith(("a1_", "beat_", "sc_")):
            st.session_state.pop(k, None)


def _reset_workspace() -> None:
    _clear_step1_widget_keys()
    for k in [
        "omni_step",
        "omni_project_id",
        "omni_topic",
        "agent1_output",
        "agent2_output",
        "agent3_output",
        "agent4_output",
        "render_task_key",
        "publish_task_key",
        "publish_balloons_shown",
        "scene_page",
    ]:
        st.session_state.pop(k, None)
    _init_session_state()


def _load_project_into_session(project_id: str) -> None:
    db = get_db()
    proj = db.get_project(project_id)
    if not proj:
        return
    _clear_step1_widget_keys()
    st.session_state["omni_project_id"] = proj["id"]
    st.session_state["omni_topic"] = proj["topic"]
    st.session_state["omni_niche"] = proj["niche"] if proj["niche"] in SUPPORTED_NICHES else SUPPORTED_NICHES[0]
    st.session_state["omni_language"] = (
        proj["language_tone"] if proj["language_tone"] in SUPPORTED_LANGUAGES else SUPPORTED_LANGUAGES[0]
    )
    st.session_state["omni_target_minutes"] = float(proj.get("target_minutes") or 6.0)
    if proj.get("target_channel_id"):
        st.session_state["omni_channel_id"] = proj.get("target_channel_id") or ""
        st.session_state["omni_channel_title"] = proj.get("target_channel_title") or ""
    if proj.get("target_playlist_id"):
        st.session_state["omni_playlist_id"] = proj.get("target_playlist_id") or "NONE"
        st.session_state["omni_playlist_title"] = proj.get("target_playlist_title") or "(No Playlist)"
    st.session_state["agent1_output"] = proj.get("agent1_data")
    st.session_state["agent2_output"] = proj.get("agent2_data")
    st.session_state["agent3_output"] = proj.get("agent3_data")
    st.session_state["agent4_output"] = proj.get("agent4_data")
    st.session_state["omni_step"] = max(0, min(4, int(proj.get("current_step") or 1)))
    st.session_state["publish_balloons_shown"] = False
    # Restore finished video/thumbnail from Google Cloud Storage on-demand if missing locally
    if proj.get("agent3_data"):
        ensure_project_renders_local(project_id, proj["agent3_data"])


# ==============================================================================
# STUDIO PIN LOCK SCREEN (HIGH-CONTRAST 3D THEME GATE)
# ==============================================================================
_PIN_SALT = "omni_studio_pin_v1:"
_DEFAULT_PIN_SHA256 = "f03dabdfb92e77221be8899d6488b0ea8bd80f4110e2a41fff46dc297dac854e"


def _verify_studio_pin(entered_pin: str) -> bool:
    candidate = (entered_pin or "").strip()
    if not candidate:
        return False
    override_pin = os.getenv("STUDIO_LOCK_PIN", "").strip()
    if override_pin:
        return hmac.compare_digest(candidate, override_pin)
    digest = hashlib.sha256(f"{_PIN_SALT}{candidate}".encode("utf-8")).hexdigest()
    return hmac.compare_digest(digest, _DEFAULT_PIN_SHA256)


def _enforce_studio_pin_lock() -> None:
    if st.session_state.get("omni_studio_unlocked", False):
        return

    # Hide sidebar completely while locked so private projects & channels stay invisible
    st.markdown(
        """
        <style>
        [data-testid="stSidebar"], [data-testid="collapsedControl"] {
            display: none !important;
        }
        div[data-testid="stTextInput"] input {
            text-align: center !important;
            font-size: 1.45rem !important;
            letter-spacing: 0.55rem !important;
            font-weight: 700 !important;
            padding: 0.65rem 1rem !important;
            background: #090F1E !important;
            border: 1px solid #334155 !important;
            border-radius: 12px !important;
            color: #FFFFFF !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    st.markdown("<div style='height: 6vh;'></div>", unsafe_allow_html=True)
    _, lock_col, _ = st.columns([1.0, 1.35, 1.0])
    with lock_col:
        st.markdown(
            """
            <div class="omni-lock-hero">
                <div class="omni-lock-emblem">🔐</div>
                <h2>OMNI STUDIO</h2>
                <p>Private Creator Workspace · Enter your PIN to unlock</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        with st.form("omni_pin_lock_form", clear_on_submit=False):
            pin_val = st.text_input(
                "Studio PIN",
                type="password",
                max_chars=8,
                placeholder="• • • •",
                label_visibility="collapsed",
                key="omni_pin_input",
            )
            submitted = st.form_submit_button("🔓 Unlock Studio", use_container_width=True)
            if submitted:
                if _verify_studio_pin(pin_val):
                    st.session_state["omni_studio_unlocked"] = True
                    st.session_state.pop("omni_pin_error", None)
                    st.rerun()
                else:
                    st.session_state["omni_pin_error"] = True

        if st.session_state.get("omni_pin_error"):
            st.error("❌ Incorrect PIN. Please try again.")

    st.stop()


sync_streamlit_secrets_to_env()
_enforce_studio_pin_lock()
_init_session_state()
cfg = OmniStudioConfig()
db = get_db()
worker = get_worker_manager()

# Automatically restore any cloud-backed projects on fresh container startup
restore_projects_from_gcs_once(db)
cloud_sync_active = is_cloud_sync_enabled()

# Hydrate all connected YouTube channels from SQLite / Streamlit Secrets / local files
all_connected_channels = list_connected_youtube_channels(cfg, db)
if all_connected_channels and not st.session_state.get("omni_channel_id"):
    first_ch = all_connected_channels[0]
    st.session_state["omni_channel_id"] = first_ch.get("channel_id") or ""
    st.session_state["omni_channel_title"] = first_ch.get("channel_title") or "Connected YouTube Channel"

# Handle OAuth 2.0 callback `?code=...` cleanly if Google redirected back to Streamlit
query_code = st.query_params.get("code")
if query_code and st.session_state.get("_oauth_last_code") != str(query_code):
    # Recover exact redirect_uri from OAuth `state` parameter (works even in a brand-new browser tab!)
    query_state = str(st.query_params.get("state") or "").strip()
    cb_redirect = (
        query_state
        if query_state.startswith(("http://", "https://"))
        else (st.session_state.get("omni_oauth_redirect_uri") or "https://onebillionviews.streamlit.app")
    )
    ok_cb, msg_cb, saved_ch = exchange_oauth_code_and_store(
        str(query_code),
        cfg.youtube_client_secrets,
        redirect_uri=cb_redirect,
        db=db,
        config=cfg,
    )
    st.session_state["_oauth_last_code"] = str(query_code)
    try:
        st.query_params.clear()
    except Exception:
        pass
    if ok_cb and saved_ch:
        st.session_state["omni_channel_id"] = saved_ch.get("channel_id") or ""
        st.session_state["omni_channel_title"] = saved_ch.get("channel_title") or ""
        st.session_state["omni_playlist_id"] = "NONE"
        st.session_state["omni_playlist_title"] = "(No Playlist)"
        st.session_state["newly_connected_secret_toml"] = format_channel_streamlit_secret_toml(saved_ch)
        all_connected_channels = list_connected_youtube_channels(cfg, db)
        st.toast(msg_cb, icon="✅")
    else:
        st.toast(f"OAuth exchange note: {msg_cb}", icon="⚠️")


def _format_channel_label(ch: Dict[str, Any], *, with_icon: bool = True) -> str:
    """Formats a clean, human-readable YouTube channel label with ZERO raw `UC...` GUID clutter."""
    ctitle = (ch.get("channel_title") or "Connected Channel").strip()
    handle = (ch.get("account_email") or (ch.get("token_dict") or {}).get("connected_custom_url") or "").strip()
    if handle and not handle.startswith("@") and "@" not in handle:
        handle = f"@{handle}"
    prefix = "📺 " if with_icon else ""
    if handle and handle.lower() not in ctitle.lower():
        return f"{prefix}{ctitle} ({handle})"
    return f"{prefix}{ctitle}"


def _render_connect_channel_drawer(prefix: str, connected_channels: List[Dict[str, Any]]) -> None:
    """Clean multi-channel YouTube sign-in & management drawer."""
    st.caption(
        "Connect as many YouTube channels as you want. Each channel is saved independently."
    )
    sel_redir = "https://onebillionviews.streamlit.app"
    st.session_state["omni_oauth_redirect_uri"] = sel_redir

    auth_url, auth_msg = build_youtube_oauth_url(
        cfg.youtube_client_secrets,
        redirect_uri=sel_redir,
        config=cfg,
        db=db,
    )
    if auth_url:
        st.markdown(
            f"1. **[🌐 Sign In with Google & Select Your YouTube Channel ↗]({auth_url})**\n"
            f"2. Pick your channel and click **Allow** — you will return here automatically."
        )
        with st.expander("⚙️ Manual Sign-In & Cloud Backup Keys", expanded=bool(st.session_state.get("newly_connected_secret_toml"))):
            code_in = st.text_input(
                "Paste Redirected URL or Code (only needed if auto-return didn't run):",
                placeholder="Paste URL or authorization code...",
                key=f"{prefix}_oauth_code_in",
            )
            if st.button("✅ Connect Channel", type="primary", use_container_width=True, key=f"{prefix}_btn_exch"):
                ok_ex, msg_ex, saved_ch = exchange_oauth_code_and_store(
                    code_in,
                    cfg.youtube_client_secrets,
                    redirect_uri=sel_redir,
                    db=db,
                    config=cfg,
                )
                if ok_ex and saved_ch:
                    st.session_state["omni_channel_id"] = saved_ch.get("channel_id") or ""
                    st.session_state["omni_channel_title"] = saved_ch.get("channel_title") or ""
                    st.session_state["omni_playlist_id"] = "NONE"
                    st.session_state["omni_playlist_title"] = "(No Playlist)"
                    st.session_state["newly_connected_secret_toml"] = format_channel_streamlit_secret_toml(saved_ch)
                    st.success(msg_ex)
                    st.rerun()
                else:
                    st.error(msg_ex)
            if connected_channels:
                all_toml_blocks = "\n\n".join(format_channel_streamlit_secret_toml(c) for c in connected_channels)
                st.caption(
                    f"Copy & paste into **Streamlit Cloud → Manage app → Settings → Secrets** to keep all "
                    f"{len(connected_channels)} channel(s) permanently signed in:"
                )
                st.code(all_toml_blocks, language="toml")
                st.download_button(
                    "⬇️ Download Channel Backup (.toml)",
                    data=lambda s=all_toml_blocks: s.encode("utf-8"),
                    file_name="omni_studio_youtube_secrets.toml",
                    mime="text/plain",
                    use_container_width=True,
                    key=f"{prefix}_dl_all_secrets_toml",
                )
    else:
        st.info("YouTube sign-in is not configured yet.")

    if connected_channels:
        st.markdown("---")
        rem_opts: Dict[str, str] = {}
        for c in connected_channels:
            base_lbl = _format_channel_label(c, with_icon=False)
            lbl_u = base_lbl
            n_dup = 2
            while lbl_u in rem_opts:
                lbl_u = f"{base_lbl} #{n_dup}"
                n_dup += 1
            rem_opts[lbl_u] = str(c.get("channel_id") or c.get("provider") or "")
        rc1, rc2 = st.columns([1.6, 1.0])
        with rc1:
            rem_pick = st.selectbox("🗑️ Disconnect a Channel:", options=list(rem_opts.keys()), key=f"{prefix}_rem_sel")
        with rc2:
            st.markdown("<div style='height:26px'></div>", unsafe_allow_html=True)
            if st.button("Disconnect", use_container_width=True, key=f"{prefix}_rem_btn"):
                target_rm = rem_opts[rem_pick]
                db.delete_youtube_channel(str(target_rm))
                if st.session_state.get("omni_channel_id") == target_rm:
                    st.session_state["omni_channel_id"] = ""
                    st.session_state["omni_channel_title"] = ""
                    st.session_state["omni_playlist_id"] = "NONE"
                    st.session_state["omni_playlist_title"] = "(No Playlist)"
                st.rerun()


def _friendly_project_status(status: str) -> str:
    s = (status or "").lower()
    if "publish" in s:
        return "Published"
    if "rendered" in s:
        return "Video Ready"
    if "step3" in s or "step2" in s:
        return "Script Ready"
    if "step1_ready" in s:
        return "Plan Ready"
    return "Draft"


# ==============================================================================
# COMPACT SIDEBAR: SAVED PROJECTS & CLOUD SYNC
# ==============================================================================
with st.sidebar:
    st.markdown("### 🗂️ My Projects")
    if st.button("➕ New Video Project", use_container_width=True, type="primary"):
        _reset_workspace()
        st.rerun()

    recent_projects = db.list_projects(limit=15)
    if recent_projects:
        st.caption("Open a saved project:")
        for rp in recent_projects:
            status_lbl = _friendly_project_status(rp.get("status", ""))
            lbl = f"🎬 {rp['topic'][:26]} · {status_lbl}"
            if st.button(lbl, key=f"load_proj_{rp['id']}", use_container_width=True):
                with st.status(f"Opening '{rp['topic'][:30]}'...", expanded=False):
                    _load_project_into_session(rp["id"])
                st.rerun()
    else:
        st.caption("No saved projects yet. Start your first video in Step 1!")

    st.markdown("---")
    if cloud_sync_active:
        if st.button("☁️ Refresh Cloud Projects", use_container_width=True):
            with st.status("Syncing projects from Google Cloud...", expanded=False):
                n_restored = restore_projects_from_gcs_once(db, force=True)
            st.toast(f"Cloud sync complete ({n_restored} project(s) updated).", icon="☁️")
            st.rerun()
        st.caption("☁️ Cloud Auto-Save: Active")
    else:
        st.caption("💾 Local Workspace Mode")

    st.markdown("")
    if st.button("🔒 Lock Studio", use_container_width=True, key="btn_lock_studio"):
        st.session_state["omni_studio_unlocked"] = False
        st.session_state.pop("omni_pin_error", None)
        st.rerun()


# ==============================================================================
# TOP HEADER & UNIFIED 3D STUDIO NAVIGATION DOCK
# ==============================================================================
active_ch_lbl = st.session_state.get("omni_channel_title") or "Select Channel"
active_pl_lbl = st.session_state.get("omni_playlist_title") or "No Playlist"
cloud_chip_html = (
    '<span class="omni-chip omni-chip-cloud">☁️ Cloud Auto-Save On</span>'
    if cloud_sync_active
    else ""
)
st.markdown(
    f"""
    <div class="omni-header">
        <div class="omni-header-top">
            <h1>🎬 OMNI STUDIO</h1>
            {cloud_chip_html}
        </div>
        <div class="omni-meta-chips">
            <span class="omni-chip">📺 {active_ch_lbl}</span>
            <span class="omni-chip">📂 {active_pl_lbl}</span>
            <span class="omni-chip">🔗 {len(all_connected_channels)} Channel(s) Connected</span>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

step = int(st.session_state["omni_step"])
steps_meta = [
    (0, "📺 Channel"),
    (1, "✨ Plan"),
    (2, "🎬 Scenes"),
    (3, "🎞️ Studio"),
    (4, "🚀 Publish"),
]

# Sleek unified progress track + single tactile 3D navigation dock (no duplicate stepper rows!)
fill_pct = int(((step + 1) / float(len(steps_meta))) * 100)
st.markdown(
    f'<div class="omni-step-track"><div class="omni-step-fill" style="width:{fill_pct}%;"></div></div>',
    unsafe_allow_html=True,
)

nav_cols = st.columns(5)
max_unlocked = 1  # Both Channel and Topic & Plan are always accessible
if st.session_state.get("agent1_output"):
    max_unlocked = max(max_unlocked, 2)
if st.session_state.get("agent2_output"):
    max_unlocked = max(max_unlocked, 3)
if st.session_state.get("agent3_output"):
    max_unlocked = max(max_unlocked, 4)

for idx, (s_num, s_label) in enumerate(steps_meta):
    with nav_cols[idx]:
        disabled = s_num > max_unlocked
        btn_type = "primary" if s_num == step else "secondary"
        display_lbl = f"✓ {s_label.split(' ', 1)[1]}" if (s_num < step and not disabled) else s_label
        if st.button(display_lbl, key=f"nav_step_{s_num}", use_container_width=True, disabled=disabled, type=btn_type):
            st.session_state["omni_step"] = s_num
            if st.session_state.get("omni_project_id"):
                db.update_project_stage(st.session_state["omni_project_id"], current_step=s_num)
            st.rerun()

st.markdown("")


# ==============================================================================
# PRE-STEP (STEP 0) — CHANNEL & PLAYLIST SELECTOR
# ==============================================================================
if step == 0:
    st.subheader("Select YouTube Channel & Playlist")

    selected_ch_auth_ok = True
    with st.container(border=True):
        if all_connected_channels:
            ch_labels: List[str] = []
            ch_by_label: Dict[str, Optional[Dict[str, Any]]] = {}
            default_ch_idx = 0
            cur_cid = st.session_state.get("omni_channel_id", "")

            for i, ch in enumerate(all_connected_channels):
                cid = ch.get("channel_id") or ""
                base_lbl = _format_channel_label(ch, with_icon=True)
                lbl = base_lbl
                n_dup = 2
                while lbl in ch_by_label:
                    lbl = f"{base_lbl} #{n_dup}"
                    n_dup += 1
                ch_labels.append(lbl)
                ch_by_label[lbl] = ch
                if cid == cur_cid:
                    default_ch_idx = i

            offline_lbl = "🎬 Create Offline / Choose Channel Later"
            ch_labels.append(offline_lbl)
            ch_by_label[offline_lbl] = None

            ch_col, pl_col = st.columns([1.25, 1.0])
            with ch_col:
                picked_ch_lbl = st.selectbox(
                    "📺 Target YouTube Channel:",
                    options=ch_labels,
                    index=default_ch_idx,
                    key="prestep_channel_sel",
                )
                picked_ch = ch_by_label[picked_ch_lbl]
                if picked_ch:
                    new_cid = picked_ch.get("channel_id") or ""
                    new_ctitle = picked_ch.get("channel_title") or "Connected Channel"
                    if new_cid != st.session_state.get("omni_channel_id"):
                        st.session_state["omni_channel_id"] = new_cid
                        st.session_state["omni_channel_title"] = new_ctitle
                        st.session_state["omni_playlist_id"] = "NONE"
                        st.session_state["omni_playlist_title"] = "(No Playlist)"
                        # Smart auto-suggest Religious & Devotional niche/BGM if channel looks devotional
                        low_c = new_ctitle.lower()
                        if any(k in low_c for k in ("shyam", "bhakti", "dharm", "katha", "ram", "krishna", "shiv", "devotion", "spirit", "relig", "temple", "sanatan", "gita")):
                            if "Religious & Devotional" in SUPPORTED_NICHES:
                                st.session_state["omni_niche"] = "Religious & Devotional"
                            for b_k in BGM_SCORE_PRESETS.keys():
                                if "Indian Devotional" in b_k:
                                    st.session_state["omni_bgm_preset"] = b_k
                                    break
                else:
                    st.session_state["omni_channel_id"] = ""
                    st.session_state["omni_channel_title"] = "Offline / Select Later"
                    st.session_state["omni_playlist_id"] = "NONE"
                    st.session_state["omni_playlist_title"] = "(No Playlist)"

            sel_cid = st.session_state.get("omni_channel_id", "")
            sel_creds = None
            if sel_cid:
                sel_creds, _ = get_valid_youtube_credentials(cfg, db, channel_id=sel_cid)
                selected_ch_auth_ok = sel_creds is not None

            with pl_col:
                if sel_cid:
                    playlists = list_user_youtube_playlists(cfg, db, channel_id=sel_cid)
                    pl_map: Dict[str, str] = {"(No Playlist)": "NONE"}
                    for pl in playlists:
                        pl_map[f"📂 {pl['title']}"] = pl["id"]
                    pl_keys = list(pl_map.keys())
                    cur_pl_id = st.session_state.get("omni_playlist_id", "NONE")
                    pl_idx = 0
                    for pi, pk in enumerate(pl_keys):
                        if pl_map[pk] == cur_pl_id:
                            pl_idx = pi
                            break
                    picked_pl_lbl = st.selectbox(
                        f"📂 Target Playlist ({len(playlists)} found on channel):",
                        options=pl_keys,
                        index=pl_idx,
                        key=f"prestep_pl_sel_{sel_cid}",
                    )
                    st.session_state["omni_playlist_id"] = pl_map[picked_pl_lbl]
                    st.session_state["omni_playlist_title"] = picked_pl_lbl.replace("📂 ", "")
                else:
                    st.selectbox("📂 Target Playlist:", options=["(Connect/Select Channel First)"], disabled=True, key="prestep_pl_disabled")

            if sel_cid:
                if selected_ch_auth_ok:
                    st.success(f"✅ **{st.session_state.get('omni_channel_title')}** is connected and ready for direct publishing.")
                else:
                    st.warning(
                        f"⚠️ **{st.session_state.get('omni_channel_title')} needs quick reconnection** — "
                        f"click below to sign in again so your playlists and uploads stay active."
                    )

            # Inline Create New Playlist widget for the selected channel
            if sel_cid and selected_ch_auth_ok:
                with st.expander(f"➕ Create a New Playlist on {st.session_state.get('omni_channel_title')}", expanded=False):
                    npl_c1, npl_c2, npl_c3 = st.columns([1.8, 0.9, 1.0])
                    with npl_c1:
                        new_pl_title = st.text_input("New Playlist Name:", placeholder="e.g., Khatu Shyam Katha, Class 10 Maths...", key="prestep_new_pl_title")
                    with npl_c2:
                        new_pl_priv = st.selectbox("Privacy:", options=["public", "unlisted", "private"], index=0, key="prestep_new_pl_priv")
                    with npl_c3:
                        st.markdown("<div style='height:26px'></div>", unsafe_allow_html=True)
                        if st.button("➕ Create Playlist", use_container_width=True, key="prestep_create_pl_btn"):
                            created_pl, pl_msg = create_youtube_playlist(
                                new_pl_title,
                                privacy_status=new_pl_priv,
                                channel_id=st.session_state.get("omni_channel_id"),
                                config=cfg,
                                db=db,
                            )
                            if created_pl:
                                st.session_state["omni_playlist_id"] = created_pl["id"]
                                st.session_state["omni_playlist_title"] = created_pl["title"]
                                st.success(pl_msg)
                                st.rerun()
                            else:
                                st.error(pl_msg)
        else:
            st.warning("🔒 **No YouTube Channel Connected Yet** — Connect your first channel below, or proceed to Step 1 in offline mode.")

    with st.expander(
        "➕ Connect or Manage YouTube Channels",
        expanded=(
            not all_connected_channels
            or not selected_ch_auth_ok
            or bool(st.session_state.get("newly_connected_secret_toml"))
        ),
    ):
        _render_connect_channel_drawer("prestep", all_connected_channels)

    st.markdown("")
    if st.button("Continue to Topic & Plan ➡️", type="primary", use_container_width=True):
        st.session_state["omni_step"] = 1
        if st.session_state.get("omni_project_id"):
            db.update_project_stage(
                st.session_state["omni_project_id"],
                current_step=1,
                target_channel_id=st.session_state.get("omni_channel_id", ""),
                target_channel_title=st.session_state.get("omni_channel_title", ""),
                target_playlist_id=st.session_state.get("omni_playlist_id", "NONE"),
                target_playlist_title=st.session_state.get("omni_playlist_title", "(No Playlist)"),
            )
        st.rerun()


# ==============================================================================
# STEP 1 — TOPIC, TITLES & STORYBOARD PLAN
# ==============================================================================
elif step == 1:
    st.subheader("Topic, Titles & Storyboard Plan")

    with st.container(border=True):
        topic_val = st.text_input(
            "🎯 Video Topic:",
            value=st.session_state["omni_topic"],
            placeholder="e.g., Khatu Shyam Baba ka Rahasya, How Electric Cars Work, Top 10 AI Tools...",
            key="input_topic_field",
        )
        c1, c2, c3 = st.columns([1.2, 1.3, 0.9])
        with c1:
            niche_val = st.selectbox(
                "🧭 Category:",
                options=SUPPORTED_NICHES,
                index=SUPPORTED_NICHES.index(st.session_state["omni_niche"])
                if st.session_state["omni_niche"] in SUPPORTED_NICHES
                else 0,
                key="input_niche_field",
            )
        with c2:
            lang_val = st.selectbox(
                "🗣️ Language & Voice Style:",
                options=SUPPORTED_LANGUAGES,
                index=SUPPORTED_LANGUAGES.index(st.session_state["omni_language"])
                if st.session_state["omni_language"] in SUPPORTED_LANGUAGES
                else 0,
                key="input_lang_field",
            )
        with c3:
            dur_val = st.slider(
                "⏱️ Target Length (min):",
                min_value=1.0,
                max_value=8.0,
                value=float(st.session_state["omni_target_minutes"]),
                step=0.5,
                help="Longer videos automatically include more visual scenes for smooth pacing.",
                key="input_dur_field",
            )

        bgm_presets_s1 = list(BGM_SCORE_PRESETS.keys())
        cur_bgm_s1 = st.session_state.get("omni_bgm_preset", DEFAULT_BGM_PRESET)
        bgm_val_s1 = st.selectbox(
            "🎼 Background Music Style:",
            options=bgm_presets_s1,
            index=bgm_presets_s1.index(cur_bgm_s1) if cur_bgm_s1 in bgm_presets_s1 else 0,
            help="Auto-Match picks music tailored to your topic and category, or choose any style (or upload your own track in Video Studio).",
            key="input_bgm_preset_s1",
        )
        st.session_state["omni_bgm_preset"] = bgm_val_s1

        run_a1 = st.button(
            "✨ Create Video Plan, Titles & Storyboard",
            type="primary",
            use_container_width=True,
        )

    if run_a1:
        if not topic_val.strip():
            st.warning("Enter a video topic above to get started.")
        else:
            st.session_state["omni_topic"] = topic_val.strip()
            st.session_state["omni_niche"] = niche_val
            st.session_state["omni_language"] = lang_val
            st.session_state["omni_target_minutes"] = float(dur_val)

            with st.status(f"✨ Creating video plan for '{topic_val.strip()}'...", expanded=True) as plan_status:
                st.write("🔍 Researching trending titles, audience questions & keywords...")
                a1_obj = run_agent1_seo_and_storyboard(
                    topic=topic_val.strip(),
                    niche=niche_val,
                    language_tone=lang_val,
                    target_duration_minutes=float(dur_val),
                    config=cfg,
                )
                st.write("📝 Saving titles, hooks & chapter storyboard to your workspace...")
                pid = st.session_state.get("omni_project_id")
                if not pid:
                    pid = db.create_project(
                        topic_val.strip(),
                        niche_val,
                        lang_val,
                        float(dur_val),
                        target_channel_id=st.session_state.get("omni_channel_id", ""),
                        target_channel_title=st.session_state.get("omni_channel_title", ""),
                        target_playlist_id=st.session_state.get("omni_playlist_id", "NONE"),
                        target_playlist_title=st.session_state.get("omni_playlist_title", "(No Playlist)"),
                    )
                    st.session_state["omni_project_id"] = pid
                db.update_project_stage(
                    pid,
                    current_step=1,
                    status="step1_ready",
                    agent1_data=a1_obj.model_dump(),
                    target_channel_id=st.session_state.get("omni_channel_id", ""),
                    target_channel_title=st.session_state.get("omni_channel_title", ""),
                    target_playlist_id=st.session_state.get("omni_playlist_id", "NONE"),
                    target_playlist_title=st.session_state.get("omni_playlist_title", "(No Playlist)"),
                )
                st.session_state["agent1_output"] = a1_obj.model_dump()
                _clear_step1_widget_keys()
                st.session_state["agent2_output"] = None
                st.session_state["agent3_output"] = None
                st.session_state["agent4_output"] = None
                plan_status.update(label="✅ Video plan & storyboard ready!", state="complete", expanded=False)
            st.success("✅ Your titles, description & storyboard are ready below — customize anything you like.")

    a1_data = st.session_state.get("agent1_output")
    if a1_data:
        a1 = Agent1Output.model_validate(a1_data)

        with st.expander("📊 Audience Insights & Trending Inspiration", expanded=False):
            if a1.competitor_insights:
                st.markdown("**Top Related Videos on YouTube:**")
                for comp in a1.competitor_insights:
                    st.markdown(
                        f"- **{comp.title}** ({comp.channel_title}) — `{comp.view_count:,} views`"
                    )
            st.markdown("**Key Viewer Questions to Answer:**")
            for q in a1.common_audience_questions:
                st.markdown(f"- {q}")

        with st.expander("📝 Video Title, Description & Thumbnail Concept", expanded=True):
            t_options = list(a1.title_options)
            default_idx = t_options.index(a1.selected_title) if a1.selected_title in t_options else 0

            def _sync_selected_title_to_input() -> None:
                st.session_state["a1_title_edit"] = st.session_state.get("a1_title_pick", t_options[default_idx])

            picked_title = st.radio(
                "Pick Your Favorite Title:",
                options=t_options,
                index=default_idx,
                key="a1_title_pick",
                on_change=_sync_selected_title_to_input,
            )
            if "a1_title_edit" not in st.session_state:
                st.session_state["a1_title_edit"] = a1.selected_title or picked_title
            edited_title = st.text_input("Refine Selected Title:", key="a1_title_edit")
            edited_desc = st.text_area("YouTube Description:", value=a1.seo_description, height=160, key="a1_desc_edit")
            edited_tags_str = st.text_area("Search Tags (comma-separated):", value=", ".join(a1.tags), height=82, key="a1_tags_edit")

            th_c1, th_c2 = st.columns(2)
            with th_c1:
                edited_thumb_hl = st.text_input("Thumbnail Headline (2–4 punchy words):", value=a1.thumbnail_hook_headline, key="a1_th_hl")
            with th_c2:
                edited_thumb_badge = st.text_input("Thumbnail Corner Badge:", value=a1.thumbnail_badge_label, key="a1_th_badge")
            edited_thumb_concept = st.text_input(
                "Thumbnail Visual Scene Idea:",
                value=a1.thumbnail_graphic_concept,
                key="a1_th_concept",
            )
            edited_bgm_style = st.text_input(
                "🎼 Background Music Mood:",
                value=a1.bgm_style_reference,
                key="a1_bgm_style",
            )
            edited_char_bible = st.text_area(
                "🎭 Main Character Look Lock (Same Face Across Every Scene):",
                value=a1.character_bible,
                height=82,
                placeholder=(
                    "Leave blank for non-character topics, or describe exact face, age, hair, forehead markings & outfit "
                    "(e.g., Barbarik: young Indian warrior, early 20s, sharp jawline, red-saffron tilak, golden armor, saffron drape, 3 glowing arrows)."
                ),
                help="Locks one consistent face & costume across every AI scene and video clip. Leave empty if your video has no recurring main character.",
                key="a1_char_bible",
            )

        with st.expander("🎬 Storyboard & Key Moments", expanded=True):
            edited_hook = st.text_area("⚡ Opening Hook (First 45 Seconds):", value=a1.hook_script_0_45s, height=90, key="a1_hook_edit")
            edited_climax = st.text_area("💡 Big Reveal / Climax:", value=a1.climax_misconception_aha, height=85, key="a1_climax_edit")
            edited_cta = st.text_area("📣 Closing Call-to-Action:", value=a1.outro_cta_script, height=80, key="a1_cta_edit")
            edited_short_hook = st.text_area(
                "📱 Shorts Cliffhanger Hook (10–20s Teaser to Drive Viewers to Full Video):",
                value=a1.short_hook_script,
                height=78,
                placeholder="Leave blank to auto-generate a punchy 10–20s curiosity/fear hook when building your Short.",
                help="26–38 spoken words (~12–18 seconds) opening with a shocking question/fear and pointing viewers to the full video link in the description.",
                key="a1_short_hook_edit",
            )

            st.markdown("**Chapter Breakdown:**")
            updated_beats = []
            for b in a1.storyboard_beats:
                with st.container(border=True):
                    bc1, bc2 = st.columns([2.2, 1.0])
                    with bc1:
                        bt = st.text_input(
                            f"Chapter {b.beat_id} · {format_timestamp(b.start_sec)}:",
                            value=b.beat_title,
                            key=f"beat_title_{b.beat_id}",
                        )
                    with bc2:
                        bd = st.number_input(
                            "Length (sec):",
                            min_value=10.0,
                            max_value=120.0,
                            value=float(b.duration_sec),
                            step=5.0,
                            key=f"beat_dur_{b.beat_id}",
                        )
                    bs = st.text_area("Story Beat Summary:", value=b.narrative_summary, height=64, key=f"beat_sum_{b.beat_id}")
                    b_dict = b.model_dump()
                    b_dict["beat_title"] = bt
                    b_dict["duration_sec"] = float(bd)
                    b_dict["narrative_summary"] = bs
                    updated_beats.append(b_dict)

        cinema_presets = list(CINEMA_STYLE_PRESETS.keys())
        cur_preset = st.session_state.get("omni_cinema_preset", DEFAULT_CINEMA_PRESET)
        chosen_preset_s1 = st.selectbox(
            "🎥 Visual Style:",
            options=cinema_presets,
            index=cinema_presets.index(cur_preset) if cur_preset in cinema_presets else 0,
            key="input_cinema_preset_s1",
        )
        st.session_state["omni_cinema_preset"] = chosen_preset_s1

        st.markdown("")
        proceed_s2 = st.button("Build Scene-by-Scene Script ➡️", type="primary", use_container_width=True)
        if proceed_s2:
            edited_a1_dict = a1.model_dump()
            edited_a1_dict["selected_title"] = edited_title.strip() or a1.selected_title
            edited_a1_dict["seo_description"] = edited_desc.strip() or a1.seo_description
            edited_a1_dict["tags"] = [t.strip() for t in edited_tags_str.split(",") if t.strip()]
            edited_a1_dict["hook_script_0_45s"] = edited_hook.strip() or a1.hook_script_0_45s
            edited_a1_dict["climax_misconception_aha"] = edited_climax.strip() or a1.climax_misconception_aha
            edited_a1_dict["outro_cta_script"] = edited_cta.strip() or a1.outro_cta_script
            edited_a1_dict["short_hook_script"] = edited_short_hook.strip()
            edited_a1_dict["thumbnail_hook_headline"] = edited_thumb_hl.strip() or a1.thumbnail_hook_headline
            edited_a1_dict["thumbnail_badge_label"] = edited_thumb_badge.strip() or a1.thumbnail_badge_label
            edited_a1_dict["thumbnail_graphic_concept"] = edited_thumb_concept.strip() or a1.thumbnail_graphic_concept
            edited_a1_dict["bgm_style_reference"] = edited_bgm_style.strip() or a1.bgm_style_reference
            new_bible = edited_char_bible.strip()
            edited_a1_dict["character_bible"] = new_bible
            if new_bible != (a1.character_bible or "").strip():
                edited_a1_dict["character_anchor_prompt"] = new_bible
            edited_a1_dict["storyboard_beats"] = updated_beats

            committed_a1 = Agent1Output.model_validate(edited_a1_dict)
            st.session_state["agent1_output"] = committed_a1.model_dump()

            with st.status("🎬 Writing scene-by-scene narration & visual shots...", expanded=True) as sc_status:
                st.write("✍️ Expanding your storyboard into paced cinema scenes...")
                a2_obj = run_agent2_scene_scripting(
                    committed_a1,
                    cinema_preset=st.session_state.get("omni_cinema_preset", DEFAULT_CINEMA_PRESET),
                    config=cfg,
                )
                st.write("☁️ Saving scenes to your Cloud Studio workspace...")
                st.session_state["agent2_output"] = a2_obj.model_dump()
                st.session_state["omni_step"] = 2
                st.session_state["scene_page"] = 1
                pid = st.session_state["omni_project_id"]
                db.update_project_stage(
                    pid,
                    current_step=2,
                    status="step2_ready",
                    agent1_data=committed_a1.model_dump(),
                    agent2_data=a2_obj.model_dump(),
                )
                sc_status.update(label=f"✅ {len(a2_obj.scenes)} scenes scripted!", state="complete", expanded=False)
            st.rerun()


# ==============================================================================
# STEP 2 — SCENE-BY-SCENE SCRIPT & VISUALS
# ==============================================================================
elif step == 2:
    st.subheader("Scene-by-Scene Script")
    a1_data = st.session_state.get("agent1_output")
    a2_data = st.session_state.get("agent2_output")

    if not a1_data or not a2_data:
        st.info("Create your Topic & Plan first to unlock scene scripting.")
        if st.button("⬅️ Go to Topic & Plan", use_container_width=True):
            st.session_state["omni_step"] = 1
            st.rerun()
    else:
        a2 = Agent2Output.model_validate(a2_data)
        pid = st.session_state["omni_project_id"]
        custom_dir = cfg.projects_dir / f"{pid}_{sanitize_slug(a2.topic)}" / "custom_assets"
        custom_dir.mkdir(parents=True, exist_ok=True)

        avg_cut = round(a2.total_estimated_duration_sec / max(1, len(a2.scenes)), 1)
        m1, m2, m3 = st.columns(3)
        m1.metric("Total Scenes", len(a2.scenes))
        m2.metric("Avg Scene Length", f"{avg_cut}s")
        m3.metric("Estimated Runtime", format_timestamp(a2.total_estimated_duration_sec))

        cinema_presets_s2 = list(CINEMA_STYLE_PRESETS.keys())
        cur_p_s2 = st.session_state.get("omni_cinema_preset", DEFAULT_CINEMA_PRESET)
        cp_c1, cp_c2 = st.columns([1.4, 1.0])
        with cp_c1:
            sel_preset_s2 = st.selectbox(
                "🎥 Visual Style:",
                options=cinema_presets_s2,
                index=cinema_presets_s2.index(cur_p_s2) if cur_p_s2 in cinema_presets_s2 else 0,
                key="cinema_preset_s2",
            )
            st.session_state["omni_cinema_preset"] = sel_preset_s2
        with cp_c2:
            st.markdown("<div style='height:26px'></div>", unsafe_allow_html=True)
            if st.button("✨ Enhance All Scene Visuals", use_container_width=True):
                with st.status("✨ Upgrading all scene visuals to cinema grade...", expanded=True) as up_st:
                    st.write("🎥 Polishing camera framing, character lock, lighting & sound cues across all scenes...")
                    cur_char_bible = Agent1Output.model_validate(a1_data).character_bible
                    boosted_a2 = enhance_all_scenes_to_cinema(
                        a2,
                        cinema_preset=sel_preset_s2,
                        character_bible=cur_char_bible,
                        config=cfg,
                    )
                    st.session_state["agent2_output"] = boosted_a2.model_dump()
                    db.update_project_stage(pid, agent2_data=boosted_a2.model_dump())
                    for s_i in range(1, len(boosted_a2.scenes) + 1):
                        st.session_state.pop(f"sc_vprompt_{s_i}", None)
                        st.session_state.pop(f"sc_sfx_{s_i}", None)
                        st.session_state.pop(f"sc_mode_{s_i}", None)
                        st.session_state.pop(f"sc_mg_{s_i}", None)
                        st.session_state.pop(f"sc_char_{s_i}", None)
                    up_st.update(label="✅ All scene visuals enhanced!", state="complete", expanded=False)
                st.rerun()

        per_page = 8
        total_pages = max(1, (len(a2.scenes) + per_page - 1) // per_page)
        pg_c1, pg_c2 = st.columns([1.4, 1.0])
        with pg_c1:
            current_page = st.number_input(
                f"Page (showing {per_page} of {len(a2.scenes)} scenes):",
                min_value=1,
                max_value=total_pages,
                value=min(int(st.session_state.get("scene_page", 1)), total_pages),
                step=1,
                key="scene_page_selector",
            )
            st.session_state["scene_page"] = int(current_page)
        with pg_c2:
            st.markdown("<div style='height:26px'></div>", unsafe_allow_html=True)
            if st.button("🔄 Regenerate Scenes", use_container_width=True):
                with st.status("🔄 Rebuilding scenes from your storyboard...", expanded=True) as rg_st:
                    st.write("✍️ Drafting fresh narration and camera direction...")
                    fresh_a2 = run_agent2_scene_scripting(
                        Agent1Output.model_validate(a1_data),
                        cinema_preset=sel_preset_s2,
                        config=cfg,
                    )
                    st.session_state["agent2_output"] = fresh_a2.model_dump()
                    db.update_project_stage(pid, agent2_data=fresh_a2.model_dump())
                    for s_i in range(1, len(fresh_a2.scenes) + 1):
                        st.session_state.pop(f"sc_vprompt_{s_i}", None)
                        st.session_state.pop(f"sc_mode_{s_i}", None)
                        st.session_state.pop(f"sc_mg_{s_i}", None)
                    rg_st.update(label="✅ Scenes regenerated!", state="complete", expanded=False)
                st.rerun()

        # Google AI Ultra / Google Flow Zero-Cloud-Video-Cost Bridge (Export clean prompts + Bulk upload clips!)
        attached_flow_cnt = sum(
            1 for s in a2.scenes if s.asset_mode == "custom_upload" and bool((s.custom_asset_path or "").strip())
        )
        flow_exp_lbl = (
            f"🎬 Use Google AI Ultra / Flow Credits (₹0 Cloud Video Cost — {attached_flow_cnt}/{len(a2.scenes)} Clips Attached)"
            if attached_flow_cnt > 0
            else "🎬 Use Google AI Ultra / Flow Credits (₹0 Cloud Video Cost)"
        )
        with st.expander(flow_exp_lbl, expanded=False):
            st.markdown(
                "Have a **Google AI Ultra** subscription? Generate your full-motion clips inside "
                "[Google Flow](https://labs.google/fx/tools/flow) using your included Ultra credits (**₹0 extra Google Cloud cost**), "
                "then drop all clips here in one batch — OMNI STUDIO will automatically add Indian voiceover, music, active subtitles, "
                "thumbnail, 16:9 HD + 9:16 Short & publish to YouTube (for only ~₹20 total)!"
            )
            fl_c1, fl_c2 = st.columns([1.0, 1.35])
            with fl_c1:
                cur_a1_for_flow = Agent1Output.model_validate(a1_data)
                flow_txt = format_flow_prompts_export_txt(
                    topic=a2.topic,
                    niche=a2.niche,
                    character_bible=cur_a1_for_flow.character_bible,
                    scenes=a2.scenes,
                    cinema_preset=sel_preset_s2,
                    character_anchor_prompt=cur_a1_for_flow.character_anchor_prompt,
                )
                st.download_button(
                    "📥 Download Clean Flow Prompts (.txt)",
                    data=flow_txt.encode("utf-8"),
                    file_name=f"{sanitize_slug(a2.topic)}_google_flow_prompts.txt",
                    mime="text/plain",
                    use_container_width=True,
                    key=f"dl_flow_prompts_{pid}",
                )
                flow_start_scene = st.number_input(
                    "Assign sequential uploads starting at Scene #:",
                    min_value=1,
                    max_value=len(a2.scenes),
                    value=1,
                    step=1,
                    help="Files named like scene_05.mp4 or 05.mp4 automatically match Scene 5; unnumbered clips fill sequentially from this scene.",
                    key=f"flow_start_sc_{pid}",
                )
            with fl_c2:
                bulk_flow_files = st.file_uploader(
                    "📁 Bulk Drop Google Flow Clips (.mp4, .mov, .png, .jpg):",
                    type=["mp4", "mov", "png", "jpg", "jpeg"],
                    accept_multiple_files=True,
                    key=f"bulk_flow_upload_{pid}",
                )
                if bulk_flow_files and st.button(
                    f"✅ Attach {len(bulk_flow_files)} Clip(s) to Scenes",
                    type="primary",
                    use_container_width=True,
                    key=f"apply_bulk_flow_{pid}",
                ):
                    import re as _re_flow

                    upd_scenes_bulk = [s.model_dump() for s in a2.scenes]
                    seq_cursor = int(flow_start_scene)
                    mapped_msgs: List[str] = []
                    for uf in sorted(bulk_flow_files, key=lambda f: f.name.lower()):
                        m_num = _re_flow.search(r"(?:scene[_\-\s]*|^s?)(\d{1,2})\b", Path(uf.name).stem, flags=_re_flow.IGNORECASE)
                        target_idx = int(m_num.group(1)) if (m_num and 1 <= int(m_num.group(1)) <= len(upd_scenes_bulk)) else seq_cursor
                        if target_idx > len(upd_scenes_bulk):
                            break
                        dest_p = custom_dir / f"scene_{target_idx:03d}_{uf.name}"
                        dest_p.write_bytes(uf.getvalue())
                        upd_scenes_bulk[target_idx - 1]["custom_asset_path"] = str(dest_p)
                        upd_scenes_bulk[target_idx - 1]["asset_mode"] = "custom_upload"
                        st.session_state.pop(f"sc_mode_{target_idx}", None)
                        mapped_msgs.append(f"Scene {target_idx:02d} ← `{uf.name}`")
                        seq_cursor = max(seq_cursor + 1, target_idx + 1)
                    if mapped_msgs:
                        new_a2_dict = a2.model_dump()
                        new_a2_dict["scenes"] = upd_scenes_bulk
                        st.session_state["agent2_output"] = new_a2_dict
                        db.update_project_stage(pid, agent2_data=new_a2_dict)
                        st.success(f"✅ Attached {len(mapped_msgs)} clip(s): " + ", ".join(mapped_msgs[:6]) + ("..." if len(mapped_msgs) > 6 else ""))
                        st.rerun()

        start_idx = (int(current_page) - 1) * per_page
        end_idx = min(len(a2.scenes), start_idx + per_page)
        scenes_dicts = [s.model_dump() for s in a2.scenes]

        for idx in range(start_idx, end_idx):
            sc = scenes_dicts[idx]
            s_num = sc["scene_index"]
            mode_icon = "🎞️" if sc["asset_mode"] == "custom_upload" else "🎥"
            exp_title = (
                f"{mode_icon} Scene {s_num:02d} ({format_timestamp(sc['start_sec'])} · {sc['duration_sec']}s) "
                f"— {sc['chapter_label'][:42]}"
            )
            with st.expander(exp_title, expanded=(idx == start_idx)):
                new_vo = st.text_area(
                    "🎙️ Voiceover Script:",
                    value=sc["voiceover_text"],
                    height=74,
                    key=f"sc_vo_{s_num}",
                )
                new_vis_prompt = st.text_area(
                    "🎥 Visual Scene Description:",
                    value=sc["visual_prompt_veo_omni"],
                    height=82,
                    key=f"sc_vprompt_{s_num}",
                )
                s_col1, s_col2 = st.columns([2.2, 0.8])
                with s_col1:
                    new_sfx = st.text_input(
                        "🔊 Sound Effects:",
                        value=sc.get("sfx_cue", ""),
                        key=f"sc_sfx_{s_num}",
                    )
                with s_col2:
                    new_dur = st.number_input(
                        "Length (sec):",
                        min_value=6.0,
                        max_value=14.0,
                        value=float(sc["duration_sec"]),
                        step=0.5,
                        key=f"sc_dur_{s_num}",
                    )

                uploaded_asset = st.file_uploader(
                    "📁 Optional: Upload Your Own Clip or Image (supports Google Flow exports)",
                    type=["mp4", "mov", "png", "jpg", "jpeg"],
                    key=f"sc_upload_{s_num}",
                )
                new_mode = sc["asset_mode"]
                new_mg = sc.get("motion_graphic_type") or "none"
                new_ssml = sc.get("ssml_voice_cues", "")
                new_callout = sc.get("on_screen_callout", "")
                new_feat_char = bool(sc.get("features_main_character", False))

                with st.expander("⚙️ Advanced Scene Options", expanded=False):
                    new_feat_char = st.checkbox(
                        "🎭 Lock Main Character Face in This Scene",
                        value=new_feat_char,
                        key=f"sc_char_{s_num}",
                    )
                    ac1, ac2 = st.columns(2)
                    with ac1:
                        modes = ["ai_video", "motion_graphics", "custom_upload"]
                        new_mode = st.selectbox(
                            "Visual Source:",
                            options=modes,
                            index=modes.index(sc["asset_mode"]) if sc["asset_mode"] in modes else 0,
                            key=f"sc_mode_{s_num}",
                        )
                    with ac2:
                        mg_opts = ["none", "manim_formula", "data_chart", "comparison_chart", "timeline_chart"]
                        new_mg = st.selectbox(
                            "Graphic Overlay:",
                            options=mg_opts,
                            index=mg_opts.index(new_mg) if new_mg in mg_opts else 0,
                            key=f"sc_mg_{s_num}",
                        )
                    new_ssml = st.text_input(
                        "Vocal Pacing Notes:",
                        value=sc.get("ssml_voice_cues", ""),
                        key=f"sc_ssml_{s_num}",
                    )
                    new_callout = st.text_input(
                        "Scene Title Tag:",
                        value=sc.get("on_screen_callout", ""),
                        key=f"sc_callout_{s_num}",
                    )

                if uploaded_asset is not None:
                    dest = custom_dir / f"scene_{s_num:03d}_{uploaded_asset.name}"
                    dest.write_bytes(uploaded_asset.getvalue())
                    sc["custom_asset_path"] = str(dest)
                    new_mode = "custom_upload"
                    st.caption(f"✅ Attached clip: `{dest.name}`")
                elif sc.get("custom_asset_path"):
                    st.caption(f"📎 Attached clip: `{Path(sc['custom_asset_path']).name}`")

                sc["asset_mode"] = new_mode
                sc["motion_graphic_type"] = new_mg
                sc["duration_sec"] = float(new_dur)
                sc["visual_prompt_veo_omni"] = new_vis_prompt
                sc["voiceover_text"] = new_vo
                sc["ssml_voice_cues"] = new_ssml
                sc["sfx_cue"] = new_sfx
                sc["on_screen_callout"] = new_callout
                sc["features_main_character"] = bool(new_feat_char)

        a2_updated_dict = a2.model_dump()
        a2_updated_dict["scenes"] = scenes_dicts
        a2_updated_dict["total_estimated_duration_sec"] = round(sum(s["duration_sec"] for s in scenes_dicts), 1)
        st.session_state["agent2_output"] = a2_updated_dict

        st.markdown("")
        act_c1, act_c2 = st.columns([1, 2])
        with act_c1:
            if st.button("⬅️ Back to Topic & Plan", use_container_width=True):
                db.update_project_stage(pid, current_step=1, agent2_data=a2_updated_dict)
                st.session_state["omni_step"] = 1
                st.rerun()
        with act_c2:
            if st.button("Continue to Video Studio ➡️", type="primary", use_container_width=True):
                validated_a2 = Agent2Output.model_validate(a2_updated_dict)
                st.session_state["agent2_output"] = validated_a2.model_dump()
                st.session_state["omni_step"] = 3
                db.update_project_stage(
                    pid,
                    current_step=3,
                    status="step3_pending_render",
                    agent2_data=validated_a2.model_dump(),
                )
                st.rerun()


# ==============================================================================
# STEP 3 — VIDEO PRODUCTION STUDIO
# ==============================================================================
elif step == 3:
    st.subheader("Video Production Studio")
    a1_data = st.session_state.get("agent1_output")
    a2_data = st.session_state.get("agent2_output")
    pid = st.session_state.get("omni_project_id")

    if not a1_data or not a2_data or not pid:
        st.info("Complete your Topic & Scenes first to open the Video Production Studio.")
    else:
        a1 = Agent1Output.model_validate(a1_data)
        a2 = Agent2Output.model_validate(a2_data)
        render_task_key = f"render_{pid}"

        fresh_proj = db.get_project(pid)
        if fresh_proj and fresh_proj.get("agent3_data"):
            st.session_state["agent3_output"] = fresh_proj["agent3_data"]

        with st.expander("⚙️ Video Quality, Music & Presenter Settings", expanded=True):
            rc1, rc2 = st.columns([1.35, 1.0])
            with rc1:
                quality_label = st.selectbox(
                    "🎞️ Video Quality:",
                    options=[
                        "⚡ Hybrid Cinema (Recommended — ~70% Lower Cost)",
                        "🖼️ Fast AI Visuals (Ultra Budget — ~90% Lower Cost)",
                        "🎬 Full Motion Cinema (All AI Video — Premium)",
                        "📝 Quick Draft Preview (Free Offline Test)",
                    ],
                    index=0,
                    key="render_quality_sel",
                )
                quality_map = {
                    "⚡ Hybrid Cinema (Recommended — ~70% Lower Cost)": "hybrid_cinema",
                    "🖼️ Fast AI Visuals (Ultra Budget — ~90% Lower Cost)": "ai_keyframes_kenburns",
                    "🎬 Full Motion Cinema (All AI Video — Premium)": "full_omni_video",
                    "📝 Quick Draft Preview (Free Offline Test)": "fast_studio_preview",
                }
                render_quality = quality_map[quality_label]
                cinema_presets_s3 = list(CINEMA_STYLE_PRESETS.keys())
                cur_p_s3 = st.session_state.get("omni_cinema_preset", DEFAULT_CINEMA_PRESET)
                cinema_preset_s3 = st.selectbox(
                    "🎥 Visual Style:",
                    options=cinema_presets_s3,
                    index=cinema_presets_s3.index(cur_p_s3) if cur_p_s3 in cinema_presets_s3 else 0,
                    key="render_cinema_preset_sel",
                )
                st.session_state["omni_cinema_preset"] = cinema_preset_s3
                bgm_presets_s3 = list(BGM_SCORE_PRESETS.keys())
                cur_bgm_s3 = st.session_state.get("omni_bgm_preset", DEFAULT_BGM_PRESET)
                selected_bgm_preset_s3 = st.selectbox(
                    "🎼 Background Music Style:",
                    options=bgm_presets_s3,
                    index=bgm_presets_s3.index(cur_bgm_s3) if cur_bgm_s3 in bgm_presets_s3 else 0,
                    key="render_bgm_preset_sel",
                )
                st.session_state["omni_bgm_preset"] = selected_bgm_preset_s3
            with rc2:
                bgm_level_label = st.selectbox(
                    "🎵 Background Music Volume:",
                    options=[
                        "Balanced (Recommended)",
                        "Bold & Dramatic",
                        "Soft & Subtle",
                    ],
                    index=0,
                    key="opt_bgm_level",
                )
                bgm_level_map = {
                    "Balanced (Recommended)": -13.5,
                    "Bold & Dramatic": -10.5,
                    "Soft & Subtle": -17.5,
                }
                selected_bgm_duck_db = bgm_level_map[bgm_level_label]
                enable_foley_sfx = st.checkbox(
                    "🔊 Realistic Scene Sound Effects",
                    value=True,
                    key="opt_enable_foley_sfx",
                )
                force_ai_cinema = st.checkbox(
                    "🎬 Full Cinema Visuals on All Scenes",
                    value=True,
                    key="opt_force_ai_cinema",
                )
                fast_tts = st.checkbox(
                    "⚡ Quick Voice Mode (Faster Draft)",
                    value=False,
                    key="render_fast_tts",
                )

            custom_bgm_file_path: Optional[str] = None
            if BGM_SCORE_PRESETS.get(selected_bgm_preset_s3) == "__CUSTOM_UPLOAD__":
                bgm_dir = cfg.projects_dir / f"{pid}_{sanitize_slug(a1.topic)}" / "audio"
                bgm_dir.mkdir(parents=True, exist_ok=True)
                up_bgm = st.file_uploader(
                    "🎵 Upload Custom Music Track (.mp3, .wav, .m4a):",
                    type=["mp3", "wav", "m4a"],
                    key="upload_custom_bgm_s3",
                )
                if up_bgm is not None:
                    dst_bgm = bgm_dir / f"user_custom_bgm{Path(up_bgm.name).suffix.lower()}"
                    dst_bgm.write_bytes(up_bgm.getvalue())
                    st.session_state["omni_custom_bgm_path"] = str(dst_bgm)
                    st.success(f"✅ Music attached: `{up_bgm.name}`")
                if st.session_state.get("omni_custom_bgm_path") and Path(st.session_state["omni_custom_bgm_path"]).exists():
                    custom_bgm_file_path = st.session_state["omni_custom_bgm_path"]
                    st.audio(Path(custom_bgm_file_path).read_bytes())

            st.markdown("**🧍 Optional Presenter Photo:**")
            av_c1, av_c2 = st.columns(2)
            with av_c1:
                include_avatar_thumb = st.checkbox(
                    "Show my photo on Thumbnail",
                    value=False,
                    key="opt_include_avatar_thumb",
                )
            with av_c2:
                include_avatar_video = st.checkbox(
                    "Show presenter badge on Intro & Outro",
                    value=False,
                    key="opt_include_avatar_video",
                )

            creator_side = "left"
            avatar_thumb_mode = "real_photo"
            if include_avatar_thumb:
                opt_c1, opt_c2 = st.columns(2)
                with opt_c1:
                    av_style_lbl = st.selectbox(
                        "Photo Style:",
                        options=[
                            "Real Studio Photo Cutout (Recommended)",
                            "Stylized AI Portrait",
                        ],
                        index=0,
                        key="opt_avatar_thumb_style",
                    )
                    avatar_thumb_mode = "real_photo" if av_style_lbl.startswith("Real") else "ai_pro"
                with opt_c2:
                    creator_side = st.selectbox(
                        "Photo Position:",
                        options=["left", "right"],
                        index=0,
                        key="thumb_creator_side",
                    )

            if include_avatar_thumb or include_avatar_video:
                with st.expander("🪪 Update Your Studio Photo", expanded=False):
                    studio_refs = [p for p in (cfg.likeness_dir / "image_13.png", cfg.likeness_dir / "image_14.png") if p.exists()]
                    if studio_refs:
                        lcols = st.columns(len(studio_refs))
                        for lcol, lp in zip(lcols, studio_refs):
                            with lcol:
                                st.image(str(lp), use_container_width=True)
                    up_ref = st.file_uploader(
                        "Upload New Studio Photo:",
                        type=["png", "jpg", "jpeg"],
                        key="replace_likeness_img",
                    )
                    if up_ref is not None:
                        (cfg.likeness_dir / "image_13.png").write_bytes(up_ref.getvalue())
                        st.success("✅ Studio photo updated!")

        is_rendering = worker.is_running(render_task_key)
        frames_task_key = f"frames_{pid}"
        is_previewing_frames = worker.is_running(frames_task_key)
        any_busy = is_rendering or is_previewing_frames

        proj_dir_s3 = cfg.projects_dir / f"{pid}_{sanitize_slug(a1.topic)}"
        proj_clips_dir = proj_dir_s3 / "clips_16x9"
        cached_vis_count = (
            len([fp for fp in proj_clips_dir.glob("scene_*_vis.mp4") if fp.stat().st_size > 16384])
            if proj_clips_dir.exists()
            else 0
        )
        approved_kf_indices: set = set()
        if proj_clips_dir.exists():
            for sc_chk in a2.scenes:
                kfp = proj_clips_dir / f"scene_{sc_chk.scene_index:03d}_keyframe.png"
                if kfp.exists() and kfp.stat().st_size > 16384:
                    approved_kf_indices.add(sc_chk.scene_index)

        # ------------------------------------------------------------------
        # 🛡️ HARD DAILY BUDGET THROTTLE BAR (Prevents Surprise Cloud Bills!)
        # ------------------------------------------------------------------
        cur_limit_usd = worker.get_daily_cost_limit_usd()
        budget_stat = worker.get_daily_budget_status()
        with st.container(border=True):
            bg_c1, bg_c2 = st.columns([2.1, 0.9])
            with bg_c1:
                spent_inr = int(round(budget_stat["spent_usd"] * 85.5))
                limit_inr = int(round(budget_stat["limit_usd"] * 85.5))
                if budget_stat["is_exceeded"]:
                    st.error(
                        f"🛑 **Daily Budget Limit Reached:** `${budget_stat['spent_usd']:.2f}` / `${budget_stat['limit_usd']:.2f}` "
                        f"(≈ ₹{spent_inr:,} / ₹{limit_inr:,}) — paid generation is paused automatically."
                    )
                else:
                    st.markdown(
                        f"🛡️ **Daily Budget Guard:** `${budget_stat['spent_usd']:.2f}` / `${budget_stat['limit_usd']:.2f}` used today "
                        f"(≈ ₹{spent_inr:,} / ₹{limit_inr:,}) · Auto-pauses if daily cap is crossed"
                    )
                st.progress(min(1.0, budget_stat["pct_used"] / 100.0))
            with bg_c2:
                new_daily_limit = st.number_input(
                    "Daily Cap ($ USD):",
                    min_value=1.0,
                    max_value=200.0,
                    value=float(cur_limit_usd),
                    step=1.0,
                    help="Hard daily spend cap enforced before every paid AI image or video API call.",
                    key="daily_budget_limit_in",
                )
                if abs(float(new_daily_limit) - float(cur_limit_usd)) > 0.01:
                    worker.set_daily_cost_limit_usd(float(new_daily_limit))
                    st.rerun()

        active_daily_limit = float(new_daily_limit)

        # Resolve per-scene I2V animation selection (defaults cleanly to Hybrid Hero / All / None)
        ai_scenes_s3 = [
            s for s in a2.scenes
            if not (s.asset_mode == "custom_upload" and bool((s.custom_asset_path or "").strip()))
        ]
        default_hero_ids = select_hybrid_hero_scene_indices(a2.scenes)
        anim_state_key = f"i2v_anim_mode_{pid}"
        if st.session_state.get(anim_state_key) != render_quality:
            st.session_state[anim_state_key] = render_quality
            for sc_i in a2.scenes:
                if render_quality == "hybrid_cinema":
                    st.session_state[f"i2v_chk_{pid}_{sc_i.scene_index}"] = (sc_i.scene_index in default_hero_ids)
                elif render_quality == "full_omni_video":
                    st.session_state[f"i2v_chk_{pid}_{sc_i.scene_index}"] = True
                else:
                    st.session_state[f"i2v_chk_{pid}_{sc_i.scene_index}"] = False

        selected_i2v_ids: set = {
            s.scene_index
            for s in ai_scenes_s3
            if st.session_state.get(f"i2v_chk_{pid}_{s.scene_index}", s.scene_index in default_hero_ids)
        }

        # ------------------------------------------------------------------
        # STAGE A: 🖼️ HUMAN-IN-THE-LOOP 2D FRAME PREVIEW & APPROVAL GATE (I2V)
        # ------------------------------------------------------------------
        needs_ai_gate = (len(ai_scenes_s3) > 0 and render_quality != "fast_studio_preview")
        frames_approved = not needs_ai_gate
        if needs_ai_gate:
            preview_est = estimate_render_cost_usd(
                a2.scenes,
                render_quality,
                cached_scene_count=0,
                use_fast_tts=fast_tts,
                approved_keyframe_indices=approved_kf_indices,
                animate_scene_indices=selected_i2v_ids,
            )
            prev_usd = preview_est["preview_frames_usd"]
            prev_inr = int(round(prev_usd * 85.5))
            missing_preview_cnt = sum(1 for s in ai_scenes_s3 if s.scene_index not in approved_kf_indices)
            with st.container(border=True):
                st.markdown("#### 🖼️ Step 1: Preview & Approve 2D Scene Frames First (Image-to-Video Gate)")
                st.caption(
                    "Verify every scene's face, anatomy, and zero-camera accuracy as cheap 2D frames (~₹4/frame) "
                    "BEFORE animating video clips — fix any single scene for ₹4 instead of wasting ₹560 on retries!"
                )
                fp_c1, fp_c2 = st.columns([1.8, 1.0])
                with fp_c1:
                    gen_frames_lbl = (
                        f"🖼️ Generate {missing_preview_cnt} Missing Preview Frames (~${prev_usd:.2f} / ≈ ₹{prev_inr:,})"
                        if missing_preview_cnt > 0
                        else f"✅ All {len(approved_kf_indices)}/{len(ai_scenes_s3)} Scene Frames Ready for Review"
                    )
                    run_frame_preview = st.button(
                        gen_frames_lbl,
                        type="primary" if missing_preview_cnt > 0 else "secondary",
                        use_container_width=True,
                        disabled=any_busy or (missing_preview_cnt == 0),
                        key=f"btn_gen_preview_frames_{pid}",
                    )
                with fp_c2:
                    regen_all_frames = st.button(
                        "🔄 Regenerate All Frames",
                        use_container_width=True,
                        disabled=any_busy or (len(approved_kf_indices) == 0),
                        key=f"btn_regen_all_frames_{pid}",
                    )

                if run_frame_preview or regen_all_frames:
                    try:
                        launched_fp = worker.submit_task(
                            task_key=frames_task_key,
                            project_id=pid,
                            job_type="frame_preview",
                            label=f"Preview Frames: {a1.topic[:28]}",
                            fn=run_agent3_keyframe_preview_batch,
                            kwargs={
                                "project_id": pid,
                                "agent1": a1,
                                "agent2": a2,
                                "cinema_preset": cinema_preset_s3,
                                "regenerate_existing": bool(regen_all_frames),
                                "cost_limit_usd": active_daily_limit,
                                "config": cfg,
                                "db": db,
                            },
                            estimated_cost_usd=max(0.05, prev_usd),
                            cost_limit_usd=active_daily_limit,
                        )
                        if launched_fp:
                            st.toast("Generating 2D preview frames...", icon="🖼️")
                            st.rerun()
                    except BudgetLimitExceededError as b_err:
                        st.error(f"🛑 {b_err}")

                fp_jobs = db.get_project_jobs(pid, job_type="frame_preview")
                if is_previewing_frames or (fp_jobs and fp_jobs[-1].get("status") == "failed"):
                    latest_fp = fp_jobs[-1] if fp_jobs else {"progress_pct": 5, "message": "Preparing preview frames..."}
                    st.progress(latest_fp["progress_pct"] / 100.0)
                    st.caption(f"🖼️ {latest_fp.get('message', '')}")
                    fp_err = worker.get_task_error(frames_task_key)
                    if fp_err:
                        st.error(f"Frame preview paused: {fp_err}")
                    if is_previewing_frames:
                        time.sleep(2.0)
                        st.rerun()

                # Visual 3-Column Frame Review Gallery (with per-frame Edit Prompt + Regenerate ~₹4 + I2V toggle!)
                if approved_kf_indices:
                    st.markdown(f"**🔍 Visual Inspection Gallery ({len(approved_kf_indices)}/{len(ai_scenes_s3)} frames ready):**")
                    per_gallery_page = 9
                    g_pages = max(1, (len(ai_scenes_s3) + per_gallery_page - 1) // per_gallery_page)
                    gal_page = (
                        st.number_input(
                            f"Gallery Page (9 frames/page, {g_pages} pages):",
                            min_value=1,
                            max_value=g_pages,
                            value=1,
                            step=1,
                            key=f"gal_page_{pid}",
                        )
                        if g_pages > 1
                        else 1
                    )
                    g_start = (int(gal_page) - 1) * per_gallery_page
                    g_slice = ai_scenes_s3[g_start : g_start + per_gallery_page]
                    for row_i in range(0, len(g_slice), 3):
                        cols_g = st.columns(3)
                        for col_j, sc_g in enumerate(g_slice[row_i : row_i + 3]):
                            with cols_g[col_j]:
                                kfp_g = proj_clips_dir / f"scene_{sc_g.scene_index:03d}_keyframe.png"
                                with st.container(border=True):
                                    st.markdown(f"**Scene {sc_g.scene_index:02d}** · {sc_g.chapter_label[:26]}")
                                    if kfp_g.exists() and kfp_g.stat().st_size > 16384:
                                        st.image(str(kfp_g), use_container_width=True)
                                    else:
                                        st.info("Not generated yet")
                                    st.checkbox(
                                        "🎬 Animate with I2V (~₹39)",
                                        key=f"i2v_chk_{pid}_{sc_g.scene_index}",
                                        disabled=any_busy,
                                    )
                                    with st.expander("✏️ Edit / Regenerate (~₹4)", expanded=False):
                                        ed_p = st.text_area(
                                            "Scene Prompt:",
                                            value=sc_g.visual_prompt_veo_omni,
                                            height=76,
                                            key=f"i2v_edit_p_{pid}_{sc_g.scene_index}",
                                        )
                                        if st.button(
                                            "🔄 Regenerate This Frame (~₹4)",
                                            use_container_width=True,
                                            disabled=any_busy,
                                            key=f"btn_regen_one_{pid}_{sc_g.scene_index}",
                                        ):
                                            try:
                                                # Save any prompt edit first before regenerating
                                                if ed_p.strip() and ed_p.strip() != sc_g.visual_prompt_veo_omni:
                                                    a2_mod = a2.model_dump()
                                                    for sd in a2_mod["scenes"]:
                                                        if sd["scene_index"] == sc_g.scene_index:
                                                            sd["visual_prompt_veo_omni"] = ed_p.strip()
                                                    st.session_state["agent2_output"] = a2_mod
                                                    db.update_project_stage(pid, agent2_data=a2_mod)
                                                    a2 = Agent2Output.model_validate(a2_mod)
                                                with st.spinner(f"Regenerating Scene {sc_g.scene_index:02d} frame..."):
                                                    regenerate_single_scene_frame(
                                                        pid,
                                                        a1,
                                                        a2,
                                                        sc_g.scene_index,
                                                        cinema_preset=cinema_preset_s3,
                                                        cost_limit_usd=active_daily_limit,
                                                        config=cfg,
                                                        db=db,
                                                    )
                                                st.toast(f"Scene {sc_g.scene_index:02d} frame updated!", icon="✅")
                                                st.rerun()
                                            except BudgetLimitExceededError as b_err:
                                                st.error(f"🛑 {b_err}")

                    # Refresh selected I2V indices from checkboxes rendered above
                    selected_i2v_ids = {
                        s.scene_index
                        for s in ai_scenes_s3
                        if st.session_state.get(f"i2v_chk_{pid}_{s.scene_index}", False)
                    }
                    frames_approved = st.checkbox(
                        f"✅ I visually inspected the frames above (zero cameras, consistent face & natural anatomy) — approve & unlock Step 2 ({len(selected_i2v_ids)} I2V animated + {max(0, len(ai_scenes_s3) - len(selected_i2v_ids))} verified motion visuals)",
                        value=st.session_state.get(f"i2v_approved_{pid}", False),
                        key=f"i2v_approved_{pid}",
                    )
                else:
                    frames_approved = False

        # Transparent Live Credit Cost Estimator Card for Step 2 (reflects reused verified frames = $0 extra!)
        fresh_est = estimate_render_cost_usd(
            a2.scenes,
            render_quality,
            cached_scene_count=0,
            use_fast_tts=fast_tts,
            approved_keyframe_indices=approved_kf_indices,
            animate_scene_indices=selected_i2v_ids if (needs_ai_gate and approved_kf_indices) else None,
        )
        est_usd = fresh_est["total_usd"]
        est_inr = int(round(est_usd * 85.5))
        full_usd = fresh_est["full_motion_usd"]
        savings_usd = max(0.0, round(full_usd - est_usd, 2))
        custom_cnt = int(fresh_est.get("custom_scenes", 0))
        reused_kf_cnt = int(fresh_est.get("reused_keyframes", 0))
        custom_prefix = f"{custom_cnt} Flow/uploaded clips (₹0 AI video cost) + " if custom_cnt > 0 else ""
        reused_kf_note = f"{reused_kf_cnt} verified frames reused (₹0 extra) + " if reused_kf_cnt > 0 else ""
        char_lock_note = (
            " · 🎭 Same-Face Lock Active"
            if (a1.character_bible or "").strip() and (fresh_est["video_scenes"] + fresh_est["keyframe_scenes"] > 0)
            else (
                " · 🎭 Auto Same-Face Lock Ready"
                if render_quality != "fast_studio_preview" and (fresh_est["video_scenes"] + fresh_est["keyframe_scenes"] > 0)
                else ""
            )
        )
        if custom_cnt >= len(a2.scenes):
            est_detail = f"All {custom_cnt} scenes use your Flow/uploaded clips (₹0 AI video cost) — only voiceover, music, thumbnail & Long+Short assembly"
        elif render_quality == "fast_studio_preview":
            est_detail = "Free offline draft preview (no AI video or image credits used)"
        else:
            est_detail = (
                f"{custom_prefix}{fresh_est['video_scenes']} I2V animated hero clips + "
                f"{reused_kf_note}{fresh_est['keyframe_scenes']} new AI visuals + voice, thumbnail & Shorts{char_lock_note}"
            )
        cost_headline = (
            "💰 Step 2 Estimated Credit Cost: Free (₹0)"
            if est_usd <= 0.0
            else f"💰 Step 2 Estimated Credit Cost: ~${est_usd:.2f} (≈ ₹{est_inr:,}) — includes Long + Short"
        )
        save_badge = f'<span class="omni-cost-save">Saves ~${savings_usd:.2f} vs Full Motion</span>' if savings_usd >= 0.50 else ""
        st.markdown(
            f"""
            <div class="omni-cost-card">
                <div>
                    <div class="omni-cost-main">{cost_headline}</div>
                    <div class="omni-cost-sub">{est_detail}</div>
                </div>
                {save_badge}
            </div>
            """,
            unsafe_allow_html=True,
        )

        resume_stitch = False
        if cached_vis_count > 0:
            res_est = estimate_render_cost_usd(a2.scenes, render_quality, cached_scene_count=cached_vis_count, use_fast_tts=fast_tts)
            st.info(
                f"🎞️ **{cached_vis_count}/{len(a2.scenes)} scene clips are already saved!** "
                f"Fast Resume reuses them (~${res_est['total_usd']:.2f} estimated cost — no AI video re-render)."
            )
            resume_stitch = st.button(
                f"⚡ Finish Video from Saved Clips ({cached_vis_count}/{len(a2.scenes)} Ready)",
                type="primary",
                use_container_width=True,
                disabled=any_busy,
                key="btn_resume_stitch_only",
            )

        btn_r1, btn_r2 = st.columns([2.0, 1.0])
        with btn_r1:
            step2_lbl = (
                "🎬 Step 2: Animate Approved Frames & Build Video + Shorts"
                if (needs_ai_gate and approved_kf_indices)
                else ("🎬 Generate Fresh Video & Shorts" if cached_vis_count > 0 else "🎬 Generate Full HD Video & Shorts")
            )
            start_render = st.button(
                step2_lbl,
                type="secondary" if cached_vis_count > 0 else "primary",
                use_container_width=True,
                disabled=any_busy or (needs_ai_gate and not frames_approved),
                help="Preview and approve your 2D frames in Step 1 above first to guarantee zero wasted video credits!" if (needs_ai_gate and not frames_approved) else None,
            )
        with btn_r2:
            regen_thumb = st.button(
                "🖼️ Regenerate Thumbnail",
                use_container_width=True,
                disabled=any_busy,
            )

        direct_skip_render = False
        if needs_ai_gate and not frames_approved:
            st.caption("🛡️ **Image-to-Video Safety Gate Active:** Generate & approve your 2D scene frames in Step 1 above to unlock Step 2 animation with zero wasted credits.")
            with st.expander("⚡ Advanced: Direct 1-Click Render (Skip 2D Frame Preview)", expanded=False):
                direct_skip_render = st.button(
                    "🚀 Render Directly Without Previewing Frames",
                    use_container_width=True,
                    disabled=any_busy,
                    key=f"btn_direct_skip_{pid}",
                )

        if start_render or direct_skip_render or resume_stitch:
            st.session_state["agent3_output"] = None
            task_est_cost = 0.22 if resume_stitch else est_usd
            try:
                launched = worker.submit_task(
                    task_key=render_task_key,
                    project_id=pid,
                    job_type="master_render",
                    label=f"{'Resume' if resume_stitch else 'Create'} Video: {a1.topic[:32]}",
                    fn=run_agent3_media_pipeline,
                    kwargs={
                        "project_id": pid,
                        "agent1": a1,
                        "agent2": a2,
                        "render_quality": render_quality,
                        "force_ai_cinema": force_ai_cinema,
                        "cinema_preset": cinema_preset_s3,
                        "bgm_preset": selected_bgm_preset_s3,
                        "custom_bgm_path": custom_bgm_file_path,
                        "bgm_duck_db": selected_bgm_duck_db,
                        "enable_foley_sfx": enable_foley_sfx,
                        "reuse_existing_clips": bool(resume_stitch),
                        "include_avatar_in_thumbnail": include_avatar_thumb,
                        "avatar_thumbnail_mode": avatar_thumb_mode,
                        "include_avatar_in_video": include_avatar_video,
                        "creator_side": creator_side,
                        "prefer_fast_local_tts": fast_tts,
                        "use_ai_thumbnail": (render_quality != "fast_studio_preview"),
                        "animate_scene_indices": selected_i2v_ids if (start_render and approved_kf_indices) else None,
                        "cost_limit_usd": active_daily_limit,
                        "config": cfg,
                        "db": db,
                    },
                    estimated_cost_usd=task_est_cost,
                    cost_limit_usd=active_daily_limit,
                )
                if launched:
                    st.session_state["render_task_key"] = render_task_key
                    st.toast("Video production started!", icon="🎬")
                    st.rerun()
            except BudgetLimitExceededError as b_err:
                st.error(f"🛑 {b_err}")

        if regen_thumb:
            a3_existing = st.session_state.get("agent3_output")
            thumb_dest = (
                Path(a3_existing["thumbnail_16x9_path"])
                if a3_existing and a3_existing.get("thumbnail_16x9_path")
                else cfg.projects_dir / f"{pid}_{sanitize_slug(a1.topic)}" / "renders" / "thumbnail_16x9.png"
            )
            with st.status("🖼️ Designing your new thumbnail...", expanded=True) as th_st:
                st.write("🎨 Composing high-contrast artwork & headline...")
                t_path, _ = generate_high_ctr_thumbnail(
                    thumb_dest,
                    topic=a1.topic,
                    niche=a1.niche,
                    headline=a1.thumbnail_hook_headline,
                    badge_label=a1.thumbnail_badge_label,
                    graphic_concept=a1.thumbnail_graphic_concept,
                    include_creator_avatar=include_avatar_thumb,
                    avatar_mode=avatar_thumb_mode,
                    creator_side=creator_side,
                    config=cfg,
                    use_ai_image_api=True,
                )
                th_st.update(label="✅ Thumbnail ready!", state="complete", expanded=False)
            st.image(str(t_path), caption="Updated Video Thumbnail", use_container_width=True)

        # Solid Structured Production Progress Deck
        stage_jobs = db.get_project_jobs(pid, job_type="media_stage")
        if stage_jobs or is_rendering:
            overall_pct = int(sum(j["progress_pct"] for j in stage_jobs) / max(1, len(stage_jobs))) if stage_jobs else 5
            hdr_dot = '<span class="omni-live-dot"></span>' if is_rendering else '<span class="omni-done-dot"></span>'
            hdr_title = "Producing Your Video..." if is_rendering else "Production Progress"
            hdr_badge = (
                f'<span class="omni-badge omni-badge-run">{overall_pct}% Complete</span>'
                if is_rendering
                else f'<span class="omni-badge omni-badge-done">{overall_pct}% Ready</span>'
            )

            rows_html: List[str] = []
            for j in stage_jobs:
                st_val = j.get("status", "queued")
                if st_val == "completed":
                    row_cls = "omni-stage-row omni-stage-row-done"
                    pill = '<span class="omni-badge omni-badge-done">Done</span>'
                elif st_val == "failed":
                    row_cls = "omni-stage-row"
                    pill = '<span class="omni-badge omni-badge-err">Error</span>'
                elif st_val == "running":
                    row_cls = "omni-stage-row omni-stage-row-active"
                    pill = f'<span class="omni-badge omni-badge-run">{j["progress_pct"]}%</span>'
                else:
                    row_cls = "omni-stage-row"
                    pill = '<span class="omni-badge omni-badge-wait">Queued</span>'
                detail_txt = j.get("message") or ""
                rows_html.append(
                    f'<div class="{row_cls}">'
                    f'<span class="omni-stage-name">{j["label"]}</span>'
                    f'<span class="omni-stage-detail"><span>{detail_txt}</span>{pill}</span>'
                    f'</div>'
                )

            st.markdown(
                f"""
                <div class="omni-process-deck">
                    <div class="omni-process-hdr">
                        <span class="omni-process-title">{hdr_dot} {hdr_title}</span>
                        {hdr_badge}
                    </div>
                    {''.join(rows_html)}
                </div>
                """,
                unsafe_allow_html=True,
            )
            st.progress(overall_pct / 100.0)

            err_msg = worker.get_task_error(render_task_key)
            if err_msg:
                st.error(f"Production paused due to an error: {err_msg}")

            if is_rendering:
                st.caption("Working in the background — updating live every 2 seconds...")
                time.sleep(2.0)
                st.rerun()

        # Preview Rendered Deliverables
        a3_data = st.session_state.get("agent3_output")
        if a3_data and not is_rendering:
            a3 = Agent3Output.model_validate(a3_data)
            st.success(
                f"✅ **Your Video is Ready!** Full HD (`{format_timestamp(a3.final_duration_sec)}`) · "
                f"Shorts (`{format_timestamp(a3.shorts_duration_sec)}`) · {a3.scene_count_rendered} scenes"
            )

            p_c1, p_c2 = st.columns([1.15, 1.0])
            with p_c1:
                st.markdown("#### 📺 Full HD Video (16:9)")
                if Path(a3.video_16x9_path).exists():
                    st.video(a3.video_16x9_path)
                    st.download_button(
                        "⬇️ Download Full HD Video (.mp4)",
                        data=lambda p=a3.video_16x9_path: Path(p).read_bytes(),
                        file_name=Path(a3.video_16x9_path).name,
                        mime="video/mp4",
                        use_container_width=True,
                        key=f"dl_16x9_{pid}",
                    )
            with p_c2:
                st.markdown("#### 🖼️ Video Thumbnail")
                if Path(a3.thumbnail_16x9_path).exists():
                    st.image(a3.thumbnail_16x9_path, use_container_width=True)
                    st.download_button(
                        "⬇️ Download Thumbnail (.png)",
                        data=lambda p=a3.thumbnail_16x9_path: Path(p).read_bytes(),
                        file_name="thumbnail_16x9.png",
                        mime="image/png",
                        use_container_width=True,
                        key=f"dl_thumb_{pid}",
                    )

            with st.expander("📱 Vertical Short (9:16) & Video Chapters", expanded=False):
                sh_c1, sh_c2 = st.columns([1.0, 1.2])
                with sh_c1:
                    if Path(a3.video_9x16_shorts_path).exists():
                        st.video(a3.video_9x16_shorts_path)
                        st.download_button(
                            "⬇️ Download Vertical Short (.mp4)",
                            data=lambda p=a3.video_9x16_shorts_path: Path(p).read_bytes(),
                            file_name=Path(a3.video_9x16_shorts_path).name,
                            mime="video/mp4",
                            use_container_width=True,
                            key=f"dl_9x16_{pid}",
                        )
                with sh_c2:
                    st.markdown("**Video Chapters:**")
                    st.code(a3.exact_chapters_text, language="text")
                    char_anchor_img = Path(a3.project_dir) / "renders" / "character_anchor.png"
                    if char_anchor_img.exists():
                        st.markdown("**🎭 Locked Character Reference Face:**")
                        st.image(str(char_anchor_img), width=220)

            st.markdown("")
            if st.button("Continue to Publish ➡️", type="primary", use_container_width=True):
                st.session_state["omni_step"] = 4
                db.update_project_stage(pid, current_step=4)
                st.rerun()


# ==============================================================================
# STEP 4 — PUBLISH TO YOUTUBE
# ==============================================================================
elif step == 4:
    st.subheader("Publish to YouTube")
    a1_data = st.session_state.get("agent1_output")
    a3_data = st.session_state.get("agent3_output")
    pid = st.session_state.get("omni_project_id")

    if not a1_data or not a3_data or not pid:
        st.info("Finish generating your video in Video Studio first to publish to YouTube.")
    else:
        a1 = Agent1Output.model_validate(a1_data)
        a3 = Agent3Output.model_validate(a3_data)
        long_pub_task_key = f"publish_long_{pid}"
        short_pub_task_key = f"publish_short_{pid}"

        fresh_proj = db.get_project(pid)
        if fresh_proj and fresh_proj.get("agent4_data"):
            st.session_state["agent4_output"] = fresh_proj["agent4_data"]

        # Resolve latest published Long Video & Short Video records cleanly from SQLite
        pub_logs = db.get_publish_records(project_id=pid, limit=12)
        long_pub_rec = next(
            (
                r for r in pub_logs
                if r.get("video_id")
                and "short" not in str(r.get("status") or "").lower()
                and "/shorts/" not in str(r.get("watch_url") or "").lower()
                and "#shorts" not in str(r.get("title") or "").lower()
            ),
            None,
        )
        short_pub_rec = next(
            (
                r for r in pub_logs
                if r.get("video_id")
                and (
                    "short" in str(r.get("status") or "").lower()
                    or "/shorts/" in str(r.get("watch_url") or "").lower()
                    or "#shorts" in str(r.get("title") or "").lower()
                )
            ),
            None,
        )
        resolved_long_vid = ""
        resolved_long_url = ""
        resolved_long_studio = ""
        if long_pub_rec and long_pub_rec.get("video_id"):
            resolved_long_vid = str(long_pub_rec["video_id"]).strip()
            resolved_long_url = f"https://www.youtube.com/watch?v={resolved_long_vid}"
            resolved_long_studio = long_pub_rec.get("studio_url") or f"https://studio.youtube.com/video/{resolved_long_vid}/edit"
        elif fresh_proj and fresh_proj.get("youtube_video_id"):
            resolved_long_vid = str(fresh_proj["youtube_video_id"]).strip()
            resolved_long_url = f"https://www.youtube.com/watch?v={resolved_long_vid}"
            resolved_long_studio = f"https://studio.youtube.com/video/{resolved_long_vid}/edit"

        connected_chs_s4 = list_connected_youtube_channels(cfg, db)
        active_ch_id_s4 = st.session_state.get("omni_channel_id", "")
        with st.container(border=True):
            if connected_chs_s4:
                ch_opts_s4: Dict[str, Dict[str, Any]] = {}
                default_s4_idx = 0
                for ci, ch in enumerate(connected_chs_s4):
                    cid = ch.get("channel_id") or ""
                    base_lbl = _format_channel_label(ch, with_icon=True)
                    lbl = base_lbl
                    n_dup = 2
                    while lbl in ch_opts_s4:
                        lbl = f"{base_lbl} #{n_dup}"
                        n_dup += 1
                    ch_opts_s4[lbl] = ch
                    if cid == active_ch_id_s4:
                        default_s4_idx = ci
                sel_ch_lbl_s4 = st.selectbox(
                    "📺 Target YouTube Channel:",
                    options=list(ch_opts_s4.keys()),
                    index=default_s4_idx,
                    key="step4_channel_sel",
                )
                sel_ch_obj_s4 = ch_opts_s4[sel_ch_lbl_s4]
                active_ch_id_s4 = sel_ch_obj_s4.get("channel_id") or ""
                st.session_state["omni_channel_id"] = active_ch_id_s4
                st.session_state["omni_channel_title"] = sel_ch_obj_s4.get("channel_title") or ""
                creds, tok_rec = get_valid_youtube_credentials(cfg, db, channel_id=active_ch_id_s4)
                if creds and tok_rec:
                    st.success(
                        f"✅ **Ready to Publish** to **{_format_channel_label(tok_rec, with_icon=False)}**"
                    )
                else:
                    st.warning("⚠️ Channel sign-in expired — reconnect below before publishing.")
            else:
                creds, tok_rec = None, None
                st.warning("🔒 **No YouTube Channel Connected Yet** — Connect your channel below to upload directly.")

            with st.expander("➕ Connect or Manage YouTube Channels", expanded=(creds is None)):
                _render_connect_channel_drawer("step4", connected_chs_s4)

        playlists = list_user_youtube_playlists(cfg, db, channel_id=active_ch_id_s4) if creds else []
        pl_map = {"(No Playlist)": "NONE"}
        for pl in playlists:
            pl_map[pl["title"]] = pl["id"]
        pl_keys_s4 = list(pl_map.keys())
        pre_pl_id = st.session_state.get("omni_playlist_id", "NONE")
        pl_s4_idx = 0
        for pi, pk in enumerate(pl_keys_s4):
            if pl_map[pk] == pre_pl_id:
                pl_s4_idx = pi
                break

        is_uploading_long = worker.is_running(long_pub_task_key)
        is_uploading_short = worker.is_running(short_pub_task_key)
        any_uploading = is_uploading_long or is_uploading_short
        target_ch_display = st.session_state.get("omni_channel_title") or "YouTube"

        # ======================================================================
        # PUBLISH STEP 1 OF 2 — FULL-LENGTH VIDEO (16:9)
        # ======================================================================
        with st.container(border=True):
            if resolved_long_url:
                st.markdown("#### ✅ Step 1 of 2: Full-Length Video (16:9) — Published")
                st.success(
                    f"📺 **Full-Length Video Live:** [{resolved_long_url}]({resolved_long_url})  ·  "
                    f"[Open in Studio]({resolved_long_studio})"
                )
                thumb_p_s4 = Path(a3.thumbnail_16x9_path)
                if resolved_long_vid and thumb_p_s4.exists() and creds is not None:
                    if st.button(
                        "🖼️ Attach / Update Thumbnail on Published Video",
                        use_container_width=True,
                        disabled=any_uploading,
                        key=f"btn_attach_thumb_{pid}_{resolved_long_vid}",
                    ):
                        with st.spinner("Optimizing thumbnail (<2 MB JPEG) & attaching to YouTube..."):
                            ok_th, msg_th = attach_thumbnail_to_published_video(
                                resolved_long_vid,
                                thumb_p_s4,
                                channel_id=active_ch_id_s4 or None,
                                config=cfg,
                                db=db,
                            )
                        if ok_th:
                            st.success(f"✅ {msg_th}!")
                        else:
                            st.warning(f"⚠️ Could not attach thumbnail: {msg_th}")
            else:
                st.markdown("#### 📺 Step 1 of 2: Publish Full-Length Video (16:9) First")
                st.caption("Upload your main video first so its YouTube URL is automatically inserted into your Hook Short's description in Step 2 below.")

            long_title = st.text_input(
                "Full Video Title:",
                value=a1.selected_title,
                max_chars=100,
                key=f"pub_long_title_{pid}",
            )
            base_long_desc = a1.seo_description
            if a3.exact_chapters_text and "00:00" not in base_long_desc:
                base_long_desc = f"{base_long_desc}\n\n⏱️ CHAPTERS:\n{a3.exact_chapters_text}"
            long_desc = st.text_area(
                "Full Video Description (includes Chapters):",
                value=base_long_desc,
                height=145,
                key=f"pub_long_desc_{pid}",
            )

            pc1, pc2, pc3 = st.columns(3)
            with pc1:
                long_privacy = st.selectbox("🔒 Visibility:", options=["private", "unlisted", "public"], index=0, key=f"pub_long_priv_{pid}")
            with pc2:
                long_use_sched = st.checkbox("📅 Schedule Publish Time", value=False, key=f"pub_long_sched_{pid}")
                long_sched_date = st.date_input("Publish Date (IST):", value=datetime.date.today() + datetime.timedelta(days=1), disabled=not long_use_sched, key=f"pub_long_sdate_{pid}")
                long_sched_time = st.time_input("Publish Time (IST):", value=datetime.time(18, 30), disabled=not long_use_sched, key=f"pub_long_stime_{pid}")
            with pc3:
                sel_long_pl_lbl = st.selectbox(
                    "📂 Add to Playlist:",
                    options=pl_keys_s4,
                    index=pl_s4_idx,
                    key=f"pub_long_pl_{active_ch_id_s4}_{pid}",
                )
                sel_long_pl_id = pl_map[sel_long_pl_lbl]
                st.session_state["omni_playlist_id"] = sel_long_pl_id
                st.session_state["omni_playlist_title"] = sel_long_pl_lbl

            submit_long_pub = st.button(
                f"🚀 Step 1: {'Re-Upload' if resolved_long_url else 'Publish'} Full-Length Video to {target_ch_display}",
                type="secondary" if resolved_long_url else "primary",
                use_container_width=True,
                disabled=(any_uploading or creds is None),
                key=f"btn_pub_long_{pid}",
            )

            if submit_long_pub:
                st.session_state["publish_balloons_shown"] = False
                sched_iso_long: Optional[str] = None
                if long_use_sched:
                    ist_tz = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
                    dt_ist = datetime.datetime.combine(long_sched_date, long_sched_time, tzinfo=ist_tz)
                    sched_iso_long = dt_ist.astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                worker.submit_task(
                    task_key=long_pub_task_key,
                    project_id=pid,
                    job_type="youtube_upload_long",
                    label=f"Uploading Full Video to {target_ch_display}",
                    fn=run_agent4_youtube_publish,
                    kwargs={
                        "project_id": pid,
                        "video_path": Path(a3.video_16x9_path),
                        "thumbnail_path": Path(a3.thumbnail_16x9_path),
                        "title": long_title,
                        "description": long_desc,
                        "exact_chapters_text": a3.exact_chapters_text,
                        "tags": a1.tags,
                        "privacy_status": long_privacy,
                        "scheduled_publish_at_iso": sched_iso_long,
                        "playlist_id": None if sel_long_pl_id == "NONE" else sel_long_pl_id,
                        "channel_id": active_ch_id_s4 or None,
                        "is_short": False,
                        "config": cfg,
                        "db": db,
                    },
                )
                st.rerun()

            long_jobs = db.get_project_jobs(pid, job_type="youtube_upload_long")
            if long_jobs or is_uploading_long:
                latest_lu = long_jobs[-1] if long_jobs else {"progress_pct": 5, "message": "Preparing Full Video upload..."}
                lu_dot = '<span class="omni-live-dot"></span>' if is_uploading_long else '<span class="omni-done-dot"></span>'
                lu_hdr = "Uploading Full-Length Video..." if is_uploading_long else "Step 1 Upload Status"
                st.markdown(
                    f"""
                    <div class="omni-process-deck">
                        <div class="omni-process-hdr">
                            <span class="omni-process-title">{lu_dot} {lu_hdr}</span>
                            <span class="omni-badge omni-badge-run">{latest_lu['progress_pct']}%</span>
                        </div>
                        <div class="omni-stage-row omni-stage-row-active">
                            <span class="omni-stage-name">Full HD Video (16:9)</span>
                            <span class="omni-stage-detail">{latest_lu['message']}</span>
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
                st.progress(latest_lu["progress_pct"] / 100.0)
                lu_err = worker.get_task_error(long_pub_task_key)
                if lu_err:
                    st.error(f"Step 1 upload paused: {lu_err}")

        # ======================================================================
        # PUBLISH STEP 2 OF 2 — HOOK SHORT (9:16 · 10–20s) LINKING TO FULL VIDEO
        # ======================================================================
        with st.container(border=True):
            short_dur_str = f"{a3.shorts_duration_sec:.1f}s"
            if short_pub_rec and short_pub_rec.get("watch_url"):
                st.markdown(f"#### ✅ Step 2 of 2: Hook Short (9:16 · {short_dur_str}) — Published")
                st.success(
                    f"📱 **Hook Short Live:** [{short_pub_rec['watch_url']}]({short_pub_rec['watch_url']})  ·  "
                    f"[Open in Studio]({short_pub_rec.get('studio_url') or ''})"
                )
            else:
                st.markdown(f"#### 📱 Step 2 of 2: Publish Hook Short (9:16 · {short_dur_str}) Linking to Full Video")

            # Auto-sync the Full Video URL into the Short's URL input & Description whenever Step 1 completes!
            url_sync_key = f"pub_short_synced_url_{pid}"
            short_url_widget_key = f"pub_short_long_url_{pid}"
            short_desc_widget_key = f"pub_short_desc_{pid}"
            effective_hook_txt = (a3.short_hook_script or a1.short_hook_script or "").strip()

            if resolved_long_url and st.session_state.get(url_sync_key) != resolved_long_url:
                st.session_state[url_sync_key] = resolved_long_url
                st.session_state[short_url_widget_key] = resolved_long_url
                st.session_state[short_desc_widget_key] = build_short_funnel_description(
                    topic=a1.topic,
                    language_tone=a1.language_tone,
                    short_hook_script=effective_hook_txt,
                    long_video_url=resolved_long_url,
                    tags=a1.tags,
                )
            elif short_desc_widget_key not in st.session_state:
                st.session_state[short_url_widget_key] = resolved_long_url
                st.session_state[short_desc_widget_key] = build_short_funnel_description(
                    topic=a1.topic,
                    language_tone=a1.language_tone,
                    short_hook_script=effective_hook_txt,
                    long_video_url=resolved_long_url,
                    tags=a1.tags,
                )

            if not resolved_long_url:
                st.info("⬆️ Publish your Full-Length Video in **Step 1** above first so its YouTube URL auto-fills below (or paste any existing YouTube video URL manually).")

            short_linked_url = st.text_input(
                "🔗 Full-Length Video YouTube URL (Auto-Embedded in Short Description):",
                placeholder="https://www.youtube.com/watch?v=... (auto-filled after Step 1)",
                key=short_url_widget_key,
            )
            # If user manually typed/pasted a URL, auto-sync it into the Short description!
            if short_linked_url.strip() and short_linked_url.strip() not in st.session_state.get(short_desc_widget_key, ""):
                st.session_state[short_desc_widget_key] = build_short_funnel_description(
                    topic=a1.topic,
                    language_tone=a1.language_tone,
                    short_hook_script=effective_hook_txt,
                    long_video_url=short_linked_url.strip(),
                    tags=a1.tags,
                )

            short_title = st.text_input(
                "Hook Short Title (includes #Shorts):",
                value=f"{a1.selected_title[:84]} #Shorts",
                max_chars=100,
                key=f"pub_short_title_{pid}",
            )
            short_desc = st.text_area(
                "Hook Short Description (Full Video URL Embedded at Top):",
                height=135,
                key=short_desc_widget_key,
            )

            sc1, sc2, sc3 = st.columns(3)
            with sc1:
                short_privacy = st.selectbox("🔒 Short Visibility:", options=["private", "unlisted", "public"], index=0, key=f"pub_short_priv_{pid}")
            with sc2:
                short_use_sched = st.checkbox("📅 Schedule Short", value=False, key=f"pub_short_sched_{pid}")
                short_sched_date = st.date_input("Short Date (IST):", value=datetime.date.today() + datetime.timedelta(days=1), disabled=not short_use_sched, key=f"pub_short_sdate_{pid}")
                short_sched_time = st.time_input("Short Time (IST):", value=datetime.time(19, 0), disabled=not short_use_sched, key=f"pub_short_stime_{pid}")
            with sc3:
                sel_short_pl_lbl = st.selectbox(
                    "📂 Short Playlist:",
                    options=pl_keys_s4,
                    index=pl_s4_idx,
                    key=f"pub_short_pl_{active_ch_id_s4}_{pid}",
                )
                sel_short_pl_id = pl_map[sel_short_pl_lbl]

            submit_short_pub = st.button(
                f"🚀 Step 2: Publish Hook Short ({short_dur_str}) with Full Video Link",
                type="primary" if resolved_long_url else "secondary",
                use_container_width=True,
                disabled=(any_uploading or creds is None),
                key=f"btn_pub_short_{pid}",
            )

            if submit_short_pub:
                st.session_state["publish_balloons_shown"] = False
                sched_iso_short: Optional[str] = None
                if short_use_sched:
                    ist_tz = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
                    dt_ist = datetime.datetime.combine(short_sched_date, short_sched_time, tzinfo=ist_tz)
                    sched_iso_short = dt_ist.astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                worker.submit_task(
                    task_key=short_pub_task_key,
                    project_id=pid,
                    job_type="youtube_upload_short",
                    label=f"Uploading Hook Short to {target_ch_display}",
                    fn=run_agent4_youtube_publish,
                    kwargs={
                        "project_id": pid,
                        "video_path": Path(a3.video_9x16_shorts_path),
                        "thumbnail_path": None,
                        "title": short_title,
                        "description": short_desc,
                        "exact_chapters_text": "",
                        "tags": a1.tags + ["Shorts"],
                        "privacy_status": short_privacy,
                        "scheduled_publish_at_iso": sched_iso_short,
                        "playlist_id": None if sel_short_pl_id == "NONE" else sel_short_pl_id,
                        "channel_id": active_ch_id_s4 or None,
                        "is_short": True,
                        "linked_long_video_url": short_linked_url.strip() or resolved_long_url,
                        "config": cfg,
                        "db": db,
                    },
                )
                st.rerun()

            short_jobs = db.get_project_jobs(pid, job_type="youtube_upload_short")
            if short_jobs or is_uploading_short:
                latest_su = short_jobs[-1] if short_jobs else {"progress_pct": 5, "message": "Preparing Hook Short upload..."}
                su_dot = '<span class="omni-live-dot"></span>' if is_uploading_short else '<span class="omni-done-dot"></span>'
                su_hdr = "Uploading Hook Short..." if is_uploading_short else "Step 2 Upload Status"
                st.markdown(
                    f"""
                    <div class="omni-process-deck">
                        <div class="omni-process-hdr">
                            <span class="omni-process-title">{su_dot} {su_hdr}</span>
                            <span class="omni-badge omni-badge-run">{latest_su['progress_pct']}%</span>
                        </div>
                        <div class="omni-stage-row omni-stage-row-active">
                            <span class="omni-stage-name">Hook Short (9:16)</span>
                            <span class="omni-stage-detail">{latest_su['message']}</span>
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
                st.progress(latest_su["progress_pct"] / 100.0)
                su_err = worker.get_task_error(short_pub_task_key)
                if su_err:
                    st.error(f"Step 2 upload paused: {su_err}")

        if any_uploading:
            st.caption("Uploading in the background — updating live every 1.5 seconds...")
            time.sleep(1.5)
            st.rerun()

        if pub_logs:
            with st.expander("📋 Recent Uploads", expanded=False):
                st.dataframe(pub_logs, use_container_width=True, hide_index=True)

        st.markdown("---")
        if st.button("➕ Start a New Video Project", use_container_width=True):
            _reset_workspace()
            st.rerun()
