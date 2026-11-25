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
import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import streamlit as st

from backend.agent1_seo_storyboard import run_agent1_seo_and_storyboard
from backend.agent2_scene_scripter import run_agent2_scene_scripting
from backend.agent3_media_composer import run_agent3_media_pipeline
from backend.agent4_youtube_publisher import (
    build_youtube_oauth_url,
    exchange_oauth_code_and_store,
    get_valid_youtube_credentials,
    list_user_youtube_playlists,
    run_agent4_youtube_publish,
)
from backend.config import (
    SUPPORTED_LANGUAGES,
    SUPPORTED_NICHES,
    OmniStudioConfig,
    format_timestamp,
    sanitize_slug,
    sync_streamlit_secrets_to_env,
)
from backend.schemas import Agent1Output, Agent2Output, Agent3Output, Agent4Output, SceneClipSpec
from render_engine.thumbnail_studio import generate_high_ctr_thumbnail
from storage.db import get_db
from worker import get_worker_manager

# ==============================================================================
# PAGE CONFIG & MOBILE-FIRST RESPONSIVE STYLING
# ==============================================================================
st.set_page_config(
    page_title="OMNI STUDIO — Multi-Agent AI Video Engine",
    page_icon="🎬",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown(
    """
    <style>
    /* Clean, spacious, uncluttered dark studio theme optimized for Mobile, Tablet & Desktop */
    .block-container {
        padding-top: 1.1rem !important;
        padding-bottom: 2.8rem !important;
        max-width: 1120px !important;
    }
    .omni-header {
        background: linear-gradient(135deg, #0b1324 0%, #121f38 60%, #0d2b3e 100%);
        border: 1px solid rgba(0, 229, 255, 0.32);
        border-radius: 16px;
        padding: 16px 20px;
        margin-bottom: 14px;
    }
    .omni-header h1 {
        margin: 0;
        font-size: 1.55rem;
        letter-spacing: 0.3px;
        color: #f8fafc;
    }
    .omni-header p {
        margin: 4px 0 0 0;
        color: #94a3b8;
        font-size: 0.9rem;
    }
    .omni-stepper {
        display: flex;
        flex-wrap: nowrap;
        overflow-x: auto;
        gap: 8px;
        padding: 10px 12px;
        background: #0f172a;
        border: 1px solid #1e293b;
        border-radius: 14px;
        margin-bottom: 18px;
        -webkit-overflow-scrolling: touch;
    }
    .omni-step-pill {
        flex: 1 1 auto;
        min-width: 128px;
        text-align: center;
        padding: 8px 10px;
        border-radius: 10px;
        font-size: 0.84rem;
        font-weight: 700;
        white-space: nowrap;
        border: 1px solid #334155;
        color: #94a3b8;
        background: #111827;
    }
    .omni-step-active {
        background: linear-gradient(90deg, #00c853 0%, #00e5ff 100%);
        color: #04101d !important;
        border-color: transparent !important;
        box-shadow: 0 0 14px rgba(0, 229, 255, 0.35);
    }
    .omni-step-done {
        background: rgba(16, 185, 129, 0.16);
        color: #6ee7b7 !important;
        border-color: rgba(16, 185, 129, 0.45) !important;
    }
    .omni-card {
        background: #101828;
        border: 1px solid #1f2937;
        border-radius: 14px;
        padding: 14px 16px;
        margin-bottom: 12px;
    }
    .omni-status-row {
        display: flex;
        justify-content: space-between;
        align-items: center;
        gap: 8px;
        padding: 8px 12px;
        border-radius: 10px;
        background: #0f172a;
        border: 1px solid #1e293b;
        margin-bottom: 6px;
        font-size: 0.88rem;
    }
    @media (max-width: 768px) {
        .block-container {
            padding-left: 0.75rem !important;
            padding-right: 0.75rem !important;
        }
        .omni-header h1 {
            font-size: 1.25rem;
        }
        .omni-step-pill {
            min-width: 112px;
            font-size: 0.78rem;
            padding: 7px 8px;
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
        "omni_step": 1,
        "omni_project_id": None,
        "omni_topic": "",
        "omni_niche": SUPPORTED_NICHES[2],  # AI & Future Tech default
        "omni_language": SUPPORTED_LANGUAGES[0],
        "omni_target_minutes": 6.0,
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


def _reset_workspace() -> None:
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
    st.session_state["omni_project_id"] = proj["id"]
    st.session_state["omni_topic"] = proj["topic"]
    st.session_state["omni_niche"] = proj["niche"] if proj["niche"] in SUPPORTED_NICHES else SUPPORTED_NICHES[0]
    st.session_state["omni_language"] = (
        proj["language_tone"] if proj["language_tone"] in SUPPORTED_LANGUAGES else SUPPORTED_LANGUAGES[0]
    )
    st.session_state["omni_target_minutes"] = float(proj.get("target_minutes") or 6.0)
    st.session_state["agent1_output"] = proj.get("agent1_data")
    st.session_state["agent2_output"] = proj.get("agent2_data")
    st.session_state["agent3_output"] = proj.get("agent3_data")
    st.session_state["agent4_output"] = proj.get("agent4_data")
    st.session_state["omni_step"] = max(1, min(4, int(proj.get("current_step") or 1)))
    st.session_state["publish_balloons_shown"] = False


sync_streamlit_secrets_to_env()
_init_session_state()
cfg = OmniStudioConfig()
db = get_db()
worker = get_worker_manager()

# Handle OAuth 2.0 callback `?code=...` cleanly if Google redirected back to Streamlit
query_code = st.query_params.get("code")
if query_code and not st.session_state.get("_oauth_code_handled"):
    ok_cb, msg_cb = exchange_oauth_code_and_store(
        str(query_code),
        cfg.youtube_client_secrets,
        redirect_uri=cfg.youtube_redirect_uri,
        db=db,
    )
    st.session_state["_oauth_code_handled"] = True
    if ok_cb:
        st.toast(msg_cb, icon="✅")
    else:
        st.toast(f"OAuth exchange note: {msg_cb}", icon="⚠️")


# ==============================================================================
# COMPACT SIDEBAR: RECENT PROJECTS & WORKSPACE CONTROLS (COLLAPSED BY DEFAULT)
# ==============================================================================
with st.sidebar:
    st.markdown("### 🗂️ OMNI STUDIO Projects")
    if st.button("➕ New Fresh Video Project", use_container_width=True, type="primary"):
        _reset_workspace()
        st.rerun()

    recent_projects = db.list_projects(limit=12)
    if recent_projects:
        st.caption("Resume a saved SQLite workspace:")
        for rp in recent_projects:
            lbl = f"S{rp['current_step']} • {rp['topic'][:26]} ({rp['status']})"
            if st.button(lbl, key=f"load_proj_{rp['id']}", use_container_width=True):
                _load_project_into_session(rp["id"])
                st.rerun()
    else:
        st.caption("No saved projects yet. Start in Step 1!")

    st.markdown("---")
    st.caption(f"Creator Likeness: `{cfg.creator_handle}` ({len(cfg.likeness_reference_paths)}/3 portraits loaded)")
    st.caption(f"AI Auth: `{cfg.active_auth_summary}`")
    st.caption(f"BGM Ducking: `{cfg.bgm_duck_db} dB` • `{cfg.resolution}`")


# ==============================================================================
# TOP HEADER & MOBILE/TABLET HORIZONTAL STEPPER
# ==============================================================================
st.markdown(
    """
    <div class="omni-header">
        <h1>🎬 OMNI STUDIO — Multi-Niche AI Video Engine</h1>
        <p>Generic 4-Agent Pipeline for High-Retention 5–8 Min YouTube Videos &amp; Shorts • Any Niche • Direct YouTube Publish</p>
    </div>
    """,
    unsafe_allow_html=True,
)

step = int(st.session_state["omni_step"])
steps_meta = [
    (1, "1. SEO & Hooks"),
    (2, "2. Scene Scripting"),
    (3, "3. Media Rendering"),
    (4, "4. YT Publish"),
]

pills_html = []
for s_num, s_label in steps_meta:
    if s_num == step:
        cls = "omni-step-pill omni-step-active"
    elif s_num < step:
        cls = "omni-step-pill omni-step-done"
    else:
        cls = "omni-step-pill"
    pills_html.append(f'<div class="{cls}">{s_label}</div>')

st.markdown(f'<div class="omni-stepper">{"".join(pills_html)}</div>', unsafe_allow_html=True)

# Compact clickable quick-navigation row for already-unlocked stages
nav_cols = st.columns(4)
max_unlocked = 1
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
        if st.button(s_label, key=f"nav_step_{s_num}", use_container_width=True, disabled=disabled, type=btn_type):
            st.session_state["omni_step"] = s_num
            if st.session_state.get("omni_project_id"):
                db.update_project_stage(st.session_state["omni_project_id"], current_step=s_num)
            st.rerun()

st.markdown("")


# ==============================================================================
# STEP 1 — AGENT 1: SEARCH, SEO & STORYBOARD AGENT
# ==============================================================================
if step == 1:
    st.subheader("Step 1 • Agent 1: Search, SEO & High-Retention Storyboard")

    with st.container(border=True):
        topic_val = st.text_input(
            "🎯 Video Topic (Any Subject / Any Niche):",
            value=st.session_state["omni_topic"],
            placeholder="e.g., The History of Cryptocurrency, How Autonomous Vehicles Navigate, 10 AI Tools Changing the World...",
            key="input_topic_field",
        )
        c1, c2, c3 = st.columns([1.2, 1.3, 0.9])
        with c1:
            niche_val = st.selectbox(
                "🧭 Niche:",
                options=SUPPORTED_NICHES,
                index=SUPPORTED_NICHES.index(st.session_state["omni_niche"])
                if st.session_state["omni_niche"] in SUPPORTED_NICHES
                else 0,
                key="input_niche_field",
            )
        with c2:
            lang_val = st.selectbox(
                "🗣️ Language & Tone:",
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
                help="5–8 minutes generates 30–50 granular scenes (8–12s visual reset rule).",
                key="input_dur_field",
            )

        run_a1 = st.button(
            "🔎 Run Agent 1: Mine YouTube SEO, Hooks & Storyboard",
            type="primary",
            use_container_width=True,
        )

    if run_a1:
        if not topic_val.strip():
            st.warning("Enter any Topic above to launch Agent 1.")
        else:
            st.session_state["omni_topic"] = topic_val.strip()
            st.session_state["omni_niche"] = niche_val
            st.session_state["omni_language"] = lang_val
            st.session_state["omni_target_minutes"] = float(dur_val)

            with st.spinner(f"Agent 1 scanning YouTube trends, mining keywords & drafting storyboard for '{topic_val.strip()}'..."):
                a1_obj = run_agent1_seo_and_storyboard(
                    topic=topic_val.strip(),
                    niche=niche_val,
                    language_tone=lang_val,
                    target_duration_minutes=float(dur_val),
                    config=cfg,
                )
                pid = st.session_state.get("omni_project_id")
                if not pid:
                    pid = db.create_project(topic_val.strip(), niche_val, lang_val, float(dur_val))
                    st.session_state["omni_project_id"] = pid
                db.update_project_stage(
                    pid,
                    current_step=1,
                    status="step1_ready",
                    agent1_data=a1_obj.model_dump(),
                )
                st.session_state["agent1_output"] = a1_obj.model_dump()
                # Clear downstream stale stages only when user explicitly re-runs Agent 1
                st.session_state["agent2_output"] = None
                st.session_state["agent3_output"] = None
                st.session_state["agent4_output"] = None
            st.success("✅ Agent 1 completed! Review and edit any SEO or storyboard fields below.")

    a1_data = st.session_state.get("agent1_output")
    if a1_data:
        a1 = Agent1Output.model_validate(a1_data)

        # Collapsible Competitor & Audience Research Drawer
        with st.expander("📊 YouTube Competitor Research, Audience Questions & Visual Hooks", expanded=False):
            if a1.competitor_insights:
                st.markdown("**Top-Performing Videos Mined via YouTube Data API v3:**")
                for comp in a1.competitor_insights:
                    st.markdown(
                        f"- **{comp.title}** ({comp.channel_title}) — `{comp.view_count:,} views` • *Hook:* {comp.hook_pattern}"
                    )
            else:
                st.caption("YouTube autocomplete & Google Search grounding used (add `YOUTUBE_API_KEY` in `.env` for live view-count mining).")
            st.markdown("**Common Audience Questions:**")
            for q in a1.common_audience_questions:
                st.markdown(f"- {q}")
            st.markdown(f"**BGM Style Inspiration:** {a1.bgm_style_reference}")

        # Editable SEO Metadata Card
        with st.expander("📝 High-CTR Titles, SEO Description & 20+ Search Tags (Editable)", expanded=True):
            t_options = list(a1.title_options)
            default_idx = t_options.index(a1.selected_title) if a1.selected_title in t_options else 0
            picked_title = st.radio("Choose Winning CTR Title:", options=t_options, index=default_idx, key="a1_title_pick")
            edited_title = st.text_input("Fine-Tune Selected Title:", value=picked_title, key="a1_title_edit")
            edited_desc = st.text_area("SEO Description (with Auto-Timestamps):", value=a1.seo_description, height=170, key="a1_desc_edit")
            edited_tags_str = st.text_area("Targeted Search Tags (comma-separated, 20+):", value=", ".join(a1.tags), height=90, key="a1_tags_edit")

            th_c1, th_c2 = st.columns(2)
            with th_c1:
                edited_thumb_hl = st.text_input("Thumbnail Bold Headline (2–4 words):", value=a1.thumbnail_hook_headline, key="a1_th_hl")
            with th_c2:
                edited_thumb_badge = st.text_input("Thumbnail Badge Label:", value=a1.thumbnail_badge_label, key="a1_th_badge")
            edited_thumb_concept = st.text_input(
                "Thumbnail Glowing Concept Graphics (Opposite @jwalashiva):",
                value=a1.thumbnail_graphic_concept,
                key="a1_th_concept",
            )

        # Editable High-Retention Storyboard & Hook Beats
        with st.expander("🎬 High-Retention Storyboard Manifest (0:00-0:45 Hook • Retention Loops • Climax & CTA)", expanded=True):
            edited_hook = st.text_area("⚡ 0:00–0:45 Visual Hook Script:", value=a1.hook_script_0_45s, height=95, key="a1_hook_edit")
            edited_climax = st.text_area("💡 Climax 'Aha!' & Misconception Debunker:", value=a1.climax_misconception_aha, height=90, key="a1_climax_edit")
            edited_cta = st.text_area("📣 Outro Subscribe & Comment CTA:", value=a1.outro_cta_script, height=85, key="a1_cta_edit")

            st.markdown("**Storyboard Beats (8-Second Visual Reset Rule Mapped):**")
            updated_beats = []
            for b in a1.storyboard_beats:
                with st.container(border=True):
                    bc1, bc2 = st.columns([2.2, 1.0])
                    with bc1:
                        bt = st.text_input(
                            f"Beat {b.beat_id} [{b.phase.replace('_', ' ')}] — {format_timestamp(b.start_sec)}:",
                            value=b.beat_title,
                            key=f"beat_title_{b.beat_id}",
                        )
                    with bc2:
                        bd = st.number_input(
                            "Duration (sec):",
                            min_value=10.0,
                            max_value=120.0,
                            value=float(b.duration_sec),
                            step=5.0,
                            key=f"beat_dur_{b.beat_id}",
                        )
                    bs = st.text_area("Narrative & Retention Loop:", value=b.narrative_summary, height=68, key=f"beat_sum_{b.beat_id}")
                    b_dict = b.model_dump()
                    b_dict["beat_title"] = bt
                    b_dict["duration_sec"] = float(bd)
                    b_dict["narrative_summary"] = bs
                    updated_beats.append(b_dict)

        st.markdown("")
        proceed_s2 = st.button("Proceed to Scene Scripting ➡️", type="primary", use_container_width=True)
        if proceed_s2:
            # Commit all user edits back to Agent1Output & SQLite
            edited_a1_dict = a1.model_dump()
            edited_a1_dict["selected_title"] = edited_title.strip() or a1.selected_title
            edited_a1_dict["seo_description"] = edited_desc.strip() or a1.seo_description
            edited_a1_dict["tags"] = [t.strip() for t in edited_tags_str.split(",") if t.strip()]
            edited_a1_dict["hook_script_0_45s"] = edited_hook.strip() or a1.hook_script_0_45s
            edited_a1_dict["climax_misconception_aha"] = edited_climax.strip() or a1.climax_misconception_aha
            edited_a1_dict["outro_cta_script"] = edited_cta.strip() or a1.outro_cta_script
            edited_a1_dict["thumbnail_hook_headline"] = edited_thumb_hl.strip() or a1.thumbnail_hook_headline
            edited_a1_dict["thumbnail_badge_label"] = edited_thumb_badge.strip() or a1.thumbnail_badge_label
            edited_a1_dict["thumbnail_graphic_concept"] = edited_thumb_concept.strip() or a1.thumbnail_graphic_concept
            edited_a1_dict["storyboard_beats"] = updated_beats

            committed_a1 = Agent1Output.model_validate(edited_a1_dict)
            st.session_state["agent1_output"] = committed_a1.model_dump()

            with st.spinner("Agent 2 breaking storyboard into granular 8–12s scenes with Veo/Omni visual prompts & vocal cues..."):
                a2_obj = run_agent2_scene_scripting(committed_a1, config=cfg)
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
            st.rerun()


# ==============================================================================
# STEP 2 — AGENT 2: MULTI-MODEL VISUAL & VOCAL SCRIPTING AGENT
# ==============================================================================
elif step == 2:
    st.subheader("Step 2 • Agent 2: Multi-Model Visual & Vocal Scene Manifest")
    a1_data = st.session_state.get("agent1_output")
    a2_data = st.session_state.get("agent2_output")

    if not a1_data or not a2_data:
        st.info("Complete Step 1 first to generate your storyboard and scenes.")
        if st.button("⬅️ Back to Step 1", use_container_width=True):
            st.session_state["omni_step"] = 1
            st.rerun()
    else:
        a2 = Agent2Output.model_validate(a2_data)
        pid = st.session_state["omni_project_id"]
        custom_dir = cfg.projects_dir / f"{pid}_{sanitize_slug(a2.topic)}" / "custom_assets"
        custom_dir.mkdir(parents=True, exist_ok=True)

        # Compact responsive metrics bar
        mg_count = sum(1 for s in a2.scenes if s.asset_mode == "motion_graphics")
        avg_cut = round(a2.total_estimated_duration_sec / max(1, len(a2.scenes)), 1)
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Total Scenes", len(a2.scenes))
        m2.metric("Avg Cut Length", f"{avg_cut}s")
        m3.metric("Est. Runtime", format_timestamp(a2.total_estimated_duration_sec))
        m4.metric("Motion Graphics", mg_count)

        # Mobile-friendly pagination so 30-50 scene cards remain super responsive
        per_page = 8
        total_pages = max(1, (len(a2.scenes) + per_page - 1) // per_page)
        pg_c1, pg_c2 = st.columns([1.4, 1.0])
        with pg_c1:
            current_page = st.number_input(
                f"Scene Page (showing {per_page} scenes/page of {len(a2.scenes)} total):",
                min_value=1,
                max_value=total_pages,
                value=min(int(st.session_state.get("scene_page", 1)), total_pages),
                step=1,
                key="scene_page_selector",
            )
            st.session_state["scene_page"] = int(current_page)
        with pg_c2:
            if st.button("🔄 Regenerate Scenes from Step 1", use_container_width=True):
                with st.spinner("Re-scripting granular scenes with Agent 2..."):
                    fresh_a2 = run_agent2_scene_scripting(Agent1Output.model_validate(a1_data), config=cfg)
                    st.session_state["agent2_output"] = fresh_a2.model_dump()
                    db.update_project_stage(pid, agent2_data=fresh_a2.model_dump())
                st.rerun()

        start_idx = (int(current_page) - 1) * per_page
        end_idx = min(len(a2.scenes), start_idx + per_page)
        scenes_dicts = [s.model_dump() for s in a2.scenes]

        for idx in range(start_idx, end_idx):
            sc = scenes_dicts[idx]
            s_num = sc["scene_index"]
            mode_icon = "📊" if sc["asset_mode"] == "motion_graphics" else "🎞️" if sc["asset_mode"] == "custom_upload" else "🎥"
            exp_title = (
                f"{mode_icon} Scene {s_num:02d} ({format_timestamp(sc['start_sec'])} • {sc['duration_sec']}s) "
                f"— {sc['chapter_label'][:38]}"
            )
            with st.expander(exp_title, expanded=(idx == start_idx)):
                sc_c1, sc_c2, sc_c3 = st.columns([1.1, 1.1, 0.8])
                with sc_c1:
                    modes = ["ai_video", "motion_graphics", "custom_upload"]
                    new_mode = st.selectbox(
                        "Visual Source Mode:",
                        options=modes,
                        index=modes.index(sc["asset_mode"]) if sc["asset_mode"] in modes else 0,
                        key=f"sc_mode_{s_num}",
                    )
                with sc_c2:
                    mg_opts = ["none", "manim_formula", "data_chart", "comparison_chart", "timeline_chart"]
                    cur_mg = sc.get("motion_graphic_type") or "none"
                    new_mg = st.selectbox(
                        "Procedural Graphic Type:",
                        options=mg_opts,
                        index=mg_opts.index(cur_mg) if cur_mg in mg_opts else 0,
                        key=f"sc_mg_{s_num}",
                    )
                with sc_c3:
                    new_dur = st.number_input(
                        "Cut Sec:",
                        min_value=6.0,
                        max_value=14.0,
                        value=float(sc["duration_sec"]),
                        step=0.5,
                        key=f"sc_dur_{s_num}",
                    )

                new_vis_prompt = st.text_area(
                    "🎥 Veo / Gemini Omni / Flow Visual Prompt:",
                    value=sc["visual_prompt_veo_omni"],
                    height=82,
                    key=f"sc_vprompt_{s_num}",
                )
                new_vo = st.text_area(
                    "🎙️ Voiceover Script:",
                    value=sc["voiceover_text"],
                    height=74,
                    key=f"sc_vo_{s_num}",
                )
                new_ssml = st.text_input(
                    "🎭 Expressive Vocal Cues & <break/> Pauses:",
                    value=sc.get("ssml_voice_cues", ""),
                    key=f"sc_ssml_{s_num}",
                )
                new_callout = st.text_input(
                    "✨ On-Screen Visual Callout:",
                    value=sc.get("on_screen_callout", ""),
                    key=f"sc_callout_{s_num}",
                )

                # Optional user custom footage/image fallback per scene
                uploaded_asset = st.file_uploader(
                    "📁 Optional: Import Your Own Scene Footage / Image (.mp4, .png, .jpg)",
                    type=["mp4", "mov", "png", "jpg", "jpeg"],
                    key=f"sc_upload_{s_num}",
                )
                if uploaded_asset is not None:
                    dest = custom_dir / f"scene_{s_num:03d}_{uploaded_asset.name}"
                    dest.write_bytes(uploaded_asset.getvalue())
                    sc["custom_asset_path"] = str(dest)
                    new_mode = "custom_upload"
                    st.caption(f"✅ Custom asset attached: `{dest.name}`")
                elif sc.get("custom_asset_path"):
                    st.caption(f"📎 Active custom asset: `{Path(sc['custom_asset_path']).name}`")

                sc["asset_mode"] = new_mode
                sc["motion_graphic_type"] = new_mg
                sc["duration_sec"] = float(new_dur)
                sc["visual_prompt_veo_omni"] = new_vis_prompt
                sc["voiceover_text"] = new_vo
                sc["ssml_voice_cues"] = new_ssml
                sc["on_screen_callout"] = new_callout

        # Persist edits seamlessly in session_state on every rerun
        a2_updated_dict = a2.model_dump()
        a2_updated_dict["scenes"] = scenes_dicts
        a2_updated_dict["total_estimated_duration_sec"] = round(sum(s["duration_sec"] for s in scenes_dicts), 1)
        st.session_state["agent2_output"] = a2_updated_dict

        st.markdown("")
        act_c1, act_c2 = st.columns([1, 2])
        with act_c1:
            if st.button("⬅️ Back to Step 1", use_container_width=True):
                db.update_project_stage(pid, current_step=1, agent2_data=a2_updated_dict)
                st.session_state["omni_step"] = 1
                st.rerun()
        with act_c2:
            if st.button("Proceed to Rendering Studio ➡️", type="primary", use_container_width=True):
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
# STEP 3 — AGENT 3: MEDIA GENERATOR & COMPOSER STUDIO
# ==============================================================================
elif step == 3:
    st.subheader("Step 3 • Agent 3: Asynchronous Media Generator & Composer Studio")
    a1_data = st.session_state.get("agent1_output")
    a2_data = st.session_state.get("agent2_output")
    pid = st.session_state.get("omni_project_id")

    if not a1_data or not a2_data or not pid:
        st.info("Complete Step 1 & Step 2 first to unlock the Media Rendering Studio.")
    else:
        a1 = Agent1Output.model_validate(a1_data)
        a2 = Agent2Output.model_validate(a2_data)
        render_task_key = f"render_{pid}"

        # Sync completed background render output from SQLite automatically
        fresh_proj = db.get_project(pid)
        if fresh_proj and fresh_proj.get("agent3_data"):
            st.session_state["agent3_output"] = fresh_proj["agent3_data"]

        with st.expander("⚙️ Render Quality, Avatar Opt-In & Audio Ducking (-24dB) Settings", expanded=True):
            rc1, rc2 = st.columns([1.4, 1.0])
            with rc1:
                quality_label = st.selectbox(
                    "🎞️ Visual Render Mode:",
                    options=[
                        "Full Gemini Omni 1.2 Flash + Veo 3.1 AI Video (Recommended Best Quality)",
                        "AI Cinema Keyframes + Smooth 24fps Motion (Fast Gemini 3 Pro)",
                        "Fast Studio Preview (Local Plates — Offline Test Only)",
                    ],
                    index=0,
                    key="render_quality_sel",
                )
                quality_map = {
                    "Full Gemini Omni 1.2 Flash + Veo 3.1 AI Video (Recommended Best Quality)": "full_omni_video",
                    "AI Cinema Keyframes + Smooth 24fps Motion (Fast Gemini 3 Pro)": "ai_keyframes_kenburns",
                    "Fast Studio Preview (Local Plates — Offline Test Only)": "fast_studio_preview",
                }
                render_quality = quality_map[quality_label]
            with rc2:
                force_ai_cinema = st.checkbox(
                    "🎬 100% AI Cinema (No Flat Python Charts)",
                    value=True,
                    help="Overrides any Python chart scenes to render with real Gemini Omni 1.2 Flash / Veo 3.1 / Gemini 3 Pro Cinema.",
                    key="opt_force_ai_cinema",
                )
                fast_tts = st.checkbox(
                    "⚡ Fast Local Edge-TTS (skip Gemini 3.8 TTS)",
                    value=False,
                    key="render_fast_tts",
                )

            st.markdown("**🧍 Creator Avatar / Likeness Opt-In Controls:**")
            av_c1, av_c2 = st.columns(2)
            with av_c1:
                include_avatar_thumb = st.checkbox(
                    "Include my avatar/photo on Thumbnail",
                    value=False,
                    help="OFF = Full-bleed epic faceless topic cinema thumbnail (recommended for clean focus). ON = Includes your likeness on the thumbnail.",
                    key="opt_include_avatar_thumb",
                )
            with av_c2:
                include_avatar_video = st.checkbox(
                    "Include my avatar/photo in Video (Hook & Outro Host PIP)",
                    value=False,
                    help="OFF = 100% pure topic visuals & motion graphics. ON = Adds a clean glowing circular host presenter badge on Opening Hook & Outro CTA.",
                    key="opt_include_avatar_video",
                )

            creator_side = "left"
            avatar_thumb_mode = "real_photo"
            if include_avatar_thumb:
                opt_c1, opt_c2 = st.columns(2)
                with opt_c1:
                    av_style_lbl = st.selectbox(
                        "Avatar Thumbnail Style:",
                        options=[
                            "Exact Real Studio Photo Cutout (100% Real Face — Zero AI Distortion)",
                            "AI Studio Portrait (Gemini 3 Pro — Nehru Jacket + Pointing)",
                        ],
                        index=0,
                        key="opt_avatar_thumb_style",
                    )
                    avatar_thumb_mode = "real_photo" if av_style_lbl.startswith("Exact Real") else "ai_pro"
                with opt_c2:
                    creator_side = st.selectbox(
                        "Avatar Side on Thumbnail:",
                        options=["left", "right"],
                        index=0,
                        key="thumb_creator_side",
                    )

            # Optional likeness manager drawer
            if include_avatar_thumb or include_avatar_video:
                with st.expander(f"🪪 Manage Studio Likeness Photos ({cfg.creator_handle})", expanded=False):
                    studio_refs = [p for p in (cfg.likeness_dir / "image_13.png", cfg.likeness_dir / "image_14.png") if p.exists()]
                    if studio_refs:
                        lcols = st.columns(len(studio_refs))
                        for lcol, lp in zip(lcols, studio_refs):
                            with lcol:
                                st.image(str(lp), caption=lp.name, use_container_width=True)
                    up_ref = st.file_uploader(
                        "Upload Your Clean Studio Photo (replaces `image_13.png`):",
                        type=["png", "jpg", "jpeg"],
                        key="replace_likeness_img",
                    )
                    if up_ref is not None:
                        (cfg.likeness_dir / "image_13.png").write_bytes(up_ref.getvalue())
                        st.success("Updated `assets/likeness/image_13.png` ✅")

        is_rendering = worker.is_running(render_task_key)
        btn_r1, btn_r2 = st.columns([2.0, 1.0])
        with btn_r1:
            start_render = st.button(
                "🚀 Launch Async Media Generation & 1080p + Shorts Assembly",
                type="primary",
                use_container_width=True,
                disabled=is_rendering,
            )
        with btn_r2:
            regen_thumb = st.button(
                "🖼️ Regenerate Thumbnail Only",
                use_container_width=True,
                disabled=is_rendering,
            )

        if start_render:
            st.session_state["agent3_output"] = None
            launched = worker.submit_task(
                task_key=render_task_key,
                project_id=pid,
                job_type="master_render",
                label=f"Render 1080p + Shorts: {a1.topic[:34]}",
                fn=run_agent3_media_pipeline,
                kwargs={
                    "project_id": pid,
                    "agent1": a1,
                    "agent2": a2,
                    "render_quality": render_quality,
                    "force_ai_cinema": force_ai_cinema,
                    "include_avatar_in_thumbnail": include_avatar_thumb,
                    "avatar_thumbnail_mode": avatar_thumb_mode,
                    "include_avatar_in_video": include_avatar_video,
                    "creator_side": creator_side,
                    "prefer_fast_local_tts": fast_tts,
                    "use_ai_thumbnail": (render_quality != "fast_studio_preview"),
                    "config": cfg,
                    "db": db,
                },
            )
            if launched:
                st.session_state["render_task_key"] = render_task_key
                st.toast("Background media worker started! Tracking real-time progress in SQLite.", icon="🎬")
                st.rerun()

        if regen_thumb:
            a3_existing = st.session_state.get("agent3_output")
            thumb_dest = (
                Path(a3_existing["thumbnail_16x9_path"])
                if a3_existing and a3_existing.get("thumbnail_16x9_path")
                else cfg.projects_dir / f"{pid}_{sanitize_slug(a1.topic)}" / "renders" / "thumbnail_16x9.png"
            )
            with st.spinner("Generating High-CTR Thumbnail..."):
                t_path, t_eng = generate_high_ctr_thumbnail(
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
            st.success(f"Thumbnail regenerated via `{t_eng}` ✅")
            st.image(str(t_path), caption="Updated High-CTR 16:9 Thumbnail", use_container_width=True)

        # Real-Time SQLite Worker Progress Monitor
        stage_jobs = db.get_project_jobs(pid, job_type="media_stage")
        if stage_jobs or is_rendering:
            st.markdown("### 📡 Live Asynchronous Render Queue (SQLite-Backed)")
            overall_pct = int(sum(j["progress_pct"] for j in stage_jobs) / max(1, len(stage_jobs))) if stage_jobs else 5
            st.progress(overall_pct / 100.0, text=f"Overall Render Progress: {overall_pct}%")

            for j in stage_jobs:
                badge = "✅ Completed" if j["status"] == "completed" else "❌ Failed" if j["status"] == "failed" else f"⏳ {j['progress_pct']}%"
                st.markdown(
                    f"""
                    <div class="omni-status-row">
                        <span><strong>{j['label']}</strong></span>
                        <span style="color:#38bdf8;">{j['message'] or badge}</span>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

            err_msg = worker.get_task_error(render_task_key)
            if err_msg:
                st.error(f"Background render error: {err_msg}")

            if is_rendering:
                st.caption("Background worker is actively rendering — auto-refreshing status every 2 seconds...")
                time.sleep(2.0)
                st.rerun()

        # Preview Rendered Deliverables (Inline 1080p Player + Thumbnail + Collapsible Shorts Drawer)
        a3_data = st.session_state.get("agent3_output")
        if a3_data and not is_rendering:
            a3 = Agent3Output.model_validate(a3_data)
            st.success(
                f"✅ **Render Complete!** 16:9 Long-Form (`{format_timestamp(a3.final_duration_sec)}`) • "
                f"9:16 Shorts (`{format_timestamp(a3.shorts_duration_sec)}`) • {a3.scene_count_rendered} scenes stitched."
            )

            p_c1, p_c2 = st.columns([1.15, 1.0])
            with p_c1:
                st.markdown("#### 📺 Final 1080p Long-Form Video (16:9 + Burned-In Active Subtitles)")
                if Path(a3.video_16x9_path).exists():
                    st.video(a3.video_16x9_path)
                    master_wav_p = Path(a3.video_16x9_path).parent / "master_audio_16x9.wav"
                    if master_wav_p.exists():
                        st.caption("🔊 Master Voiceover + (-24dB) Ducked BGM Audio Preview:")
                        st.audio(str(master_wav_p))
                    with open(a3.video_16x9_path, "rb") as vfp:
                        st.download_button(
                            "⬇️ Download 16:9 1080p MP4",
                            data=vfp.read(),
                            file_name=Path(a3.video_16x9_path).name,
                            mime="video/mp4",
                            use_container_width=True,
                        )
            with p_c2:
                st.markdown("#### 🖼️ High-CTR @jwalashiva Likeness Thumbnail (16:9)")
                if Path(a3.thumbnail_16x9_path).exists():
                    st.image(a3.thumbnail_16x9_path, use_container_width=True)
                    with open(a3.thumbnail_16x9_path, "rb") as tfp:
                        st.download_button(
                            "⬇️ Download High-CTR Thumbnail (.png)",
                            data=tfp.read(),
                            file_name="thumbnail_16x9.png",
                            mime="image/png",
                            use_container_width=True,
                        )

            with st.expander("📱 9:16 Vertical Shorts Cutdown, Exact Chapters & Subtitle Files", expanded=False):
                sh_c1, sh_c2 = st.columns([1.0, 1.2])
                with sh_c1:
                    if Path(a3.video_9x16_shorts_path).exists():
                        st.video(a3.video_9x16_shorts_path)
                        with open(a3.video_9x16_shorts_path, "rb") as sfp:
                            st.download_button(
                                "⬇️ Download 9:16 Shorts MP4",
                                data=sfp.read(),
                                file_name=Path(a3.video_9x16_shorts_path).name,
                                mime="video/mp4",
                                use_container_width=True,
                            )
                with sh_c2:
                    st.markdown("**Exact Auto-Calculated Chapters (Anchored to Measured Audio):**")
                    st.code(a3.exact_chapters_text, language="text")
                    st.caption(f"ASS Subtitles (16:9): `{a3.ass_subtitles_16x9_path}`")
                    st.caption(f"BGM Stem (-24dB ducked): `{a3.bgm_stem_path}`")

            st.markdown("")
            if st.button("👉 PROCEED TO AGENT 4 (OAUTH & PUBLISH)", type="primary", use_container_width=True):
                st.session_state["omni_step"] = 4
                db.update_project_stage(pid, current_step=4)
                st.rerun()


# ==============================================================================
# STEP 4 — AGENT 4: DIRECT YOUTUBE PUBLISHER AGENT
# ==============================================================================
elif step == 4:
    st.subheader("Step 4 • Agent 4: OAuth 2.0 & Direct YouTube Resumable Publisher")
    a1_data = st.session_state.get("agent1_output")
    a3_data = st.session_state.get("agent3_output")
    pid = st.session_state.get("omni_project_id")

    if not a1_data or not a3_data or not pid:
        st.info("Complete Step 3 (Media Rendering) first to publish your video to YouTube.")
    else:
        a1 = Agent1Output.model_validate(a1_data)
        a3 = Agent3Output.model_validate(a3_data)
        publish_task_key = f"publish_{pid}"

        # Sync completed publish status from SQLite
        fresh_proj = db.get_project(pid)
        if fresh_proj and fresh_proj.get("agent4_data"):
            st.session_state["agent4_output"] = fresh_proj["agent4_data"]

        # 1. OAuth 2.0 Connection Status Card (Stored in SQLite)
        creds, tok_rec = get_valid_youtube_credentials(cfg, db)
        with st.container(border=True):
            if creds and tok_rec:
                st.success(
                    f"🔐 **YouTube OAuth 2.0 Connected** — Channel: **{tok_rec.get('channel_title') or 'Authorized Channel'}** "
                    f"(`{tok_rec.get('channel_id') or 'SQLite Token Active'}`)"
                )
            else:
                st.warning("🔒 **YouTube OAuth 2.0 Not Connected Yet** — Authenticate below to enable 4MB chunked direct upload.")

            with st.expander("🔑 Manage YouTube OAuth 2.0 Connection (`youtube.upload`)", expanded=(creds is None)):
                auth_url, auth_msg = build_youtube_oauth_url(cfg.youtube_client_secrets, redirect_uri=cfg.youtube_redirect_uri)
                if auth_url:
                    st.markdown(f"[🌐 Click Here to Authorize YouTube Channel via Google OAuth 2.0 ↗]({auth_url})")
                    code_in = st.text_input("Or paste OAuth Authorization Code here:", key="oauth_manual_code")
                    if st.button("Verify & Save Refresh Token to SQLite", use_container_width=True):
                        ok_ex, msg_ex = exchange_oauth_code_and_store(
                            code_in, cfg.youtube_client_secrets, redirect_uri=cfg.youtube_redirect_uri, db=db
                        )
                        if ok_ex:
                            st.success(msg_ex)
                            st.rerun()
                        else:
                            st.error(msg_ex)
                else:
                    st.caption(f"Setup note: {auth_msg} Upload your OAuth token JSON below or place `client_secret.json` in `config/credentials/`.")

                up_tok = st.file_uploader("Import Authorized `youtube_oauth_token.json`:", type=["json"], key="upload_yt_tok")
                if up_tok is not None:
                    try:
                        parsed_tok = json.loads(up_tok.getvalue().decode("utf-8"))
                        db.save_oauth_token("youtube", parsed_tok, channel_title="Imported YouTube OAuth Token")
                        st.success("Saved OAuth token into SQLite ✅")
                        st.rerun()
                    except Exception as tok_err:
                        st.error(f"Invalid token JSON: {tok_err}")

                if creds and st.button("Disconnect / Clear Stored YouTube Token"):
                    db.delete_oauth_token("youtube")
                    st.rerun()

        # 2. Publishing & Scheduling Form
        with st.container(border=True):
            pub_format = st.radio(
                "📦 Deliverable to Upload:",
                options=["16:9 Long-Form (1080p)", "9:16 Vertical Shorts"],
                horizontal=True,
                key="pub_format_radio",
            )
            default_title = a1.selected_title if pub_format.startswith("16:9") else f"{a1.selected_title[:85]} #Shorts"
            pub_title = st.text_input("YouTube Video Title:", value=default_title, max_chars=100, key="pub_title_in")

            # Merge exact audio-anchored chapters into description
            base_desc = a1.seo_description
            if a3.exact_chapters_text and "00:00" not in base_desc:
                base_desc = f"{base_desc}\n\n⏱️ CHAPTERS:\n{a3.exact_chapters_text}"
            pub_desc = st.text_area("YouTube Description (with Exact Chapters):", value=base_desc, height=160, key="pub_desc_in")

            pc1, pc2, pc3 = st.columns(3)
            with pc1:
                privacy_opt = st.selectbox("🔒 Privacy Status:", options=["private", "unlisted", "public"], index=0, key="pub_privacy")
            with pc2:
                use_schedule = st.checkbox("📅 Schedule Future Publish", value=False, key="pub_use_sched")
                sched_date = st.date_input("Publish Date (IST):", value=datetime.date.today() + datetime.timedelta(days=1), disabled=not use_schedule)
                sched_time = st.time_input("Publish Time (IST):", value=datetime.time(18, 30), disabled=not use_schedule)
            with pc3:
                playlists = list_user_youtube_playlists(cfg, db) if creds else []
                pl_map = {"(No Playlist)": "NONE"}
                for pl in playlists:
                    pl_map[pl["title"]] = pl["id"]
                sel_pl_label = st.selectbox("📂 Playlist Routing:", options=list(pl_map.keys()), key="pub_playlist")
                sel_pl_id = pl_map[sel_pl_label]

        is_uploading = worker.is_running(publish_task_key)
        submit_pub = st.button(
            "🚀 Publish to YouTube (4MB Chunked Resumable Upload)",
            type="primary",
            use_container_width=True,
            disabled=(is_uploading or creds is None),
        )

        if submit_pub:
            st.session_state["agent4_output"] = None
            st.session_state["publish_balloons_shown"] = False

            sched_iso: Optional[str] = None
            if use_schedule:
                # Convert IST (+05:30) to RFC3339 UTC ISO-8601 required by YouTube Data API
                ist_tz = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
                dt_ist = datetime.datetime.combine(sched_date, sched_time, tzinfo=ist_tz)
                sched_iso = dt_ist.astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

            target_video = Path(a3.video_16x9_path if pub_format.startswith("16:9") else a3.video_9x16_shorts_path)
            target_thumb = Path(a3.thumbnail_16x9_path) if pub_format.startswith("16:9") else None

            worker.submit_task(
                task_key=publish_task_key,
                project_id=pid,
                job_type="youtube_upload",
                label=f"YouTube Upload: {pub_title[:34]}",
                fn=run_agent4_youtube_publish,
                kwargs={
                    "project_id": pid,
                    "video_path": target_video,
                    "thumbnail_path": target_thumb,
                    "title": pub_title,
                    "description": pub_desc,
                    "exact_chapters_text": a3.exact_chapters_text,
                    "tags": a1.tags,
                    "privacy_status": privacy_opt,
                    "scheduled_publish_at_iso": sched_iso,
                    "playlist_id": None if sel_pl_id == "NONE" else sel_pl_id,
                    "config": cfg,
                    "db": db,
                },
            )
            st.session_state["publish_task_key"] = publish_task_key
            st.rerun()

        # Live Upload Progress Tracker
        up_jobs = db.get_project_jobs(pid, job_type="youtube_upload")
        if up_jobs or is_uploading:
            latest_up = up_jobs[-1] if up_jobs else {"progress_pct": 5, "message": "Initializing upload..."}
            st.progress(latest_up["progress_pct"] / 100.0, text=f"Upload Status: {latest_up['message']}")
            up_err = worker.get_task_error(publish_task_key)
            if up_err:
                st.error(f"YouTube upload error: {up_err}")
            if is_uploading:
                time.sleep(1.5)
                st.rerun()

        # Final Published Confirmation + Studio URL + Balloons + Restart Button
        a4_data = st.session_state.get("agent4_output")
        if a4_data and not is_uploading:
            a4 = Agent4Output.model_validate(a4_data)
            if not st.session_state.get("publish_balloons_shown"):
                st.balloons()
                st.session_state["publish_balloons_shown"] = True
            st.success(f"🎉 **Published to YouTube!** Status: `{a4.status}` • Video ID: `{a4.video_id}`")
            st.markdown(f"- **🎬 YouTube Studio Editor:** [{a4.studio_url}]({a4.studio_url})")
            st.markdown(f"- **📺 YouTube Watch Link:** [{a4.watch_url}]({a4.watch_url})")
            st.caption(a4.note)

        # Recent SQLite Publish Log
        pub_logs = db.get_publish_records(project_id=pid, limit=5)
        if pub_logs:
            with st.expander("📋 Project Upload History (SQLite)", expanded=False):
                st.dataframe(pub_logs, use_container_width=True, hide_index=True)

        st.markdown("---")
        if st.button("🔄 Restart Pipeline Workspace", use_container_width=True):
            _reset_workspace()
            st.rerun()
