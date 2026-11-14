"""
Streamlit UI Panel for OMNI CREATOR — Ultra-Realistic 4K 3D Hinglish Science Video & SEO Engine (Classes 9-12)
==============================================================================================================
Provides an interactive GUI over all 5 modular pipeline stages:
- Module A: `seo_keyword_engine.py` (Google Keyword Planner + YouTube India Autocomplete + Gemini Search Grounding)
- Module B: `script_and_pedagogy_agent.py` (5-Beat High-Retention Hinglish Blueprint + Indian Analogies + Exam Sniper)
- Module C: `visual_3d_generator.py` (`gemini-3-pro-image` + `gemini-nano-banana-2.1` + `gemini-omni-1.2-flash`)
- Module D: `thumbnail_hook_studio.py` (3 A/B High-CTR 4K Thumbnails: Visual Paradox, Exam Urgency, Curiosity Zoom)
- Module E: `compositor_and_packager.py` (`gemini-3.8-flash-tts` + `gemini-3.5-transcribe` + `-22dB` `lyria-3.5` BGM + HUD)
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import streamlit as st

from config.models import (
    FRONTIER_BRAIN_MODEL,
    IMAGE_4K_PRO_MODEL,
    IMAGE_CONTINUITY_MODEL,
    MUSIC_LYRIA_MODEL,
    ORCHESTRATOR_MODEL,
    TRANSCRIBE_MODEL,
    TTS_EXPRESSIVE_MODEL,
    VIDEO_OMNI_MODEL,
    OmniModelConfig,
    estimate_pipeline_credits,
)
from omni_creator.compositor_and_packager import run_compositor_and_packager
from omni_creator.script_and_pedagogy_agent import generate_chapter_video_blueprint
from omni_creator.seo_keyword_engine import run_seo_keyword_engine
from omni_creator.syllabus_catalog import OMNI_SCIENCE_SYLLABUS_2027
from schemas.blueprint import OmniCreatorInput


def render_omni_creator_science_studio() -> None:
    """Renders the Omni Creator 4K 3D Hinglish Science Video & SEO Studio panel in Streamlit."""
    st.markdown("---")
    st.markdown(
        """
        <div style="background: linear-gradient(135deg, rgba(8,15,32,0.96), rgba(18,32,64,0.94));
                    border: 1px solid #00e5ff; border-radius: 14px; padding: 18px 22px; margin-bottom: 16px;">
            <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:8px;">
                <div>
                    <span style="background:#e11d48; color:#fff; font-weight:800; padding:4px 10px; border-radius:6px; font-size:0.78rem;">
                        PAID TIER 1 / ULTRA STACK • STRICTLY NON-KIDDISH 4K 3D
                    </span>
                    <h2 style="margin:8px 0 4px 0; color:#f8fafc;">
                        🌌 OMNI CREATOR — Ultra-Realistic 3D Hinglish Science Video &amp; SEO Engine (Classes 9–12)
                    </h2>
                    <p style="margin:0; color:#94a3b8; font-size:0.93rem;">
                        Unreal Engine 5 / Octane 3D Scientific Cinema • <code>gemini-4-carbon</code> Search-Grounded SEO &amp; 5-Beat Hinglish Script •
                        <code>gemini-omni-1.2-flash</code> 3D Simulation • <code>gemini-3-pro-image</code> 4K A/B Thumbnails •
                        <code>gemini-3.8-flash-tts</code> (@jwalashiv Mentor Voice) + <code>-22dB lyria-3.5</code> Dark-Synth Score
                    </p>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    col_c1, col_c2, col_c3, col_c4, col_c5 = st.columns([1.0, 1.0, 1.8, 1.8, 1.1])
    with col_c1:
        sel_class = st.selectbox(
            "🎓 Class Level:",
            options=["Class 9", "Class 10", "Class 11", "Class 12"],
            index=1,
            key="omni_3d_class_level",
        )
    with col_c2:
        sel_subject = st.selectbox(
            "🔬 Science Subject:",
            options=["Physics", "Chemistry", "Biology"],
            index=0,
            key="omni_3d_subject",
        )

    chapters_dict = OMNI_SCIENCE_SYLLABUS_2027.get(sel_class, {}).get(sel_subject, {})
    chapter_options = list(chapters_dict.keys()) or ["Light — Reflection and Refraction"]

    with col_c3:
        sel_chapter = st.selectbox(
            "📘 NCERT 2026–27 Rationalized Chapter:",
            options=chapter_options,
            index=0,
            key="omni_3d_chapter_name",
        )

    section_options = chapters_dict.get(sel_chapter, ["Full Chapter Modular"])
    with col_c4:
        sel_section = st.selectbox(
            "🎯 Chapter Section / Sub-Topic:",
            options=section_options,
            index=0,
            key="omni_3d_chapter_section",
        )
    with col_c5:
        sel_format = st.selectbox(
            "📐 Video Format:",
            options=["16:9_LongForm", "9:16_Shorts"],
            index=0,
            key="omni_3d_video_format",
        )

    spec = OmniCreatorInput(
        class_level=sel_class,      # type: ignore[arg-type]
        subject=sel_subject,        # type: ignore[arg-type]
        chapter_name=sel_chapter,
        chapter_section=sel_section,
        video_format=sel_format,    # type: ignore[arg-type]
    )

    btn_a, btn_b = st.columns(2)
    with btn_a:
        run_dry = st.button(
            "🧪 Run --dry-run (SEO Keywords + 5-Beat Hinglish Script + 3 A/B 4K Thumbnails + Credit Estimate)",
            use_container_width=True,
            key="omni_btn_dry_run",
        )
    with btn_b:
        run_full = st.button(
            "🎬 Render Full 4K 3D Hinglish Science Video + HUD Overlays + YouTube Publish Bundle",
            type="primary",
            use_container_width=True,
            key="omni_btn_full_render",
        )

    if run_dry or run_full:
        is_dry = bool(run_dry and not run_full)
        with st.spinner(
            "Running Omni Creator 5-Module Pipeline (SEO Keyword Planner -> 5-Beat Hinglish Blueprint -> "
            "3 A/B 4K Thumbnails -> 3D Keyframes & Compositor)..."
        ):
            cfg = OmniModelConfig()
            kw_strategy = run_seo_keyword_engine(spec, config=cfg)
            blueprint = generate_chapter_video_blueprint(spec, keyword_strategy=kw_strategy, config=cfg)
            prod_out = run_compositor_and_packager(blueprint, config=cfg, dry_run=is_dry)
            st.session_state["omni_active_blueprint"] = blueprint
            st.session_state["omni_active_output"] = prod_out

    blueprint = st.session_state.get("omni_active_blueprint")
    prod_out = st.session_state.get("omni_active_output")

    if blueprint and prod_out:
        st.success(
            f"✅ **Omni Creator Bundle Ready:** `{prod_out.bundle_dir}` | "
            f"**Primary Focus Keyword:** `{blueprint.keyword_strategy.primary_focus_keyword}` | "
            f"**Planned Duration:** `{blueprint.total_planned_duration_sec}s`"
        )

        tab_seo, tab_script, tab_thumbs, tab_video = st.tabs(
            [
                "📊 Module A: Keyword & SEO Strategy",
                "🧠 Module B: 5-Beat Hinglish Blueprint",
                "🖼️ Module D: 3 A/B 4K Thumbnails",
                "🎬 Module C & E: 4K 3D Video & Publish Sheet",
            ]
        )

        with tab_seo:
            kw = blueprint.keyword_strategy
            m1, m2, m3 = st.columns(3)
            m1.metric("Primary Focus Keyword (<=45 chars)", kw.primary_focus_keyword)
            m2.metric("Geo & Language Target", kw.geo_target)
            m3.metric("Tag Block Length", f"{len(kw.tags_500_chars)} / 500 chars")
            st.markdown("**Secondary LSI Keywords (Timestamps & Spoken Script):**")
            st.write(kw.secondary_lsi_keywords)
            st.markdown("**Scored Seed Candidates (India Monthly Volume + Exam Intent + Visual Opportunity):**")
            if kw.top_candidates:
                st.dataframe([c.model_dump() for c in kw.top_candidates], use_container_width=True, hide_index=True)
            st.markdown("**Exact `<= 500` Character YouTube Tag Block:**")
            st.code(kw.tags_500_chars, language="text")

        with tab_script:
            b1 = blueprint.beat_1_pattern_interrupt_hook
            st.markdown("### ⚡ Beat 1 (`0:00–0:03`): 3-Second Pattern-Interrupt Hook")
            st.info(
                f"**Spoken Hinglish Hook (@jwalashiv):** \"{b1.spoken_hinglish_hook}\"\n\n"
                f"**Macro 3D Visual Prompt:** {b1.visual_macro_3d_prompt}\n\n"
                f"**HUD Callout:** `{b1.on_screen_hud_callout}` | **SFX Cue:** `{b1.sfx_cue}`"
            )

            st.markdown("### 🔬 Beat 2: Core Concept in 3D Visual Mode (Indian Analogies)")
            for sc in blueprint.beat_2_simulation_scenes:
                with st.expander(f"Scene {sc.scene_id} ({sc.duration_sec}s) — {sc.scene_title}", expanded=(sc.scene_id == 1)):
                    st.markdown(f"- **Indian Everyday Analogy:** {sc.indian_everyday_analogy}")
                    st.markdown(f"- **Spoken Hinglish Narration:** *\"{sc.spoken_hinglish_narration}\"*")
                    st.markdown(f"- **Start 4K Keyframe Prompt (`{IMAGE_4K_PRO_MODEL}`):** `{sc.start_keyframe_prompt}`")
                    if sc.end_keyframe_prompt:
                        st.markdown(f"- **End 4K Keyframe Prompt (`{IMAGE_CONTINUITY_MODEL}`):** `{sc.end_keyframe_prompt}`")
                    st.markdown(f"- **`{VIDEO_OMNI_MODEL}` Camera Motion Prompt:** `{sc.omni_camera_motion_prompt}`")

            b3 = blueprint.beat_3_hud_formula_vault
            st.markdown(f"### 📐 Beat 3: HUD Formula Vault & Memory Hack — `{b3.formula_title}`")
            st.warning(
                f"**Exact Formula:** `{b3.exact_formula_expression}`\n\n"
                f"**SI Units & Variables:** {b3.si_units_and_variables}\n\n"
                f"**Vector/Scalar & Sign Conventions:** {b3.vector_scalar_sign_conventions}\n\n"
                f"**Sticky Hinglish Mnemonic:** *{b3.sticky_hinglish_mnemonic}*"
            )

            b4 = blueprint.beat_4_exam_sniper_tip
            st.markdown(f"### 🎯 Beat 4: Exam Sniper Tip (`{b4.exam_target_badge}`)")
            st.error(
                f"**#1 Silly Mistake:** {b4.number_one_silly_mistake}\n\n"
                f"**Exact NCERT Step-Marking Keywords:** `{', '.join(b4.exact_ncert_step_marking_keywords)}`\n\n"
                f"**Competency / Assertion-Reason PYQ Angle:** {b4.pyq_competency_assertion_reason_angle}"
            )

            b5 = blueprint.beat_5_gamified_engagement
            st.markdown("### 🎮 Beat 5: Gamified Engagement Trigger (Mid-Roll + 10s PYQ Outro)")
            st.success(
                f"**Mid-Roll Retention Check:** \"{b5.mid_roll_micro_check_hinglish}\"\n\n"
                f"**10s Outro PYQ Puzzle:** \"{b5.outro_10s_tricky_pyq_puzzle}\"\n\n"
                f"**HUD Options:** `{'  |  '.join(b5.options_hud)}`\n\n"
                f"**Pin Solution Note:** {b5.correct_answer_hint_for_pin}"
            )

        with tab_thumbs:
            st.markdown("### 🖼️ A/B High-CTR 4K Thumbnail Suite (`< 4` Words Hook, Non-Kiddish 3D)")
            tcols = st.columns(3)
            for idx, tv in enumerate(blueprint.thumbnail_variants):
                t_path = prod_out.thumbnail_paths.get(tv.variant_id)
                with tcols[idx]:
                    st.markdown(f"**{tv.variant_id.upper()}** — `{tv.archetype}`")
                    st.caption(f"Hook: **\"{tv.hook_text_max_3_words}\"** | Badge: `{tv.sub_badge_text}`")
                    if t_path and Path(t_path).exists():
                        st.image(str(t_path), use_container_width=True)
                        with open(t_path, "rb") as fp:
                            st.download_button(
                                f"⬇️ Download {tv.variant_id}.png (4K)",
                                data=fp.read(),
                                file_name=f"{tv.variant_id}.png",
                                mime="image/png",
                                use_container_width=True,
                                key=f"dl_omni_thumb_{tv.variant_id}",
                            )

        with tab_video:
            vcol1, vcol2 = st.columns([1.3, 1.0])
            with vcol1:
                if prod_out.final_video_path and Path(prod_out.final_video_path).exists():
                    st.markdown("### 🎬 Final Rendered 3D Hinglish Science Video (`final_video_4k.mp4`)")
                    st.video(str(prod_out.final_video_path))
                    with open(prod_out.final_video_path, "rb") as vfp:
                        st.download_button(
                            "⬇️ Download final_video_4k.mp4",
                            data=vfp.read(),
                            file_name="final_video_4k.mp4",
                            mime="video/mp4",
                            use_container_width=True,
                            key="dl_omni_final_mp4",
                        )
                else:
                    st.info(
                        "Dry-Run mode completed without spending video credits. "
                        "Click **🎬 Render Full 4K 3D Hinglish Science Video** above to composite `final_video_4k.mp4`."
                    )
            with vcol2:
                st.markdown("### 💰 Paid Tier 1 API Credit & Cost Report")
                st.json(prod_out.credit_estimate)

            st.markdown("### 📄 Ready-to-Publish YouTube Sheet (`youtube_publish_sheet.md`)")
            if prod_out.publish_sheet_md_path.exists():
                md_text = prod_out.publish_sheet_md_path.read_text(encoding="utf-8")
                st.markdown(md_text)
