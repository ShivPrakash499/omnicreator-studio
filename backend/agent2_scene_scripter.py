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
    CINEMATIC_SHOT_CHOREOGRAPHY,
    DEFAULT_CINEMA_PRESET,
    FAST_AGENT_MODEL,
    REASONING_FALLBACK_MODEL,
    SCRIPT_FRONTIER_MODEL,
    STRICT_ENGLISH_NO_FOREIGN_TEXT_RULE,
    OmniStudioConfig,
    build_cinematic_video_prompt,
    call_interaction_with_fallback,
    format_timestamp,
    get_cinema_preset,
    get_genai_client,
    get_niche_profile,
    resolve_current_model,
)
from backend.schemas import Agent1Output, Agent2Output, SceneClipSpec

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


def _expand_deterministic_scenes(
    agent1: Agent1Output,
    desired_scene_count: int,
    *,
    cinema_preset: str = DEFAULT_CINEMA_PRESET,
) -> Agent2Output:
    """
    Deterministic multi-niche cinematography expander guaranteeing 8-12s scene pacing
    (30-50 scenes for 5-8 min) with rotating 8-shot Hollywood framing choreography.
    """
    prof = get_niche_profile(agent1.niche)
    preset = get_cinema_preset(cinema_preset)
    total_target_sec = max(60.0, float(agent1.target_duration_minutes) * 60.0)
    num_scenes = max(8, min(55, int(desired_scene_count)))

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

    for b, q in zip(beats, beat_quotas):
        for sub_i in range(q):
            sub_ratio = f"Part {sub_i + 1}/{q}" if q > 1 else "Core Shot"
            dur = round(max(7.5, min(12.0, b.duration_sec / float(q))), 1)

            # Default ALL scenes to seamless AI Cinema (`ai_video`) so no flat Python charts interrupt the video!
            # Users can still manually toggle any individual scene to `motion_graphics` in Step 2 if desired.
            asset_mode = "ai_video"
            mg_type = "none"

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

            split_char = "।" if "।" in vo else "."
            vo_parts = [p.strip() for p in vo.split(split_char) if p.strip()]
            if len(vo_parts) >= 2:
                ssml_cues = (
                    f"[Energetic, warm Indian creator tone] {vo_parts[0]}{split_char} "
                    f"<break time=\"0.4s\"/> {f'{split_char} '.join(vo_parts[1:])}{split_char}"
                )
            else:
                ssml_cues = f"[Energetic, warm Indian creator tone] {vo}"

            choreo = CINEMATIC_SHOT_CHOREOGRAPHY[(scene_idx - 1) % len(CINEMATIC_SHOT_CHOREOGRAPHY)]
            cam = f"{choreo['shot_type']}: {choreo['camera_move']}. {choreo['lighting']}."
            raw_shot = (
                f"{choreo['shot_type']} bringing '{b.beat_title}' ({sub_ratio}) to life for '{agent1.topic}'. "
                f"Scene action: {b.visual_direction}. "
                f"Camera choreography: {choreo['camera_move']}. "
                f"Lighting & atmosphere: {choreo['lighting']}; {preset['lighting_signature']}. "
                f"Film aesthetic: {preset['camera_rig']}; {preset['color_grade']}; {prof['visual_style']}."
            )
            visual_prompt = build_cinematic_video_prompt(
                raw_shot,
                niche=agent1.niche,
                cinema_preset=cinema_preset,
                camera_cue=cam,
                sfx_cue=f"realistic environmental ambience and physical foley matching '{b.beat_title}'",
                duration_sec=dur,
                scene_index=scene_idx,
            )

            mg_payload: Dict[str, Any] = {}

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
                    sfx_cue=f"realistic environmental ambience and physical foley matching '{b.beat_title}'",
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
    cinema_preset: str = DEFAULT_CINEMA_PRESET,
    config: Optional[OmniStudioConfig] = None,
) -> Agent2Output:
    """
    Executes Agent 2 (Multi-Model Visual & Vocal Scripting Agent).
    Produces 30–50 granular 8–12s Hollywood-grade cinematic scenes for 5–8 minute videos.
    """
    cfg = config or OmniStudioConfig()
    total_sec = max(60.0, float(agent1.target_duration_minutes) * 60.0)
    # 8-Second Visual Reset Rule: ~10s avg cut length -> 30 scenes for 5 min, 36 for 6 min, 48 for 8 min
    computed_scenes = int(round(total_sec / 10.0))
    desired_count = target_scene_count or max(12, min(50, computed_scenes))

    baseline = _expand_deterministic_scenes(agent1, desired_count, cinema_preset=cinema_preset)

    if not cfg.has_valid_gemini_key:
        return baseline

    try:
        client = get_genai_client(cfg.gemini_api_key)
        prof = get_niche_profile(agent1.niche)
        preset = get_cinema_preset(cinema_preset)

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
            char_bible_block = (
                f"LOCKED CHARACTER IDENTITY BIBLE (CRITICAL — ZERO FACE DRIFT ACROSS ALL SCENES!):\n"
                f"  {agent1.character_bible}\n"
                f"  - Whenever the main protagonist appears on screen, set `features_main_character = true` AND describe them strictly matching the EXACT age, face, forehead markings/tilak, hairstyle, facial hair, and costume colors above (NEVER change their age, add/remove beards, or alter their outfit).\n"
                f"  - Whenever a scene is purely a wide landscape, temple exterior, crowd, or object close-up without the main protagonist in frame, set `features_main_character = false`.\n\n"
                if (agent1.character_bible or "").strip()
                else ""
            )
            prompt = (
                f"You are Agent 2 — an Award-Winning Film Director of Photography & Vocal Scriptwriter inside OMNI STUDIO.\n"
                f"Topic: {agent1.topic} | Niche: {agent1.niche} | Language & Tone: {agent1.language_tone}\n"
                f"Cinema Look Preset: {cinema_preset}\n"
                f"  - Camera Rig & Lens: {preset['camera_rig']}\n"
                f"  - Lighting Signature: {preset['lighting_signature']}\n"
                f"  - Color Grade: {preset['color_grade']}\n"
                f"  - Camera Motion Style: {preset['motion_feel']}\n"
                f"Niche Visual Aesthetic: {prof['visual_style']}\n"
                f"Selected Title: {agent1.selected_title}\n"
                f"Opening Hook Direction: {agent1.hook_script_0_45s}\n"
                f"Climax Misconception Reveal: {agent1.climax_misconception_aha}\n\n"
                f"{char_bible_block}"
                f"Rewrite and elevate these {len(slice_scenes)} consecutive scenes (indices {slice_scenes[0].scene_index} to {slice_scenes[-1].scene_index}) "
                f"into breathtaking, filmable, high-retention cinema (8-12 seconds each):\n"
                f"1. `voiceover_text`: Natural, punchy, non-repetitive narration strictly in {agent1.language_tone} (~18-26 spoken words per 10s scene so it aligns tightly with 8-12s cuts).\n"
                f"2. `ssml_voice_cues`: Same narration enhanced with expressive Indian creator emotion cues and `<break time=\"0.4s\"/>` dramatic pauses before reveals.\n"
                f"3. `visual_prompt_veo_omni` (CRITICAL — HOLLYWOOD 5-LAYER CINEMA FORMULA FOR GEMINI OMNI 1.2 FLASH & VEO 3.1):\n"
                f"   Every single scene prompt MUST be 55-95 words of vivid, concrete, physically filmable cinematography containing ALL FIVE layers:\n"
                f"   (a) SHOT SCALE & LENS (strictly alternate consecutive scenes: Wide Aerial Establishing -> Low-Angle Tracking -> 100mm Macro Detail -> Orbital Steadicam Arc -> Overhead Crane Reveal -> 120fps Slow-Mo Physics -> Foreground Parallax -> Horizon Pull-Back).\n"
                f"   (b) CONCRETE TANGIBLE SUBJECT & CONTINUOUS MOTION: Describe real physical subjects, environments, vehicles, hands, optics, architecture, nature, or light phenomena IN CONTINUOUS ACTION that visually illustrate the voiceover. NEVER describe abstract concepts, flat bar charts, PowerPoint slides, wireframe grids, neon grid floors, UI dashboard overlays, or floating text.\n"
                f"   (c) LIVED-IN ATMOSPHERE & MICRO-DETAILS: Foreground/midground/background depth layers, wet pavement specular reflections, drifting dust motes, steam, rain droplets, atmospheric haze, or natural background life.\n"
                f"   (d) MOTIVATED LIGHTING & FILM GRADE: Practical key lights, dramatic rim backlighting, volumetric shafts, shallow f/1.4 depth of field, cohesive with '{cinema_preset}'.\n"
                f"   (e) SINGLE UNBROKEN TAKE: Explicitly end with single unbroken continuous shot, no scene cuts, no dialogue, and {STRICT_ENGLISH_NO_FOREIGN_TEXT_RULE}\n"
                f"4. `camera_and_lighting_cue`: Concise 1-line DP note matching the scene's exact lens, movement, and lighting.\n"
                f"5. `sfx_cue` (CRITICAL — FRAME-SYNCED CINEMA FOLEY SOUND DESIGN): Describe the EXACT realistic physical sound effects "
                f"heard during the visible action of this scene (e.g., 'taut bowstring creak, explosive arrow release twang, and whistling flaming arrow cutting through air', "
                f"'revolving metallic divine chakra resonant cosmic hum with swirling wind vortex', 'distant temple conch shankh and rolling thunder', "
                f"'rain pattering on wet asphalt with deep electric hum', 'crackling fire embers and wind'). NEVER write cartoon beeps, 'ting', 'kinetic click', or generic risers.\n"
                f"6. Keep `asset_mode='ai_video'` and `motion_graphic_type='none'` for EVERY scene (zero flat Python charts).\n"
                f"7. Provide a crisp 3-6 word `on_screen_callout` in proper English for each scene.\n\n"
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

        # Normalize sequential indices, lock ai_video & polish every prompt through the cinema guard
        for idx, sc in enumerate(enriched_scenes, start=1):
            sc.scene_index = idx
            sc.asset_mode = "ai_video"
            sc.motion_graphic_type = "none"
            sc.visual_prompt_veo_omni = build_cinematic_video_prompt(
                sc.visual_prompt_veo_omni,
                niche=agent1.niche,
                cinema_preset=cinema_preset,
                camera_cue=sc.camera_and_lighting_cue,
                sfx_cue=sc.sfx_cue,
                duration_sec=sc.duration_sec,
                scene_index=idx,
            )
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


def enhance_all_scenes_to_cinema(
    agent2: Agent2Output,
    *,
    cinema_preset: str = DEFAULT_CINEMA_PRESET,
    character_bible: str = "",
    config: Optional[OmniStudioConfig] = None,
) -> Agent2Output:
    """
    Upgrades ALL scene visual prompts in an existing `Agent2Output` in-place to Hollywood-grade
    cinematography while strictly preserving the user's edited voiceovers, SSML cues, durations,
    and custom uploads. Enforces `character_bible` across every protagonist scene when provided.
    """
    cfg = config or OmniStudioConfig()
    prof = get_niche_profile(agent2.niche)
    preset = get_cinema_preset(cinema_preset)
    upgraded_scenes = [SceneClipSpec.model_validate(s.model_dump()) for s in agent2.scenes]
    clean_bible = (character_bible or "").strip()

    if cfg.has_valid_gemini_key:
        try:
            client = get_genai_client(cfg.gemini_api_key)
            models_chain = [
                resolve_current_model(FAST_AGENT_MODEL, "gemini-3.8-flash"),
                resolve_current_model(REASONING_FALLBACK_MODEL, "gemini-4-argon"),
            ]
            from pydantic import BaseModel as _PydBase

            class _CinemaRewriteItem(_PydBase):
                scene_index: int
                visual_prompt_veo_omni: str
                camera_and_lighting_cue: str
                sfx_cue: str
                features_main_character: Optional[bool] = None

            class _CinemaRewriteBatch(_PydBase):
                items: List[_CinemaRewriteItem]

            char_bible_block = (
                f"LOCKED CHARACTER IDENTITY BIBLE (CRITICAL — ZERO FACE DRIFT ACROSS ALL SCENES!):\n"
                f"  {clean_bible}\n"
                f"  - Whenever the main protagonist appears on screen, set `features_main_character = true` AND "
                f"describe them strictly matching the EXACT age, face, forehead markings/tilak, hairstyle, facial hair, "
                f"and costume colors above (NEVER change age, add/remove beards, or alter attire).\n"
                f"  - Whenever a scene is purely a landscape, temple exterior, crowd, or prop close-up without the "
                f"main protagonist in frame, set `features_main_character = false`.\n\n"
                if clean_bible
                else ""
            )

            batch_size = 18
            for b_start in range(0, len(upgraded_scenes), batch_size):
                chunk = upgraded_scenes[b_start : b_start + batch_size]
                compact_in = [
                    {
                        "scene_index": s.scene_index,
                        "chapter_label": s.chapter_label,
                        "duration_sec": s.duration_sec,
                        "voiceover_text": s.voiceover_text,
                        "current_visual_prompt": s.visual_prompt_veo_omni,
                        "current_sfx_cue": s.sfx_cue,
                        "features_main_character": s.features_main_character,
                    }
                    for s in chunk
                ]
                prompt = (
                    f"You are an Academy-Award Director of Photography & Supervising Sound Editor upgrading scenes for "
                    f"Gemini Omni 1.2 Flash & Veo 3.1.\n"
                    f"Topic: {agent2.topic} | Niche: {agent2.niche} | Cinema Look: {cinema_preset}\n"
                    f"Rig & Grade: {preset['camera_rig']}; {preset['lighting_signature']}; {preset['color_grade']}\n"
                    f"Niche Visual Grammar: {prof['visual_style']}\n\n"
                    f"{char_bible_block}"
                    f"Rewrite `visual_prompt_veo_omni`, `camera_and_lighting_cue`, `sfx_cue`, and `features_main_character` "
                    f"for each scene below into jaw-dropping 55-90 word photorealistic single-take cinema prompts with "
                    f"frame-accurate Foley SFX:\n"
                    f"- Alternate shot scales across consecutive scenes (Wide Establishing, Low-Angle Tracking, 100mm Macro, "
                    f"Orbital Steadicam, Aerial Top-Down, 120fps Slow-Mo, Foreground Parallax, Horizon Pull-Back).\n"
                    f"- Replace any chart, slide, text card, infographic, or wireframe grid imagery with vivid physical "
                    f"real-world environments, tactile materials, atmospheric depth (rain/mist/dust/reflections), and natural motion.\n"
                    f"- In `sfx_cue`, write concrete physical sound effects matching the action (e.g. bowstring snap & arrow whistle, "
                    f"revolving metallic chakra cosmic hum, rolling thunder, fire crackle, wet tires) — zero cartoon beeps or clicks.\n"
                    f"- Strictly single unbroken shot, no scene cuts, no spoken dialogue, zero Chinese/foreign letters.\n\n"
                    f"Scenes:\n{json.dumps(compact_in, ensure_ascii=False)}"
                )
                interaction = call_interaction_with_fallback(
                    client,
                    models=models_chain,
                    max_retries=2,
                    input=prompt,
                    response_format={
                        "type": "text",
                        "mime_type": "application/json",
                        "schema": _CinemaRewriteBatch.model_json_schema(),
                    },
                )
                raw = (getattr(interaction, "output_text", None) or "").strip()
                if raw:
                    parsed = _CinemaRewriteBatch.model_validate_json(raw)
                    by_idx = {it.scene_index: it for it in parsed.items}
                    for s in chunk:
                        if s.scene_index in by_idx:
                            s.visual_prompt_veo_omni = by_idx[s.scene_index].visual_prompt_veo_omni
                            s.camera_and_lighting_cue = by_idx[s.scene_index].camera_and_lighting_cue
                            if by_idx[s.scene_index].sfx_cue.strip():
                                s.sfx_cue = by_idx[s.scene_index].sfx_cue.strip()
                            if by_idx[s.scene_index].features_main_character is not None:
                                s.features_main_character = bool(by_idx[s.scene_index].features_main_character)
        except Exception as exc:
            logger.info("LLM batch cinema prompt enhancer fell back to deterministic DP polish: %s", exc)

    # Guarantee every scene is normalized to ai_video (unless user attached custom upload) + cinema-polished
    for idx, sc in enumerate(upgraded_scenes, start=1):
        sc.scene_index = idx
        if sc.asset_mode != "custom_upload":
            sc.asset_mode = "ai_video"
            sc.motion_graphic_type = "none"
        sc.visual_prompt_veo_omni = build_cinematic_video_prompt(
            sc.visual_prompt_veo_omni,
            niche=agent2.niche,
            cinema_preset=cinema_preset,
            camera_cue=sc.camera_and_lighting_cue,
            sfx_cue=sc.sfx_cue,
            duration_sec=sc.duration_sec,
            scene_index=idx,
        )

    return Agent2Output(
        topic=agent2.topic,
        niche=agent2.niche,
        language_tone=agent2.language_tone,
        total_scenes=len(upgraded_scenes),
        total_estimated_duration_sec=round(sum(s.duration_sec for s in upgraded_scenes), 1),
        chapters_markdown=_compute_chapters_markdown(upgraded_scenes),
        scenes=upgraded_scenes,
    )
