"""
Agent 2: Multi-Model Visual & Vocal Scripting Agent (`backend/agent2_scene_scripter.py`)
========================================================================================
Expands Agent 1's edited Storyboard Manifest into granular, scene-by-scene production manifests:
- Enforces the **8-Second Visual Reset Rule** (~8–12s per clip → 30–50 granular scenes for a 5–8 min video).
- Maps visual generation prompts for Vertex Veo 3.1 / Gemini Omni 1.2 Flash / Google Flow strictly
  to the selected niche's visual grammar with zero hallucination.
- Automatically detects analytical, quantitative, comparative, chronological, or formula scenes and
  tags them for zero-hallucination procedural motion graphics (`manim_formula`, `data_chart`,
  `comparison_chart`, `timeline_chart`).
- Generates expressive, spirited Indian vocal cues (Hinglish / Hindi / English) with exact phonetic
  pacing, emotion tags, and `<break time="0.4s"/>` SSML pauses.
"""

from __future__ import annotations

import json
import logging
import math
from typing import Any, Dict, List, Optional

from backend.config import (
    FAST_AGENT_MODEL,
    REASONING_FALLBACK_MODEL,
    SCRIPT_FRONTIER_MODEL,
    OmniStudioConfig,
    call_interaction_with_fallback,
    format_timestamp,
    get_genai_client,
    get_niche_profile,
    resolve_current_model,
)
from backend.schemas import Agent1Output, Agent2Output, SceneClipSpec
from render_engine.motion_graphics import detect_motion_graphic_type

logger = logging.getLogger("omni_studio.agent2")


def _compute_chapters_markdown(scenes: List[SceneClipSpec]) -> str:
    seen_labels: List[str] = []
    lines: List[str] = []
    cursor = 0.0
    for sc in scenes:
        sc.start_sec = round(cursor, 1)
        lbl = (sc.chapter_label or sc.beat_phase.replace("_", " ")).strip()
        if lbl and lbl not in seen_labels:
            seen_labels.append(lbl)
            lines.append(f"{format_timestamp(cursor)} - {lbl}")
        cursor += sc.duration_sec
    return "\n".join(lines)


def _expand_deterministic_scenes(agent1: Agent1Output, desired_scene_count: int) -> Agent2Output:
    """
    Deterministic multi-niche expander guaranteeing 8-12s scene pacing (30-50 scenes for 5-8 min)
    and automatic motion-graphics routing for data/timeline/comparison beats.
    """
    prof = get_niche_profile(agent1.niche)
    total_target_sec = max(60.0, float(agent1.target_duration_minutes) * 60.0)
    num_scenes = max(8, min(55, int(desired_scene_count)))
    avg_dur = round(max(7.5, min(12.0, total_target_sec / float(num_scenes))), 1)

    beats = agent1.storyboard_beats
    total_beat_dur = sum(b.duration_sec for b in beats) or total_target_sec
    is_hinglish = "hinglish" in agent1.language_tone.lower()
    is_hindi = "hindi" in agent1.language_tone.lower() and not is_hinglish

    scenes: List[SceneClipSpec] = []
    scene_idx = 1
    cursor = 0.0

    # Distribute scene quota proportionally across storyboard beats
    beat_quotas: List[int] = []
    assigned = 0
    for idx, b in enumerate(beats):
        if idx == len(beats) - 1:
            q = max(1, num_scenes - assigned)
        else:
            q = max(1, int(round((b.duration_sec / total_beat_dur) * num_scenes)))
            q = min(q, max(1, num_scenes - assigned - (len(beats) - 1 - idx)))
        beat_quotas.append(q)
        assigned += q

    camera_moves = [
        "Slow cinematic macro push-in, crisp edge rim lighting, shallow depth of field",
        "Dynamic orbital tracking sweep, clean volumetric depth, dramatic contrast",
        "Crisp overhead crane pull-back revealing full conceptual layout",
        "Tight punch-in detail shot with kinetic light accents, smooth 24fps stabilization",
        "Parallax slide transition moving cleanly across high-contrast focal elements",
    ]

    for b, q in zip(beats, beat_quotas):
        for sub_i in range(q):
            sub_ratio = f"Part {sub_i + 1}/{q}" if q > 1 else "Core Shot"
            dur = round(max(7.5, min(12.0, b.duration_sec / float(q))), 1)

            # Decide whether this sub-scene uses analytical motion graphics (every 4th scene or keyword match)
            detected_mg = detect_motion_graphic_type(f"{b.beat_title} {b.narrative_summary} {b.visual_direction}", agent1.niche)
            use_mg = bool(detected_mg and (sub_i == 1 or (scene_idx % 4 == 0)))
            asset_mode = "motion_graphics" if use_mg else "ai_video"
            mg_type = detected_mg if use_mg else "none"

            if b.phase == "Visual_Hook_0_45s" and sub_i == 0:
                vo = agent1.hook_script_0_45s
            elif b.phase == "Climax_Aha" and sub_i == 0:
                vo = agent1.climax_misconception_aha
            elif b.phase == "Outro_CTA" and sub_i == q - 1:
                vo = agent1.outro_cta_script
            else:
                if is_hinglish:
                    vo = (
                        f"{b.beat_title} ke is critical angle ko dekho — {b.narrative_summary} "
                        f"Dhyan dena: {b.retention_device} yahan pura perspective change kar deta hai!"
                    )
                elif is_hindi:
                    vo = (
                        f"{b.beat_title} के इस महत्वपूर्ण पहलू को समझिए — {b.narrative_summary} "
                        f"यही बिंदु पूरी कहानी को स्पष्ट कर देता है।"
                    )
                else:
                    vo = (
                        f"Look closely at {b.beat_title} ({sub_ratio}): {b.narrative_summary} "
                        f"Notice how {b.retention_device.lower()} reveals what really drives {agent1.topic}."
                    )

            ssml_cues = (
                f"[Energetic, warm Indian creator tone] {vo.split('.')[0]}. "
                f"<break time=\"0.4s\"/> {'. '.join(vo.split('.')[1:]).strip() or 'Keep watching closely!'}"
            )

            cam = camera_moves[(scene_idx - 1) % len(camera_moves)]
            visual_prompt = (
                f"Single unbroken 24fps cinematic shot representing '{b.beat_title}' ({sub_ratio}) "
                f"for the topic '{agent1.topic}' in the {agent1.niche} niche. "
                f"Visual direction: {b.visual_direction}. "
                f"Style lock: {prof['visual_style']}. Camera: {cam}. "
                f"No deformed text, no watermarks, zero visual hallucination."
            )

            mg_payload: Dict[str, Any] = {}
            if use_mg:
                mg_payload = {
                    "labels": ["Stage 1", "Stage 2", "Stage 3", "Stage 4", "Impact"],
                    "values": [18 + (scene_idx % 10), 36, 54, 78, 94],
                }

            scenes.append(
                SceneClipSpec(
                    scene_index=scene_idx,
                    beat_phase=b.phase,
                    chapter_label=b.beat_title,
                    start_sec=round(cursor, 1),
                    duration_sec=dur,
                    asset_mode=asset_mode,  # type: ignore[arg-type]
                    motion_graphic_type=mg_type,  # type: ignore[arg-type]
                    motion_graphic_payload=mg_payload,
                    visual_prompt_veo_omni=visual_prompt,
                    camera_and_lighting_cue=cam,
                    voiceover_text=vo,
                    ssml_voice_cues=ssml_cues,
                    on_screen_callout=f"{b.beat_title[:42]}",
                    sfx_cue="crisp whoosh riser" if sub_i == 0 else "subtle kinetic click",
                )
            )
            cursor += dur
            scene_idx += 1

    chapters_md = _compute_chapters_markdown(scenes)
    return Agent2Output(
        topic=agent1.topic,
        niche=agent1.niche,
        language_tone=agent1.language_tone,
        total_scenes=len(scenes),
        total_estimated_duration_sec=round(sum(s.duration_sec for s in scenes), 1),
        chapters_markdown=chapters_md,
        scenes=scenes,
    )


def run_agent2_scene_scripting(
    agent1: Agent1Output,
    *,
    target_scene_count: Optional[int] = None,
    config: Optional[OmniStudioConfig] = None,
) -> Agent2Output:
    """
    Executes Agent 2 (Multi-Model Visual & Vocal Scripting Agent).
    Produces 30–50 granular 8–12s scenes for 5–8 minute videos (scaled cleanly if target duration differs).
    """
    cfg = config or OmniStudioConfig()
    total_sec = max(60.0, float(agent1.target_duration_minutes) * 60.0)
    # 8-Second Visual Reset Rule: ~10s avg cut length -> 30 scenes for 5 min, 36 for 6 min, 48 for 8 min
    computed_scenes = int(round(total_sec / 10.0))
    desired_count = target_scene_count or max(12, min(50, computed_scenes))

    baseline = _expand_deterministic_scenes(agent1, desired_count)

    if not cfg.has_valid_gemini_key:
        return baseline

    try:
        client = get_genai_client(cfg.gemini_api_key)
        prof = get_niche_profile(agent1.niche)

        # Generate in clean batches of up to 18 scenes per call to preserve high prompt quality & prevent truncation
        batch_size = 18
        enriched_scenes: List[SceneClipSpec] = []
        models_chain = [
            resolve_current_model(REASONING_FALLBACK_MODEL, "gemini-4-argon"),
            resolve_current_model(FAST_AGENT_MODEL, "gemini-3.8-flash"),
            resolve_current_model(SCRIPT_FRONTIER_MODEL, "gemini-4-carbon"),
        ]

        for b_start in range(0, len(baseline.scenes), batch_size):
            slice_scenes = baseline.scenes[b_start : b_start + batch_size]
            prompt = (
                f"You are Agent 2 (Multi-Model Visual & Vocal Scriptwriter) in OMNI STUDIO.\n"
                f"Topic: {agent1.topic} | Niche: {agent1.niche} | Language & Tone: {agent1.language_tone}\n"
                f"Niche Visual Grammar (STRICT): {prof['visual_style']}\n"
                f"Selected Title: {agent1.selected_title}\n"
                f"Opening Hook Direction: {agent1.hook_script_0_45s}\n"
                f"Climax Misconception Reveal: {agent1.climax_misconception_aha}\n\n"
                f"Rewrite and elevate these {len(slice_scenes)} consecutive scenes (indices {slice_scenes[0].scene_index} to {slice_scenes[-1].scene_index}) "
                f"into razor-sharp, non-repetitive, high-retention scenes (8-12 seconds each):\n"
                f"1. `voiceover_text`: Natural, punchy, non-repetitive narration strictly in {agent1.language_tone} (~18-26 spoken words per 10s scene so it matches the 8-12s cut length cleanly!).\n"
                f"2. `ssml_voice_cues`: Same narration enhanced with emotion hints and `<break time=\"0.4s\"/>` dramatic pauses before twists.\n"
                f"3. `visual_prompt_veo_omni`: Concrete, filmable single-shot prompt optimized for Vertex Veo 3.1 / Gemini Omni 1.2 Flash / Google Flow in the {agent1.niche} aesthetic (zero visual hallucination).\n"
                f"4. For scenes containing numbers, comparisons, timelines, or formulas, set `asset_mode='motion_graphics'`, choose `motion_graphic_type` ('manim_formula'|'data_chart'|'comparison_chart'|'timeline_chart'), and fill realistic topic-specific `motion_graphic_payload` (`{{\"labels\": [...], \"values\": [...]}}`).\n"
                f"5. Provide a crisp 3-6 word `on_screen_callout` for each scene.\n\n"
                f"Baseline scaffold JSON:\n{json.dumps([s.model_dump() for s in slice_scenes], ensure_ascii=False)}"
            )

            from pydantic import BaseModel as _PydBase

            class _SceneBatch(_PydBase):
                scenes: List[SceneClipSpec]

            interaction = call_interaction_with_fallback(
                client,
                models=models_chain,
                max_retries=2,
                input=prompt,
                response_format={
                    "type": "text",
                    "mime_type": "application/json",
                    "schema": _SceneBatch.model_json_schema(),
                },
            )
            raw = (getattr(interaction, "output_text", None) or "").strip()
            if raw:
                batch_obj = _SceneBatch.model_validate_json(raw)
                if len(batch_obj.scenes) == len(slice_scenes):
                    enriched_scenes.extend(batch_obj.scenes)
                    continue
            enriched_scenes.extend(slice_scenes)

        # Normalize sequential indices & timestamps
        for idx, sc in enumerate(enriched_scenes, start=1):
            sc.scene_index = idx
        chapters_md = _compute_chapters_markdown(enriched_scenes)
        return Agent2Output(
            topic=agent1.topic,
            niche=agent1.niche,
            language_tone=agent1.language_tone,
            total_scenes=len(enriched_scenes),
            total_estimated_duration_sec=round(sum(s.duration_sec for s in enriched_scenes), 1),
            chapters_markdown=chapters_md,
            scenes=enriched_scenes,
        )
    except Exception as exc:
        logger.info("Agent 2 LLM scripting fell back to structured baseline scenes: %s", exc)
        return baseline
