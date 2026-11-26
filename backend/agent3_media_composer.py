"""
Agent 3: Media Generator & Composer Agent (`backend/agent3_media_composer.py`)
==============================================================================
Orchestrates asynchronous multi-asset media synthesis & broadcast assembly:
1. Voiceover Synthesis (Cloud TTS Chirp 3 HD -> `gemini-3.8-flash-tts` -> local Edge-TTS)
   with exact WAV duration validation anchoring B-roll pacing per scene.
2. Visual Asset Engine per scene:
   - Custom user-uploaded footage/image override (`custom_asset_path`)
   - Procedural Motion Graphics (`render_engine/motion_graphics.py`: Manim / Matplotlib / Vector HUD)
   - Generative AI Video / Keyframe B-Roll (`gemini-omni-1.2-flash` / `gemini-nano-banana-2.1` /
     optional Vertex Veo 3.1 + high-contrast cinematic kinetic B-roll fallback)
3. Word-level active-highlight `.ass` subtitles (`render_engine/subtitle_engine.py`) burned cleanly
   into BOTH 16:9 (1080p) and 9:16 (Shorts/vertical) outputs.
4. High-spirited niche-matched background music (`lyria-3.5` / procedural synth) ducked strictly
   at **-24dB** during narration + crisp cut SFX (`render_engine/audio_mixer.py`).
5. High-CTR Thumbnail Generator (`render_engine/thumbnail_studio.py`) preserving `@jwalashiva`'s
   likeness (`assets/likeness/image_12..14.png`, Nehru jacket/vest, pointing gesture, glowing
   topic graphics, neon typography & badge matching `image_11.png`).

Persists granular real-time progress logs ("Processing (45%)", "Completed ✅") directly into SQLite!
"""

from __future__ import annotations

import base64
import gc
import json
import logging
import math
import re
import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import imageio_ffmpeg
from PIL import Image, ImageDraw, ImageFont

from backend.config import (
    DEFAULT_BGM_PRESET,
    DEFAULT_CINEMA_PRESET,
    FAST_AGENT_MODEL,
    IMAGE_CONTINUITY_MODEL,
    IMAGE_PRO_MODEL,
    STRICT_ENGLISH_NO_FOREIGN_TEXT_RULE,
    VEO_STRICT_NEGATIVE_PROMPT,
    VERTEX_VEO_MODEL,
    VIDEO_OMNI_MODEL,
    OmniStudioConfig,
    build_cinematic_video_prompt,
    call_interaction_with_fallback,
    format_timestamp,
    get_genai_client,
    get_niche_profile,
    get_vertex_adc_credentials,
    resolve_current_model,
    sanitize_slug,
)
from google.genai import types as genai_types
from backend.schemas import Agent1Output, Agent2Output, Agent3Output, RenderedSceneArtifact, SceneClipSpec
from render_engine.audio_mixer import (
    concat_wav_segments,
    generate_niche_bgm_stem,
    mix_scene_master_audio,
    synthesize_scene_voiceover,
)
from render_engine.foley_sfx import extract_native_video_foley, synthesize_scene_foley_fallback
from render_engine.motion_graphics import render_motion_graphic_clip
from render_engine.subtitle_engine import (
    TimedWord,
    extract_scene_word_timestamps,
    write_active_highlight_ass_file,
)
from render_engine.thumbnail_studio import generate_high_ctr_thumbnail
from storage.db import OmniDatabase, get_db

logger = logging.getLogger("omni_studio.agent3")

# Serialize heavy 1080p libx264 encodes & cap FFmpeg threads/lookahead so peak RAM stays <120MB
# on 1 GB cloud containers (prevents Linux OOM SIGKILL on Streamlit Community Cloud!).
_FFMPEG_ENCODE_LOCK = threading.Lock()
_LOW_RAM_X264_ARGS: List[str] = [
    "-threads", "2",
    "-x264-params", "rc-lookahead=10:sync-lookahead=0:threads=2",
]


def _hex_to_rgb(hex_color: str, fallback: Tuple[int, int, int] = (0, 229, 255)) -> Tuple[int, int, int]:
    h = hex_color.lstrip("#")
    if len(h) == 6:
        try:
            return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))
        except Exception:
            pass
    return fallback


def _load_scene_font(size: int, bold: bool = True) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for p in [
        "C:/Windows/Fonts/segoeuib.ttf" if bold else "C:/Windows/Fonts/segoeui.ttf",
        "C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]:
        if Path(p).exists():
            try:
                return ImageFont.truetype(p, size=size)
            except Exception:
                pass
    return ImageFont.load_default()


def _render_kinetic_cinematic_plate(
    output_png: Path,
    *,
    scene: SceneClipSpec,
    topic: str,
    niche: str,
    size: Tuple[int, int] = (1920, 1080),
) -> Path:
    """
    Renders a clean, non-cluttered cinematic dark-studio plate with niche-matched volumetric light
    and sleek minimal top-corner chapter callout (zero hallucination, crisp legibility).
    """
    w, h = size
    prof = get_niche_profile(niche)
    acc = _hex_to_rgb(prof["accent_hex"])
    sec = _hex_to_rgb(prof["secondary_hex"])

    img = Image.new("RGBA", (w, h), (7, 11, 20, 255))
    draw = ImageDraw.Draw(img, "RGBA")

    phase = scene.scene_index * 0.72
    cx = int(w * (0.50 + 0.14 * math.sin(phase)))
    cy = int(h * (0.48 + 0.08 * math.cos(phase)))
    max_r = max(w, h)
    for r in range(max_r, 80, -55):
        t = 1.0 - (r / float(max_r))
        col = (
            int(7 + acc[0] * 0.24 * t),
            int(11 + acc[1] * 0.24 * t),
            int(20 + acc[2] * 0.30 * t),
            255,
        )
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=col)

    # Geometric dynamic light ribbons / focal rings (clean modern broadcast look)
    for ring_idx in range(3):
        rr = int(min(w, h) * (0.14 + ring_idx * 0.11))
        col_r = acc if ring_idx % 2 == 0 else sec
        draw.ellipse([cx - rr, cy - rr, cx + rr, cy + rr], outline=(*col_r, 120 - ring_idx * 25), width=4)

    for k in range(10):
        ang = phase + (k * math.pi / 5.0)
        x1, y1 = int(cx + math.cos(ang) * 90), int(cy + math.sin(ang) * 90)
        x2, y2 = int(cx + math.cos(ang) * 340), int(cy + math.sin(ang) * 340)
        draw.line([(x1, y1), (x2, y2)], fill=(*acc, 65), width=2)
        draw.ellipse([x2 - 8, y2 - 8, x2 + 8, y2 + 8], fill=(*sec, 195))

    # Centered safe-zone top callout pill (never clipped by Ken-Burns pan or 9:16 vertical center-crop)
    f_badge = _load_scene_font(20, bold=True)
    f_callout = _load_scene_font(30, bold=True)
    pill_w = min(w - 220, 620)
    px1 = (w - pill_w) // 2
    py1 = 96
    draw.rounded_rectangle(
        [px1, py1, px1 + pill_w, py1 + 98],
        radius=16,
        fill=(10, 16, 30, 215),
        outline=(*acc, 210),
        width=2,
    )
    draw.text((px1 + 24, py1 + 12), f"{niche.split('&')[0].strip().upper()}  •  SCENE {scene.scene_index:02d}", fill=(*acc, 255), font=f_badge)
    draw.text((px1 + 24, py1 + 46), (scene.on_screen_callout or topic)[:34], fill=(248, 250, 252, 255), font=f_callout)

    output_png.parent.mkdir(parents=True, exist_ok=True)
    img.convert("RGB").save(output_png, format="PNG", optimize=True)
    return output_png


def _probe_video_duration_sec(video_path: Path) -> float:
    """Measures exact source duration (in seconds) of an MP4 clip via FFmpeg header inspection."""
    import re as _re
    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    res = subprocess.run(
        [ffmpeg_exe, "-i", str(video_path)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    m = _re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", res.stderr or "")
    if m:
        return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
    return 0.0


def _normalize_video_clip_exact(
    raw_src: Path,
    output_mp4: Path,
    *,
    w: int,
    h: int,
    fps: int,
    exact_frames: int,
    trim_source_sec: Optional[float] = None,
    start_offset_sec: Optional[float] = None,
) -> Path:
    """
    Normalizes ANY source video clip (Omni 1.2 Flash, Veo 3.1, Custom Upload, Sewn Flow Master, Motion Graphic)
    to EXACTLY `exact_frames` closed-GOP zero-B-frame CFR frames at `fps` with uniform bt709
    pixel format & 24000 timescale — ZERO hard loop jumps, ZERO frame drift, ZERO overlap!
    """
    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    target_dur = exact_frames / float(fps)
    full_src_dur = _probe_video_duration_sec(raw_src)
    seek_val = max(0.0, float(start_offset_sec or 0.0))
    avail_after_seek = max(0.5, full_src_dur - seek_val) if full_src_dur > 0.0 else 0.0
    in_seek_args: List[str] = ["-ss", f"{seek_val:.4f}"] if seek_val > 0.01 else []
    in_trim_args: List[str] = []
    if trim_source_sec and trim_source_sec > 0.5 and (avail_after_seek <= 0.0 or trim_source_sec < avail_after_seek - 0.05):
        in_trim_args = ["-t", f"{trim_source_sec:.4f}"]
        src_dur = min(avail_after_seek, trim_source_sec) if avail_after_seek > 0.0 else trim_source_sec
    else:
        src_dur = avail_after_seek if avail_after_seek > 0.0 else full_src_dur
    scale_crop = f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},setsar=1"

    if src_dur > 0.4 and src_dur < target_dur - 0.08:
        stretch = target_dur / src_dur
        if stretch <= 2.15:
            # Smooth theatrical slow-motion stretch + tpad safety clone (zero ping-pong reversal & exact frame count!)
            vf = f"{scale_crop},setpts={stretch:.5f}*(PTS-STARTPTS),fps={fps},tpad=stop_mode=clone:stop_duration=1.5,format=yuv420p"
            cmd = [ffmpeg_exe, "-y", *in_seek_args, *in_trim_args, "-i", str(raw_src), "-vf", vf]
        else:
            # Extreme fallback (>2.15x): forward + reverse ping-pong with gentle slow-mo
            half_stretch = max(1.0, min(2.0, target_dur / (2.0 * src_dur)))
            fc = (
                f"[0:v]{scale_crop},setpts=PTS-STARTPTS,split[a][b];"
                f"[b]reverse,setpts=PTS-STARTPTS[r];"
                f"[a][r]concat=n=2:v=1:a=0,setpts={half_stretch:.5f}*(PTS-STARTPTS),fps={fps},"
                f"tpad=stop_mode=clone:stop_duration=1.5,format=yuv420p[vout]"
            )
            cmd = [ffmpeg_exe, "-y", *in_seek_args, *in_trim_args, "-i", str(raw_src), "-filter_complex", fc, "-map", "[vout]"]
    else:
        vf = f"{scale_crop},setpts=PTS-STARTPTS,fps={fps},tpad=stop_mode=clone:stop_duration=1.5,format=yuv420p"
        cmd = [ffmpeg_exe, "-y", *in_seek_args, *in_trim_args, "-i", str(raw_src), "-vf", vf]

    # Always pad last frame via tpad safety if source was a hair short, then cut to EXACT `exact_frames`
    # Using uniform closed-GOP `-bf 0 -g fps -video_track_timescale 24000` guarantees zero concat bleed!
    cmd.extend([
        "-r", str(fps),
        "-frames:v", str(exact_frames),
        "-video_track_timescale", "24000",
        "-bf", "0",
        "-g", str(fps),
        "-colorspace", "bt709",
        "-color_primaries", "bt709",
        "-color_trc", "bt709",
        "-an",
        "-c:v", "libx264", "-preset", "superfast", "-crf", "20",
        *_LOW_RAM_X264_ARGS,
        str(output_mp4),
    ])
    with _FFMPEG_ENCODE_LOCK:
        subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return output_mp4


_CHARACTER_STOPWORDS = {
    "the", "and", "for", "with", "from", "into", "about", "behind", "story", "rahasya", "mystery",
    "secret", "secrets", "truth", "hidden", "explained", "complete", "history", "katha", "video",
    "mahabharata", "ramayana", "temple", "shrine", "baba", "shree", "shri", "lord", "king", "prince",
    "queen", "warrior", "hero", "protagonist", "character", "young", "ancient", "indian", "male",
    "female", "man", "woman", "boy", "girl", "early", "late", "mid", "20s", "30s", "40s", "skin",
    "tone", "warm", "wheatish", "dark", "black", "gold", "golden", "saffron", "deep", "eyes", "hair",
    "face", "sharp", "jawline", "wearing", "drape", "armor", "tilak", "forehead", "arrows", "glowing",
    "main", "recurring", "sacred", "divine", "epic", "battlefield", "kurukshetra", "rajasthan",
    "india", "how", "why", "what", "when", "where", "which", "that", "this", "their", "your",
}

_PERSON_PRESENCE_CUES = (
    "warrior", "man", "young", "face", "eyes", "portrait", "kneeling", "standing", "riding",
    "holding", "drawing", "aiming", "bow", "smiling", "looking", "gazing", "figure", "hero",
    "protagonist", "character", "prince", "sage", "king", "queen", "woman", "boy", "girl",
    "person", "hands", "silhouette", "close-up of his", "close-up of her",
    "close up of his", "close up of her", "medium shot of", "low-angle shot of", "over-the-shoulder",
)

_NON_CHARACTER_SCENERY_CUES = (
    "temple exterior", "aerial establishing", "empty battlefield", "empty landscape",
    "architecture", "shrine exterior", "marble temple", "crowd of", "devotees", "village",
    "statue", "idol", "resting on", "close-up of arrows", "three arrows floating",
)


def _extract_character_keywords(character_bible: str, topic: str = "") -> List[str]:
    """
    Extracts primary character proper-name keywords (e.g. `barbarik`, `barbar`, `shyam`, `krishna`)
    so scenes featuring the protagonist receive visual reference anchoring while empty landscapes do not.
    """
    keywords: List[str] = []
    seen: set = set()

    def _add(tok: str) -> None:
        t = re.sub(r"[^a-zA-Z]", "", tok).lower()
        if len(t) >= 4 and t not in _CHARACTER_STOPWORDS and t not in seen:
            seen.add(t)
            keywords.append(t)

    # Priority 1: Leading proper nouns from character_bible (first 140 chars / before colon/dash)
    bible_head = (character_bible or "").strip()[:140]
    if bible_head:
        lead_segment = re.split(r"[:\-\(\n,.]", bible_head)[0]
        for w in re.findall(r"[A-Za-z][a-zA-Z]{3,}", lead_segment):
            _add(w)
        # Also include capitalized proper names from first sentence of character_bible
        first_sent = bible_head.split(".")[0]
        for w in re.findall(r"\b[A-Z][a-z]{3,}\b", first_sent):
            _add(w)

    # Priority 2: Proper-name tokens from topic if bible yielded few keywords
    if len(keywords) < 2 and topic:
        for w in re.findall(r"[A-Za-z][a-zA-Z]{3,}", topic):
            _add(w)

    # Add common stem variant (e.g., "barbarik" -> also match "barbar")
    extra: List[str] = []
    for kw in keywords:
        if kw.endswith("ik") and len(kw) >= 7:
            stem = kw[:-2]
            if stem not in seen:
                seen.add(stem)
                extra.append(stem)
    keywords.extend(extra)
    return keywords[:8]


def _scene_mentions_character(
    scene: SceneClipSpec,
    character_keywords: List[str],
    *,
    has_explicit_flags: bool = False,
) -> bool:
    """
    Determines whether a given scene actually depicts the locked main character on screen.
    Prevents pasting a character portrait onto empty temple exteriors, aerial maps, or standalone objects.
    """
    if scene.features_main_character:
        return True

    vis_low = (scene.visual_prompt_veo_omni or "").lower()
    if not vis_low:
        return False

    has_person_cue = any(cue in vis_low for cue in _PERSON_PRESENCE_CUES)
    is_scenery_only = any(cue in vis_low for cue in _NON_CHARACTER_SCENERY_CUES) and not has_person_cue

    if is_scenery_only:
        return False

    # Check explicit character name tokens inside the visual prompt
    if any(re.search(rf"\b{re.escape(kw)}", vis_low) for kw in character_keywords):
        return True

    # For legacy projects (no explicit Agent 2 flags yet), lock shots explicitly depicting the hero/protagonist
    if not has_explicit_flags and character_keywords:
        if any(tok in vis_low for tok in ("protagonist", "main character", "young warrior", "divine warrior", "the warrior")):
            return True

    return False


def _generate_character_anchor_portrait(
    output_png: Path,
    *,
    agent1: Agent1Output,
    agent2: Agent2Output,
    reuse_existing: bool = False,
    config: OmniStudioConfig,
) -> Tuple[Optional[Path], str]:
    """
    Generates ONE high-detail neutral-backdrop studio reference portrait (`renders/character_anchor.png`, ~$0.04)
    for the video's recurring main character so EVERY scene (both AI cinema keyframes AND Gemini Omni 1.2 Flash
    full-motion video clips) locks the exact same face, age, tilak/markings, hair, and outfit!
    Returns `(anchor_png_path_or_None, effective_character_bible)`.
    """
    import time as _time

    bible = (agent1.character_bible or "").strip()
    anchor_prompt = (agent1.character_anchor_prompt or "").strip()

    # Auto-detect recurring protagonist on legacy projects (created before Character Lock existed!)
    if not bible and not anchor_prompt and config.has_valid_gemini_key:
        sample_scenes = [
            f"Scene {s.scene_index}: {s.visual_prompt_veo_omni[:180]}"
            for s in agent2.scenes[:8]
        ]
        try:
            from pydantic import BaseModel as _PydBase

            class _CharDetect(_PydBase):
                has_recurring_character: bool
                character_bible: str = ""
                character_anchor_prompt: str = ""

            client = get_genai_client(config.gemini_api_key, location="global")
            detect_prompt = (
                f"Analyze this video topic and sample scenes to check if there is ONE primary recurring human/mythological/historical "
                f"protagonist who appears across multiple scenes (e.g., Barbarik / Khatu Shyam, Arjuna, Krishna, Chanakya, Tesla, Einstein).\n"
                f"Topic: {agent1.topic} | Niche: {agent1.niche}\n"
                f"Sample scenes:\n" + "\n".join(sample_scenes) + "\n\n"
                f"- If YES: set `has_recurring_character=true`, write a hyper-specific 25-45 word immutable `character_bible` "
                f"(name, exact age, facial structure, skin tone, hair, facial hair, forehead tilak/markings, exact costume & signature props), "
                f"and a clean neutral-backdrop studio portrait prompt `character_anchor_prompt`.\n"
                f"- If NO (abstract tech, vehicles, science diagrams, products, nature, or varied crowd scenes with no recurring lead): "
                f"set `has_recurring_character=false` and empty strings."
            )
            inter = call_interaction_with_fallback(
                client,
                models=[resolve_current_model(FAST_AGENT_MODEL, "gemini-3.8-flash")],
                max_retries=1,
                input=detect_prompt,
                response_format={
                    "type": "text",
                    "mime_type": "application/json",
                    "schema": _CharDetect.model_json_schema(),
                },
            )
            raw = (getattr(inter, "output_text", None) or "").strip()
            if raw:
                det = _CharDetect.model_validate_json(raw)
                if det.has_recurring_character and (det.character_bible.strip() or det.character_anchor_prompt.strip()):
                    bible = det.character_bible.strip()
                    anchor_prompt = det.character_anchor_prompt.strip() or bible
        except Exception as exc:
            logger.info("Auto character detection skipped: %s", exc)

    effective_bible = bible or anchor_prompt
    if not effective_bible:
        return None, ""

    # Reuse existing anchor portrait on disk when resuming or if already generated for this project
    if reuse_existing and output_png.exists() and output_png.stat().st_size > 16384:
        return output_png, effective_bible

    if not config.has_valid_gemini_key:
        return None, effective_bible

    portrait_desc = anchor_prompt or effective_bible
    studio_prompt = (
        f"Photorealistic 8K cinematic character reference portrait, head-and-shoulders three-quarter angle looking "
        f"clearly toward camera, sharp unobstructed facial features, natural warm human skin texture, crisp expressive "
        f"eyes, soft even studio key lighting against a clean plain warm dark-gray neutral studio backdrop (NO scenery, "
        f"NO crowd, NO text, NO watermarks, single person only): {portrait_desc}. "
        f"{STRICT_ENGLISH_NO_FOREIGN_TEXT_RULE}"
    )

    output_png.parent.mkdir(parents=True, exist_ok=True)
    v_creds, v_proj = get_vertex_adc_credentials()
    if v_creds is not None and v_proj:
        for m_kf in ("gemini-3-pro-image", resolve_current_model(IMAGE_CONTINUITY_MODEL, "gemini-nano-banana-2.1")):
            for attempt in range(1, 3):
                try:
                    client = get_genai_client(config.gemini_api_key, location="global")
                    resp = client.models.generate_content(
                        model=m_kf,
                        contents=studio_prompt,
                        config=genai_types.GenerateContentConfig(
                            response_modalities=["IMAGE"],
                            image_config=genai_types.ImageConfig(aspect_ratio="1:1"),
                        ),
                    )
                    for cand in getattr(resp, "candidates", []) or []:
                        for part in getattr(getattr(cand, "content", None), "parts", []) or []:
                            if getattr(part, "inline_data", None) and part.inline_data.data:
                                output_png.write_bytes(bytes(part.inline_data.data))
                                return output_png, effective_bible
                except Exception as exc:
                    if any(t in str(exc).lower() for t in ("429", "resource_exhausted", "503", "timeout")) and attempt < 2:
                        _time.sleep(3.0)
                        continue
                    logger.info("Character anchor portrait (%s) skipped: %s", m_kf, exc)
                    break
    else:
        try:
            client = get_genai_client(config.gemini_api_key)
            inter = call_interaction_with_fallback(
                client,
                models=["gemini-3-pro-image", resolve_current_model(IMAGE_CONTINUITY_MODEL, "gemini-nano-banana-2.1")],
                max_retries=2,
                input=studio_prompt,
                response_format={"type": "image", "aspect_ratio": "1:1", "image_size": "1K"},
            )
            out_img = getattr(inter, "output_image", None)
            if out_img and getattr(out_img, "data", None):
                raw_img = base64.b64decode(out_img.data) if isinstance(out_img.data, str) else bytes(out_img.data)
                output_png.write_bytes(raw_img)
                return output_png, effective_bible
        except Exception as exc:
            logger.info("Character anchor portrait skipped: %s", exc)

    return None, effective_bible


def _check_daily_budget_or_raise(
    next_cost_usd: float,
    *,
    cost_limit_usd: Optional[float] = None,
    database: Optional[OmniDatabase] = None,
) -> None:
    """Enforces the hard Daily Budget Throttle before any paid AI image or video API call."""
    from worker import BudgetLimitExceededError, get_worker_manager

    wm = get_worker_manager()
    if database is not None and database is not wm.db:
        limit = (
            round(float(cost_limit_usd), 2)
            if (cost_limit_usd is not None and cost_limit_usd > 0)
            else wm.get_daily_cost_limit_usd()
        )
        spent = database.get_daily_spend_usd()
        req = max(0.0, float(next_cost_usd))
        if (req > 0.0 and (spent + req) > limit + 1e-6) or (req == 0.0 and spent >= limit):
            raise BudgetLimitExceededError(spent_usd=spent, limit_usd=limit, requested_usd=req)
        return
    wm.check_daily_budget(next_cost_usd=next_cost_usd, cost_limit_usd=cost_limit_usd)


def _record_paid_api_spend(
    project_id: str,
    operation: str,
    estimated_usd: float,
    *,
    model: str = "",
    database: Optional[OmniDatabase] = None,
) -> None:
    try:
        (database or get_db()).record_api_spend(project_id, operation, estimated_usd, model=model)
    except Exception:
        pass


def generate_scene_keyframe_image(
    scene: SceneClipSpec,
    output_png: Path,
    *,
    topic: str,
    niche: str,
    aspect_ratio: str = "16:9",
    cinema_preset: str = DEFAULT_CINEMA_PRESET,
    character_anchor_bytes: Optional[bytes] = None,
    character_bible: str = "",
    use_character_anchor: bool = False,
    project_id: str = "",
    cost_limit_usd: Optional[float] = None,
    config: OmniStudioConfig,
    database: Optional[OmniDatabase] = None,
) -> Tuple[Path, str]:
    """
    Step 1 of the Human-in-the-Loop Image-to-Video (I2V) Pipeline:
    Generates ONE crisp, verified 2D scene keyframe (~$0.05 — 10-15x cheaper than video!)
    using Character Identity Reference Lock + Zero-Camera/Anatomy Negative Blacklist.
    """
    import time as _time
    from worker import BudgetLimitExceededError

    output_png.parent.mkdir(parents=True, exist_ok=True)
    safe_prompt = build_cinematic_video_prompt(
        scene.visual_prompt_veo_omni,
        niche=niche,
        cinema_preset=cinema_preset,
        camera_cue=scene.camera_and_lighting_cue,
        sfx_cue=scene.sfx_cue,
        aspect_ratio=aspect_ratio,
        duration_sec=6.0,
        scene_index=scene.scene_index,
    )
    has_char_ref = bool(use_character_anchor and character_anchor_bytes)
    clean_bible = (character_bible or "").strip()
    char_note = f" Locked character appearance: {clean_bible}." if clean_bible else ""

    kf_prompt = (
        f"{safe_prompt} Photorealistic widescreen theatrical still, completely clean textless photography, "
        f"zero video cameras, zero tripods, zero film crew, zero modern equipment, natural realistic anatomy."
    )
    kf_ref_prompt = (
        "CHARACTER IDENTITY LOCK: Generate a photorealistic 16:9 theatrical movie still featuring the "
        "EXACT SAME person shown in the attached reference portrait — preserve the identical face, eyes, "
        "jawline, age, hair, facial hair, forehead markings/tilak, and traditional attire/colors, placed "
        f"naturally inside the scene below (do NOT copy the plain studio backdrop).{char_note}\n\n{kf_prompt}"
    )

    if not config.has_valid_gemini_key:
        w, h = (1920, 1080) if aspect_ratio == "16:9" else (1080, 1920)
        _render_kinetic_cinematic_plate(output_png, scene=scene, topic=topic, niche=niche, size=(w, h))
        return output_png, "python_studio_plate"

    # Hard Daily Budget Check BEFORE calling image API
    _check_daily_budget_or_raise(0.05, cost_limit_usd=cost_limit_usd, database=database)

    v_creds, v_proj = get_vertex_adc_credentials()
    if v_creds is not None and v_proj:
        for m_kf in ("gemini-3-pro-image", resolve_current_model(IMAGE_CONTINUITY_MODEL, "gemini-nano-banana-2.1")):
            for attempt in range(1, 4):
                try:
                    client = get_genai_client(config.gemini_api_key, location="global")
                    kf_contents: Any = (
                        [
                            genai_types.Part.from_bytes(data=character_anchor_bytes, mime_type="image/png"),
                            kf_ref_prompt,
                        ]
                        if (has_char_ref and character_anchor_bytes)
                        else kf_prompt
                    )
                    resp = client.models.generate_content(
                        model=m_kf,
                        contents=kf_contents,
                        config=genai_types.GenerateContentConfig(
                            response_modalities=["IMAGE"],
                            image_config=genai_types.ImageConfig(aspect_ratio=aspect_ratio),
                        ),
                    )
                    for cand in getattr(resp, "candidates", []) or []:
                        for part in getattr(getattr(cand, "content", None), "parts", []) or []:
                            if getattr(part, "inline_data", None) and part.inline_data.data:
                                output_png.write_bytes(bytes(part.inline_data.data))
                                _record_paid_api_spend(project_id, "scene_keyframe", 0.05, model=m_kf, database=database)
                                ref_suffix = ",ref_lock" if has_char_ref else ""
                                return output_png, f"vertex_keyframe({m_kf}{ref_suffix})"
                except BudgetLimitExceededError:
                    raise
                except Exception as kf_exc:
                    if any(t in str(kf_exc).lower() for t in ("429", "resource_exhausted", "503", "timeout")) and attempt < 3:
                        _time.sleep(3.0 * attempt)
                        continue
                    logger.info("Scene %d keyframe (%s) skipped: %s", scene.scene_index, m_kf, kf_exc)
                    break
    else:
        try:
            client = get_genai_client(config.gemini_api_key)
            if has_char_ref and character_anchor_bytes:
                anchor_b64 = base64.b64encode(character_anchor_bytes).decode("ascii")
                kf_input: Any = [
                    {"type": "image", "data": anchor_b64, "mime_type": "image/png"},
                    {"type": "text", "text": kf_ref_prompt},
                ]
            else:
                kf_input = kf_prompt
            interaction = call_interaction_with_fallback(
                client,
                models=["gemini-3-pro-image", resolve_current_model(IMAGE_CONTINUITY_MODEL, "gemini-nano-banana-2.1")],
                max_retries=3,
                input=kf_input,
                response_format={"type": "image", "aspect_ratio": aspect_ratio, "image_size": "1K"},
            )
            out_img = getattr(interaction, "output_image", None)
            if out_img and getattr(out_img, "data", None):
                raw_img = base64.b64decode(out_img.data) if isinstance(out_img.data, str) else bytes(out_img.data)
                output_png.write_bytes(raw_img)
                _record_paid_api_spend(project_id, "scene_keyframe", 0.05, model="gemini-3-pro-image", database=database)
                ref_suffix = ",ref_lock" if has_char_ref else ""
                return output_png, f"ai_keyframe(gemini-3-pro-image{ref_suffix})"
        except BudgetLimitExceededError:
            raise
        except Exception as exc:
            logger.info("Scene %d AI keyframe fell back to studio plate: %s", scene.scene_index, exc)

    w, h = (1920, 1080) if aspect_ratio == "16:9" else (1080, 1920)
    _render_kinetic_cinematic_plate(output_png, scene=scene, topic=topic, niche=niche, size=(w, h))
    return output_png, "python_studio_plate"


def run_agent3_keyframe_preview_batch(
    project_id: str,
    agent1: Agent1Output,
    agent2: Agent2Output,
    *,
    cinema_preset: str = DEFAULT_CINEMA_PRESET,
    regenerate_existing: bool = False,
    cost_limit_usd: Optional[float] = None,
    config: Optional[OmniStudioConfig] = None,
    db: Optional[OmniDatabase] = None,
) -> Dict[int, str]:
    """
    Generates 2D storyboard preview frames (`clips_16x9/scene_XXX_keyframe.png`) for EVERY scene
    so the user can visually verify faces, anatomy, and zero-camera accuracy BEFORE spending
    credits on Image-to-Video (I2V) animation!
    """
    cfg = config or OmniStudioConfig()
    database = db or get_db()
    slug = sanitize_slug(agent1.topic)
    proj_dir = cfg.projects_dir / f"{project_id}_{slug}"
    clips_16_dir = proj_dir / "clips_16x9"
    renders_dir = proj_dir / "renders"
    clips_16_dir.mkdir(parents=True, exist_ok=True)
    renders_dir.mkdir(parents=True, exist_ok=True)

    scenes = agent2.scenes
    total = len(scenes)
    job_id = f"{project_id}_frame_preview"
    database.upsert_job(
        job_id=job_id,
        project_id=project_id,
        job_type="frame_preview",
        scene_index=0,
        label="2D Frame Preview & Face Lock",
        status="running",
        progress_pct=5,
        message="Locking main character reference portrait...",
    )

    # 1. Generate or reuse Character Reference Portrait (~$0.04 once)
    character_anchor_bytes: Optional[bytes] = None
    effective_bible = (agent1.character_bible or "").strip()
    anchor_file = renders_dir / "character_anchor.png"
    had_anchor = anchor_file.exists() and anchor_file.stat().st_size > 16384
    if cfg.has_valid_gemini_key:
        if not had_anchor:
            _check_daily_budget_or_raise(0.04, cost_limit_usd=cost_limit_usd, database=database)
        anchor_path, effective_bible = _generate_character_anchor_portrait(
            anchor_file,
            agent1=agent1,
            agent2=agent2,
            reuse_existing=not regenerate_existing,
            config=cfg,
        )
        if anchor_path and anchor_path.exists():
            character_anchor_bytes = anchor_path.read_bytes()
            if not had_anchor:
                _record_paid_api_spend(project_id, "character_anchor", 0.04, model="gemini-3-pro-image", database=database)

    char_kws = _extract_character_keywords(effective_bible, agent1.topic) if effective_bible else []
    has_explicit_flags = any(bool(s.features_main_character) for s in scenes)

    results: Dict[int, str] = {}

    def _gen_one(sc: SceneClipSpec) -> Tuple[int, str]:
        if sc.asset_mode == "custom_upload" and sc.custom_asset_path and Path(sc.custom_asset_path).exists():
            return sc.scene_index, "custom_upload"
        kf_path = clips_16_dir / f"scene_{sc.scene_index:03d}_keyframe.png"
        if not regenerate_existing and kf_path.exists() and kf_path.stat().st_size > 16384:
            return sc.scene_index, "cached_keyframe"
        use_char = bool(
            character_anchor_bytes
            and _scene_mentions_character(sc, char_kws, has_explicit_flags=has_explicit_flags)
        )
        _, tag = generate_scene_keyframe_image(
            sc,
            kf_path,
            topic=agent1.topic,
            niche=agent1.niche,
            aspect_ratio="16:9",
            cinema_preset=cinema_preset,
            character_anchor_bytes=character_anchor_bytes,
            character_bible=effective_bible,
            use_character_anchor=use_char,
            project_id=project_id,
            cost_limit_usd=cost_limit_usd,
            config=cfg,
            database=database,
        )
        return sc.scene_index, tag

    done_cnt = 0
    with ThreadPoolExecutor(max_workers=2) as pool:
        futs = [pool.submit(_gen_one, sc) for sc in scenes]
        for fut in as_completed(futs):
            s_idx, tag = fut.result()
            results[s_idx] = tag
            done_cnt += 1
            pct = int((done_cnt / float(max(1, total))) * 100)
            database.upsert_job(
                job_id=job_id,
                project_id=project_id,
                job_type="frame_preview",
                scene_index=0,
                label="2D Frame Preview & Face Lock",
                status="running" if done_cnt < total else "completed",
                progress_pct=pct,
                message=f"Preview frame {done_cnt}/{total} ready ({pct}%)" if done_cnt < total else f"All {total} frames ready for your review ✅",
            )
    return results


def regenerate_single_scene_frame(
    project_id: str,
    agent1: Agent1Output,
    agent2: Agent2Output,
    scene_index: int,
    *,
    cinema_preset: str = DEFAULT_CINEMA_PRESET,
    cost_limit_usd: Optional[float] = None,
    config: Optional[OmniStudioConfig] = None,
    db: Optional[OmniDatabase] = None,
) -> Tuple[Path, str]:
    """Regenerates ONLY one single scene's 2D preview frame (~$0.05 / ₹4) without touching any other scene."""
    cfg = config or OmniStudioConfig()
    database = db or get_db()
    slug = sanitize_slug(agent1.topic)
    proj_dir = cfg.projects_dir / f"{project_id}_{slug}"
    clips_16_dir = proj_dir / "clips_16x9"
    renders_dir = proj_dir / "renders"
    clips_16_dir.mkdir(parents=True, exist_ok=True)

    target_scene = next((s for s in agent2.scenes if s.scene_index == scene_index), None)
    if target_scene is None:
        raise ValueError(f"Scene {scene_index} not found.")

    anchor_path = renders_dir / "character_anchor.png"
    anchor_bytes = anchor_path.read_bytes() if (anchor_path.exists() and anchor_path.stat().st_size > 16384) else None
    effective_bible = (agent1.character_bible or "").strip()
    char_kws = _extract_character_keywords(effective_bible, agent1.topic) if effective_bible else []
    has_explicit = any(bool(s.features_main_character) for s in agent2.scenes)
    use_char = bool(anchor_bytes and _scene_mentions_character(target_scene, char_kws, has_explicit_flags=has_explicit))

    kf_path = clips_16_dir / f"scene_{scene_index:03d}_keyframe.png"
    # Invalidate stale rendered MP4 for this scene so the next build uses this fresh frame!
    stale_mp4 = clips_16_dir / f"scene_{scene_index:03d}_vis.mp4"
    stale_mp4.unlink(missing_ok=True)

    return generate_scene_keyframe_image(
        target_scene,
        kf_path,
        topic=agent1.topic,
        niche=agent1.niche,
        aspect_ratio="16:9",
        cinema_preset=cinema_preset,
        character_anchor_bytes=anchor_bytes,
        character_bible=effective_bible,
        use_character_anchor=use_char,
        project_id=project_id,
        cost_limit_usd=cost_limit_usd,
        config=cfg,
        database=database,
    )


def _generate_ai_scene_visual(
    scene: SceneClipSpec,
    output_mp4: Path,
    *,
    topic: str,
    niche: str,
    duration_sec: float,
    exact_frames: Optional[int] = None,
    aspect_ratio: str,
    render_quality: str,
    force_ai_cinema: bool = True,
    cinema_preset: str = DEFAULT_CINEMA_PRESET,
    foley_out_wav: Optional[Path] = None,
    character_anchor_bytes: Optional[bytes] = None,
    character_bible: str = "",
    use_character_anchor: bool = False,
    approved_keyframe_path: Optional[Path] = None,
    project_id: str = "",
    cost_limit_usd: Optional[float] = None,
    database: Optional[OmniDatabase] = None,
    config: OmniStudioConfig,
) -> Tuple[Path, str]:
    """
    Produces a single scene's visual MP4 clip locked to EXACTLY `exact_frames` frames (0.000ms drift!)
    with True First-Frame Image-to-Video (I2V) from verified keyframes, Character Identity Reference Lock,
    hard Daily Budget Guard before every paid API call, cost-optimized 6s–7s Omni video duration,
    vocal-notched native Foley extraction, ZERO cameras & ZERO foreign glyphs.
    """
    import time as _time
    from worker import BudgetLimitExceededError

    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    w, h = (1920, 1080) if aspect_ratio == "16:9" else (1080, 1920)
    fps = config.fps
    n_frames = int(exact_frames) if (exact_frames and exact_frames > 0) else max(fps * 3, int(round(max(2.5, float(duration_sec)) * fps)))
    dur = n_frames / float(fps)
    output_mp4.parent.mkdir(parents=True, exist_ok=True)

    # Match generated clip duration (`6s`/`7s` for cost-locked Omni video) so prompt text never contradicts response_format!
    prompt_dur = (6.0 if dur <= 9.5 else 7.0) if render_quality == "full_omni_video" else dur
    safe_prompt = build_cinematic_video_prompt(
        scene.visual_prompt_veo_omni,
        niche=niche,
        cinema_preset=cinema_preset,
        camera_cue=scene.camera_and_lighting_cue,
        sfx_cue=scene.sfx_cue,
        aspect_ratio=aspect_ratio,
        duration_sec=prompt_dur,
        scene_index=scene.scene_index,
    )
    has_char_ref = bool(use_character_anchor and character_anchor_bytes)
    clean_bible = (character_bible or "").strip()
    char_note = f" Character specification: {clean_bible}." if clean_bible else ""
    approved_kf_bytes: Optional[bytes] = (
        approved_keyframe_path.read_bytes()
        if (approved_keyframe_path is not None and approved_keyframe_path.exists() and approved_keyframe_path.stat().st_size > 16384)
        else None
    )

    # 1. Custom User Asset Override (Google Flow / User Upload -> $0 AI cost!)
    if scene.custom_asset_path and Path(scene.custom_asset_path).exists():
        custom_p = Path(scene.custom_asset_path)
        if custom_p.suffix.lower() in (".mp4", ".mov", ".mkv", ".webm"):
            if foley_out_wav is not None:
                extract_native_video_foley(custom_p, foley_out_wav, target_duration_sec=dur)
            _normalize_video_clip_exact(custom_p, output_mp4, w=w, h=h, fps=fps, exact_frames=n_frames)
            return output_mp4, "custom_uploaded_video"
        else:
            vf = (
                f"scale={int(w*1.06)}:{int(h*1.06)}:force_original_aspect_ratio=increase,"
                f"crop={w}:{h}:x='(iw-ow)/2+((iw-ow)/4)*sin(2*PI*t/{dur:.4f})':y='(ih-oh)/2',"
                f"setsar=1,setpts=PTS-STARTPTS,fps={fps},format=yuv420p"
            )
            with _FFMPEG_ENCODE_LOCK:
                subprocess.run(
                    [
                        ffmpeg_exe, "-y", "-loop", "1", "-i", str(custom_p),
                        "-vf", vf, "-r", str(fps), "-frames:v", str(n_frames),
                        "-video_track_timescale", "24000", "-bf", "0", "-g", str(fps),
                        "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709",
                        "-an", "-c:v", "libx264", "-preset", "superfast", "-crf", "20",
                        *_LOW_RAM_X264_ARGS,
                        str(output_mp4),
                    ],
                    check=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
            return output_mp4, "custom_uploaded_image"

    # 2. Procedural Motion Graphics (ONLY if explicitly opted in AND `force_ai_cinema=False`)
    if (
        not force_ai_cinema
        and scene.asset_mode == "motion_graphics"
        and scene.motion_graphic_type
        and scene.motion_graphic_type != "none"
    ):
        mg_raw = output_mp4.with_suffix(".mg_raw.mp4")
        render_motion_graphic_clip(
            mg_raw,
            graphic_type=scene.motion_graphic_type,
            title=scene.chapter_label or topic,
            callout=scene.on_screen_callout or scene.voiceover_text[:72],
            niche=niche,
            duration_sec=dur,
            payload=scene.motion_graphic_payload,
            aspect_ratio=aspect_ratio,
            fps=fps,
        )
        _normalize_video_clip_exact(mg_raw, output_mp4, w=w, h=h, fps=fps, exact_frames=n_frames)
        mg_raw.unlink(missing_ok=True)
        return output_mp4, f"procedural_{scene.motion_graphic_type}"

    # 3. Full-Motion AI Video Stack: True First-Frame Image-to-Video (I2V) -> Character R2V -> Veo 3.1 I2V Backup
    if render_quality == "full_omni_video" and config.has_valid_gemini_key:
        # Hard Daily Budget Check BEFORE calling video generation API (~$0.46)
        _check_daily_budget_or_raise(0.46, cost_limit_usd=cost_limit_usd, database=database)

        v_creds, v_proj = get_vertex_adc_credentials()
        omni_dur = 6 if dur <= 9.5 else 7
        omni_resp_fmt = {
            "type": "video",
            "aspect_ratio": aspect_ratio,
            "resolution": "720p",
            "duration": f"{omni_dur}s",
        }

        # 3A. Primary: Gemini Omni 1.2 Flash (Prefers Verified First-Frame I2V when approved keyframe exists!)
        omni_model = resolve_current_model(VIDEO_OMNI_MODEL, "gemini-omni-1.2-flash")
        use_i2v_this_call = approved_kf_bytes is not None
        use_r2v_this_call = (not use_i2v_this_call) and has_char_ref
        for attempt in range(1, 3):
            try:
                client = get_genai_client(config.gemini_api_key, location="global")
                if use_i2v_this_call and approved_kf_bytes:
                    kf_b64 = base64.b64encode(approved_kf_bytes).decode("ascii")
                    omni_i2v_prompt = (
                        f"Use this image as the starting frame. Smoothly animate this exact verified scene as a continuous "
                        f"{omni_dur}-second theatrical shot with natural lifelike motion (gentle breeze, drifting atmospheric "
                        f"dust or incense, flickering firelight, subtle organic character expression, and smooth gliding perspective). "
                        f"Strictly preserve every person's exact face, clothing, animal anatomy, and authentic environment shown in "
                        f"the starting frame with ZERO object mutations, ZERO morphing faces, and ZERO cameras or modern gear.\n\n"
                        f"{safe_prompt}"
                    )
                    omni_input: Any = [
                        {"type": "image", "data": kf_b64, "mime_type": "image/png"},
                        {"type": "text", "text": omni_i2v_prompt},
                    ]
                elif use_r2v_this_call and character_anchor_bytes:
                    anchor_b64 = base64.b64encode(character_anchor_bytes).decode("ascii")
                    omni_ref_prompt = (
                        "CHARACTER IDENTITY LOCK (CRITICAL): Use the provided reference image strictly as the "
                        "exact character identity reference — preserve the EXACT SAME person's face, facial "
                        "structure, eyes, age, hair, facial hair, forehead markings/tilak, and costume colors "
                        "throughout the entire shot. Do NOT use the neutral studio backdrop from the reference "
                        "image as a starting frame; place this exact person naturally inside the cinematic "
                        f"scene described below.{char_note}\n\n{safe_prompt}"
                    )
                    omni_input = [
                        {"type": "image", "data": anchor_b64, "mime_type": "image/png"},
                        {"type": "text", "text": omni_ref_prompt},
                    ]
                else:
                    omni_input = (
                        f"CHARACTER APPEARANCE LOCK:{char_note} {safe_prompt}"
                        if (use_character_anchor and char_note)
                        else safe_prompt
                    )

                interaction = client.interactions.create(
                    model=omni_model,
                    input=omni_input,
                    response_format=omni_resp_fmt,
                )
                out_vid = getattr(interaction, "output_video", None)
                raw_vid: Optional[bytes] = None
                if out_vid and getattr(out_vid, "data", None):
                    raw_vid = base64.b64decode(out_vid.data) if isinstance(out_vid.data, str) else bytes(out_vid.data)
                elif out_vid and getattr(out_vid, "uri", None):
                    raw_vid = bytes(client.files.download(file=out_vid.uri))
                if raw_vid and len(raw_vid) > 16384:
                    _record_paid_api_spend(
                        project_id,
                        "omni_i2v_video" if use_i2v_this_call else "omni_video",
                        0.46,
                        model=omni_model,
                        database=database,
                    )
                    raw_tmp = output_mp4.with_suffix(".omni_raw.mp4")
                    raw_tmp.write_bytes(raw_vid)
                    if foley_out_wav is not None:
                        extract_native_video_foley(raw_tmp, foley_out_wav, target_duration_sec=dur)
                    _normalize_video_clip_exact(raw_tmp, output_mp4, w=w, h=h, fps=fps, exact_frames=n_frames)
                    raw_tmp.unlink(missing_ok=True)
                    mode_tag = ",i2v_verified" if use_i2v_this_call else (",ref_lock" if use_r2v_this_call else "")
                    return output_mp4, f"gemini_omni({omni_model}{mode_tag})"
            except BudgetLimitExceededError:
                raise
            except Exception as exc:
                err_low = str(exc).lower()
                if any(tok in err_low for tok in ("429", "resource_exhausted", "503", "timeout")) and attempt < 2:
                    _time.sleep(4.0 * attempt)
                    continue
                if (use_i2v_this_call or use_r2v_this_call) and attempt < 2:
                    logger.info("Scene %d Omni multimodal retry as text-locked (%s).", scene.scene_index, exc)
                    use_i2v_this_call = False
                    use_r2v_this_call = False
                    continue
                logger.info("Scene %d Omni 1.2 Flash skipped (%s); trying Vertex Veo 3.1.", scene.scene_index, exc)
                break

        # 3B. Secondary Full-Motion Video: Vertex AI `veo-3.1-generate-001` (supports native I2V image input + negative_prompt!)
        if v_creds is not None and v_proj:
            veo_prompt = (
                f"CHARACTER APPEARANCE LOCK:{char_note} {safe_prompt}"
                if (use_character_anchor and char_note)
                else safe_prompt
            )
            for attempt in range(1, 3):
                try:
                    v_us = get_genai_client(config.gemini_api_key, location="us-central1")
                    veo_dur = 6
                    veo_source = (
                        genai_types.GenerateVideosSource(
                            prompt=veo_prompt,
                            image=genai_types.Image(image_bytes=approved_kf_bytes, mime_type="image/png"),
                        )
                        if approved_kf_bytes
                        else genai_types.GenerateVideosSource(prompt=veo_prompt)
                    )
                    op = v_us.models.generate_videos(
                        model=VERTEX_VEO_MODEL,
                        source=veo_source,
                        config=genai_types.GenerateVideosConfig(
                            aspect_ratio=aspect_ratio,
                            duration_seconds=veo_dur,
                            negative_prompt=VEO_STRICT_NEGATIVE_PROMPT,
                        ),
                    )
                    deadline = _time.time() + 180.0
                    while not getattr(op, "done", False) and _time.time() < deadline:
                        _time.sleep(6.0)
                        op = v_us.operations.get(op)
                    gen_vids = getattr(getattr(op, "response", None), "generated_videos", None) or []
                    if gen_vids and getattr(gen_vids[0], "video", None) and getattr(gen_vids[0].video, "video_bytes", None):
                        _record_paid_api_spend(project_id, "veo_i2v_video" if approved_kf_bytes else "veo_video", 0.46, model=VERTEX_VEO_MODEL, database=database)
                        raw_tmp = output_mp4.with_suffix(".veo_raw.mp4")
                        raw_tmp.write_bytes(gen_vids[0].video.video_bytes)
                        if foley_out_wav is not None:
                            extract_native_video_foley(raw_tmp, foley_out_wav, target_duration_sec=dur)
                        _normalize_video_clip_exact(raw_tmp, output_mp4, w=w, h=h, fps=fps, exact_frames=n_frames)
                        raw_tmp.unlink(missing_ok=True)
                        return output_mp4, f"vertex_veo({VERTEX_VEO_MODEL}{',i2v' if approved_kf_bytes else ''})"
                except BudgetLimitExceededError:
                    raise
                except Exception as exc:
                    err_low = str(exc).lower()
                    if any(tok in err_low for tok in ("429", "resource_exhausted", "quota", "503")) and attempt < 2:
                        _time.sleep(8.0 * attempt)
                        continue
                    logger.info("Scene %d Vertex Veo 3.1 skipped (%s); falling back to AI keyframe.", scene.scene_index, exc)
                    break

    # 4. Photorealistic AI Keyframe Visual (REUSES user-approved preview frame at $0.00 extra cost if present!)
    frame_png = output_mp4.with_suffix(".png")
    source_tag = "python_studio_plate"
    if approved_kf_bytes is not None and approved_keyframe_path is not None:
        frame_png = approved_keyframe_path
        source_tag = "verified_keyframe(reused)"
    elif render_quality in ("full_omni_video", "ai_keyframes_kenburns") and config.has_valid_gemini_key:
        frame_png, source_tag = generate_scene_keyframe_image(
            scene,
            frame_png,
            topic=topic,
            niche=niche,
            aspect_ratio=aspect_ratio,
            cinema_preset=cinema_preset,
            character_anchor_bytes=character_anchor_bytes,
            character_bible=character_bible,
            use_character_anchor=use_character_anchor,
            project_id=project_id,
            cost_limit_usd=cost_limit_usd,
            config=config,
            database=database,
        )

    if not frame_png.exists():
        _render_kinetic_cinematic_plate(frame_png, scene=scene, topic=topic, niche=niche, size=(w, h))

    # Animate smooth broadcast Ken-Burns drift locked to EXACT `n_frames` (zero drift, zero B-frame bleed!)
    vf = (
        f"scale={int(w * 1.05)}:{int(h * 1.05)}:force_original_aspect_ratio=increase,"
        f"crop={w}:{h}:x='(iw-ow)/2+((iw-ow)/4)*sin(2*PI*t/{dur:.4f})':y='(ih-oh)/2+((ih-oh)/4)*cos(2*PI*t/{dur:.4f})',"
        f"setsar=1,setpts=PTS-STARTPTS,fps={fps},format=yuv420p"
    )
    with _FFMPEG_ENCODE_LOCK:
        subprocess.run(
            [
                ffmpeg_exe, "-y",
                "-loop", "1", "-i", str(frame_png),
                "-vf", vf,
                "-r", str(fps),
                "-frames:v", str(n_frames),
                "-video_track_timescale", "24000",
                "-bf", "0", "-g", str(fps),
                "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709",
                "-an",
                "-c:v", "libx264", "-preset", "superfast", "-crf", "20",
                *_LOW_RAM_X264_ARGS,
                str(output_mp4),
            ],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    return output_mp4, source_tag


def _ffmpeg_ass_filter_escape(ass_path: Path) -> str:
    """Safely escapes Windows drive letters and backslashes for FFmpeg's `ass=` filter."""
    posix = ass_path.resolve().as_posix()
    return posix.replace(":", "\\:").replace("'", "\\'")


def _create_circular_host_pip_png(
    portrait_path: Path,
    output_png: Path,
    *,
    diameter: int = 230,
    accent_rgb: Tuple[int, int, int] = (0, 229, 255),
) -> Optional[Path]:
    """Creates a clean glowing circular host presenter badge PNG for optional video PIP overlay."""
    if not portrait_path.exists():
        return None
    pad = 16
    size = diameter + pad * 2
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas, "RGBA")

    # Outer glowing ring
    draw.ellipse([4, 4, size - 4, size - 4], fill=(*accent_rgb, 65), outline=(*accent_rgb, 245), width=6)

    # Circular cropped portrait
    src = Image.open(portrait_path).convert("RGBA")
    side = min(src.width, src.height)
    left = (src.width - side) // 2
    top = max(0, int((src.height - side) * 0.15))
    cropped = src.crop((left, top, left + side, top + side)).resize((diameter, diameter), Image.Resampling.LANCZOS)

    mask = Image.new("L", (diameter, diameter), 0)
    ImageDraw.Draw(mask).ellipse([0, 0, diameter, diameter], fill=255)
    canvas.paste(cropped, (pad, pad), mask)

    output_png.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output_png, format="PNG")
    return output_png


def _overlay_host_pip_on_clip(
    input_mp4: Path,
    pip_png: Path,
    output_mp4: Path,
    *,
    fps: int = 24,
    exact_frames: Optional[int] = None,
) -> Path:
    """Overlays the optional circular host PIP cleanly while preserving exact frame count & closed GOP."""
    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    cmd = [
        ffmpeg_exe, "-y",
        "-i", str(input_mp4),
        "-i", str(pip_png),
        "-filter_complex", f"[0:v][1:v]overlay=44:H-h-180,setpts=PTS-STARTPTS,fps={fps},format=yuv420p[outv]",
        "-map", "[outv]",
        "-r", str(fps),
        "-video_track_timescale", "24000",
        "-bf", "0", "-g", str(fps),
        "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709",
        "-an",
        "-c:v", "libx264", "-preset", "superfast", "-crf", "20",
        *_LOW_RAM_X264_ARGS,
    ]
    if exact_frames and exact_frames > 0:
        cmd.extend(["-frames:v", str(exact_frames)])
    cmd.append(str(output_mp4))
    with _FFMPEG_ENCODE_LOCK:
        subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return output_mp4


def _mux_continuous_audio_and_burn_ass(
    concat_txt_or_video: Path,
    continuous_master_wav: Path,
    ass_path: Path,
    output_mp4: Path,
    *,
    fps: int = 24,
    is_concat_list: bool = True,
) -> Path:
    """
    Single-pass frame-exact broadcast stitch & mux (ZERO `-c:v copy` overlap or drift!):
    - Decodes the frame-locked concat list directly into ONE continuous CFR `fps` H.264 stream
    - Burns word-level active-highlight `.ass` subtitles (with bundled Devanagari fontsdir)
    - Muxes ONE continuous 44.1kHz STEREO AAC-LC (`192k`) audio stream with `-movflags +faststart`.
    """
    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    escaped_ass = _ffmpeg_ass_filter_escape(ass_path)
    fonts_dir = Path("assets/fonts")
    ass_filter = (
        f"ass='{escaped_ass}':fontsdir='{_ffmpeg_ass_filter_escape(fonts_dir)}'"
        if fonts_dir.exists()
        else f"ass='{escaped_ass}'"
    )
    vf_str = f"fps={fps},{ass_filter},format=yuv420p"
    vid_in_args = (
        ["-f", "concat", "-safe", "0", "-i", str(concat_txt_or_video)]
        if is_concat_list
        else ["-i", str(concat_txt_or_video)]
    )
    try:
        with _FFMPEG_ENCODE_LOCK:
            subprocess.run(
                [
                    ffmpeg_exe, "-y",
                    *vid_in_args,
                    "-i", str(continuous_master_wav),
                    "-map", "0:v:0", "-map", "1:a:0",
                    "-vf", vf_str,
                    "-r", str(fps),
                    "-c:v", "libx264", "-preset", "superfast", "-crf", "21", "-pix_fmt", "yuv420p",
                    *_LOW_RAM_X264_ARGS,
                    "-c:a", "aac", "-ar", "44100", "-ac", "2", "-b:a", "192k",
                    "-max_muxing_queue_size", "512",
                    "-movflags", "+faststart",
                    "-shortest",
                    str(output_mp4),
                ],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        if output_mp4.exists() and output_mp4.stat().st_size > 4096:
            return output_mp4
    except subprocess.CalledProcessError as exc:
        err_tail = (exc.stderr or b"").decode("utf-8", errors="ignore")[-320:]
        logger.warning("FFmpeg ASS burn pass failed (%s); stitching clean CFR video + stereo audio without ASS.", err_tail)
    except Exception as exc:
        logger.warning("FFmpeg ASS burn pass failed (%s); stitching clean CFR video + stereo audio without ASS.", exc)

    # Guaranteed FFmpeg 4.x-9.x compatible fallback WITH clean CFR re-encode & full 44.1kHz stereo audio
    with _FFMPEG_ENCODE_LOCK:
        res = subprocess.run(
            [
                ffmpeg_exe, "-y",
                *vid_in_args,
                "-i", str(continuous_master_wav),
                "-map", "0:v:0", "-map", "1:a:0",
                "-vf", f"fps={fps},format=yuv420p",
                "-r", str(fps),
                "-c:v", "libx264", "-preset", "superfast", "-crf", "21", "-pix_fmt", "yuv420p",
                *_LOW_RAM_X264_ARGS,
                "-c:a", "aac", "-ar", "44100", "-ac", "2", "-b:a", "192k",
                "-max_muxing_queue_size", "512",
                "-movflags", "+faststart",
                "-shortest",
                str(output_mp4),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    if res.returncode != 0:
        err_msg = (res.stderr or b"").decode("utf-8", errors="ignore")[-450:]
        raise RuntimeError(f"FFmpeg final stitch failed (exit {res.returncode}): {err_msg}")
    return output_mp4


def select_hybrid_hero_scene_indices(scenes: List[SceneClipSpec]) -> set:
    """
    Selects the high-impact Hero scenes (~25% of scenes) for full-motion AI video (`gemini-omni-1.2-flash`)
    in `hybrid_cinema` mode while rendering supporting scenes with ultra-crisp AI cinema visuals + 24fps motion
    (~70% cheaper than rendering every single scene with Omni video!).
    Always prioritizes: Opening Hook (first 2 scenes), Climax Reveal (first 2 scenes), Final Outro,
    plus evenly spaced body hero shots every 5th scene.
    """
    if not scenes:
        return set()
    hero: set = set()
    hooks = [s.scene_index for s in scenes if s.beat_phase == "Visual_Hook_0_45s"]
    climaxes = [s.scene_index for s in scenes if s.beat_phase == "Climax_Aha"]
    hero.update(hooks[:2] if hooks else [scenes[0].scene_index])
    hero.update(climaxes[:2])
    hero.add(scenes[-1].scene_index)
    # Sprinkle full-motion hero shots roughly every 5 scenes across the middle body
    for idx, sc in enumerate(scenes):
        if idx > 0 and idx % 5 == 0:
            hero.add(sc.scene_index)
    return hero


def estimate_render_cost_usd(
    scenes: List[SceneClipSpec],
    render_quality: str,
    *,
    cached_scene_count: int = 0,
    use_fast_tts: bool = False,
    approved_keyframe_indices: Optional[set] = None,
    animate_scene_indices: Optional[set] = None,
) -> Dict[str, Any]:
    """
    Computes a transparent pre-render Vertex AI credit estimate (USD) before the user clicks Generate:
    - Custom/Google Flow uploaded clips (`asset_mode == 'custom_upload'` with file attached): $0.00!
    - Already-verified 2D preview keyframes (`approved_keyframe_indices`): $0.00 extra when reused for motion visuals!
    - `gemini-omni-1.2-flash` I2V (720p cost-locked 6s-7s clip): ~$0.46/scene (~35% cheaper than 10s default!)
    - `gemini-3-pro-image` cinema keyframe + 24fps motion: ~$0.05/scene
    - Voiceover + Thumbnail + Character Reference Portrait ($0.04 if not yet created) + Lyria-002 music: ~$0.26 (or ~$0.10 quick voice)
    """
    total = len(scenes)
    approved_kfs = approved_keyframe_indices or set()
    custom_scenes = [
        s for s in scenes
        if s.asset_mode == "custom_upload" and bool((s.custom_asset_path or "").strip())
    ]
    custom_cnt = len(custom_scenes)
    ai_eligible_scenes = [
        s for s in scenes
        if not (s.asset_mode == "custom_upload" and bool((s.custom_asset_path or "").strip()))
    ]
    remaining = max(0, len(ai_eligible_scenes) - max(0, int(cached_scene_count)))
    omni_clip_usd = 0.46
    kf_clip_usd = 0.05
    missing_kf_count = sum(1 for s in ai_eligible_scenes if s.scene_index not in approved_kfs)
    preview_frames_usd = round((missing_kf_count * kf_clip_usd) + (0.04 if (missing_kf_count > 0 and not approved_kfs) else 0.0), 2)
    anchor_usd = 0.04 if (remaining > 0 and not approved_kfs and render_quality != "fast_studio_preview") else 0.0
    base_overhead = (0.06 if use_fast_tts else 0.22) + anchor_usd
    full_motion_ref = round(len(ai_eligible_scenes) * omni_clip_usd + (0.06 if use_fast_tts else 0.22) + (0.04 if ai_eligible_scenes else 0.0), 2)

    if remaining == 0:
        return {
            "total_usd": round(base_overhead, 2),
            "video_scenes": 0,
            "keyframe_scenes": 0,
            "reused_keyframes": 0,
            "custom_scenes": custom_cnt,
            "reused_scenes": total - custom_cnt,
            "preview_frames_usd": preview_frames_usd,
            "full_motion_usd": full_motion_ref,
        }

    if render_quality == "fast_studio_preview":
        return {
            "total_usd": 0.0,
            "video_scenes": 0,
            "keyframe_scenes": 0,
            "reused_keyframes": 0,
            "custom_scenes": custom_cnt,
            "reused_scenes": max(0, len(ai_eligible_scenes) - remaining),
            "preview_frames_usd": 0.0,
            "full_motion_usd": full_motion_ref,
        }

    # Resolve exact set of scenes slated for I2V full-motion video vs 2D keyframe motion
    if animate_scene_indices is not None:
        anim_ids = {s.scene_index for s in ai_eligible_scenes if s.scene_index in animate_scene_indices}
    elif render_quality == "ai_keyframes_kenburns":
        anim_ids = set()
    elif render_quality == "hybrid_cinema":
        hero_ids = select_hybrid_hero_scene_indices(scenes)
        anim_ids = {s.scene_index for s in ai_eligible_scenes if s.scene_index in hero_ids}
    else:
        anim_ids = {s.scene_index for s in ai_eligible_scenes}

    non_anim_scenes = [s for s in ai_eligible_scenes if s.scene_index not in anim_ids]
    reused_kf_cnt = sum(1 for s in non_anim_scenes if s.scene_index in approved_kfs)
    new_kf_cnt = max(0, len(non_anim_scenes) - reused_kf_cnt)
    hero_cnt = min(remaining, len(anim_ids))
    # Cap new keyframes if some scenes are already cached
    new_kf_cnt = min(max(0, remaining - hero_cnt), new_kf_cnt)
    est = hero_cnt * omni_clip_usd + new_kf_cnt * kf_clip_usd + base_overhead
    return {
        "total_usd": round(est, 2),
        "video_scenes": hero_cnt,
        "keyframe_scenes": new_kf_cnt,
        "reused_keyframes": reused_kf_cnt,
        "custom_scenes": custom_cnt,
        "reused_scenes": max(0, len(ai_eligible_scenes) - remaining),
        "preview_frames_usd": preview_frames_usd,
        "full_motion_usd": full_motion_ref,
    }


def _resolve_short_hook_script(
    agent1: Agent1Output,
    agent2: Agent2Output,
    config: OmniStudioConfig,
) -> str:
    """
    Produces a high-retention 26–38 word (11–18s) curiosity/fear/shock cliffhanger hook script
    tailored to the video's topic and language to drive Shorts viewers directly to the full video!
    """
    existing = (agent1.short_hook_script or "").strip()
    if len(existing.split()) >= 14:
        return existing

    lang_low = (agent1.language_tone or "").lower()
    is_hinglish = "hinglish" in lang_low
    is_hindi = "hindi" in lang_low and not is_hinglish

    if config.has_valid_gemini_key:
        try:
            client = get_genai_client(config.gemini_api_key, location="global")
            prompt = (
                f"Write ONE razor-sharp, scroll-stopping YouTube Shorts narration hook (strictly 26 to 36 words, "
                f"~12 to 17 seconds spoken aloud) in {agent1.language_tone} for the video '{agent1.topic}'.\n"
                f"Story hook context: {agent1.hook_script_0_45s[:220]}\n"
                f"Climax twist context: {agent1.climax_misconception_aha[:220]}\n\n"
                f"RULES:\n"
                f"- Open immediately with a provocative question, hidden fear, shocking warning, or intense mystery.\n"
                f"- Do NOT reveal the final answer — create a powerful cliffhanger.\n"
                f"- End with a crisp 1-line CTA telling viewers to tap the full video link in the description right now.\n"
                f"- Return ONLY the plain spoken narration text (no quotes, no labels, no stage directions, no markdown)."
            )
            inter = call_interaction_with_fallback(
                client,
                models=[resolve_current_model(FAST_AGENT_MODEL, "gemini-3.8-flash")],
                max_retries=1,
                input=prompt,
            )
            raw = (getattr(inter, "output_text", None) or "").strip().strip('"').strip("'")
            if 14 <= len(raw.split()) <= 52:
                return raw
        except Exception as exc:
            logger.info("Auto Short hook generation fell back to template: %s", exc)

    if is_hinglish:
        return (
            f"Ek second ruko! Kya aapko pata hai ki {agent1.topic} ke peeche ek aisa shocking sach chhupa hai "
            f"jo 99% log miss kar dete hain? Asli raaz jaankar aap chaunk jaoge — "
            f"poora video dekhne ke liye abhi description wale link par click karo!"
        )
    if is_hindi:
        return (
            f"एक सेकंड रुकिए! क्या आप जानते हैं कि {agent1.topic} के पीछे एक ऐसा चौंकाने वाला रहस्य छिपा है "
            f"जिसे 99% लोग आज तक नहीं जानते? सच्चाई जानकर आपके होश उड़ जाएंगे — "
            f"पूरा वीडियो देखने के लिए अभी डिस्क्रिप्शन में दिए लिंक पर क्लिक करें!"
        )
    return (
        f"Stop scrolling! Almost everyone misses the shocking hidden truth behind {agent1.topic} — "
        f"and what really happened will give you chills. Don't stay in the dark: "
        f"tap the full video link in the description right now!"
    )


def _fit_wav_to_max_duration(src_wav: Path, dst_wav: Path, *, max_sec: float = 19.2) -> Tuple[Path, float]:
    """
    If a synthesized Shorts hook voiceover slightly exceeds `max_sec` (e.g. 21s–25s), gently accelerates
    tempo (<=1.4x, pitch-preserving FFmpeg `atempo`) and caps strictly below 20s so the Short ALWAYS stays
    inside the crisp 10s–20s window!
    """
    import wave as _wave

    with _wave.open(str(src_wav), "rb") as wf:
        raw_dur = wf.getnframes() / float(wf.getframerate() or 24000)

    if raw_dur <= max_sec:
        return src_wav, raw_dur

    tempo = min(1.42, max(1.02, raw_dur / (max_sec - 0.35)))
    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    subprocess.run(
        [
            ffmpeg_exe, "-y",
            "-i", str(src_wav),
            "-af", f"atempo={tempo:.4f},atrim=0:{max_sec:.3f}",
            "-ar", "24000", "-ac", "1", "-c:a", "pcm_s16le",
            str(dst_wav),
        ],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    with _wave.open(str(dst_wav), "rb") as wf:
        new_dur = wf.getnframes() / float(wf.getframerate() or 24000)
    return dst_wav, new_dur


def run_agent3_media_pipeline(
    project_id: str,
    agent1: Agent1Output,
    agent2: Agent2Output,
    *,
    render_quality: str = "full_omni_video",
    force_ai_cinema: bool = True,
    cinema_preset: str = DEFAULT_CINEMA_PRESET,
    bgm_preset: str = DEFAULT_BGM_PRESET,
    custom_bgm_path: Optional[str] = None,
    bgm_duck_db: Optional[float] = None,
    enable_foley_sfx: bool = True,
    reuse_existing_clips: bool = False,
    include_avatar_in_thumbnail: bool = False,
    avatar_thumbnail_mode: str = "real_photo",
    include_avatar_in_video: bool = False,
    creator_side: str = "left",
    prefer_fast_local_tts: bool = False,
    use_ai_thumbnail: bool = True,
    animate_scene_indices: Optional[set] = None,
    cost_limit_usd: Optional[float] = None,
    sewn_master_video_path: Optional[str] = None,
    custom_thumbnail_16x9_path: Optional[str] = None,
    custom_thumbnail_9x16_path: Optional[str] = None,
    config: Optional[OmniStudioConfig] = None,
    db: Optional[OmniDatabase] = None,
) -> Agent3Output:
    """
    Executes Agent 3 (Media Generator & Composer Agent) end-to-end with SQLite real-time job tracking.
    """
    cfg = config or OmniStudioConfig()
    database = db or get_db()
    slug = sanitize_slug(agent1.topic)
    proj_dir = cfg.projects_dir / f"{project_id}_{slug}"
    audio_dir = proj_dir / "audio"
    clips_16_dir = proj_dir / "clips_16x9"
    clips_9_dir = proj_dir / "clips_9x16"
    renders_dir = proj_dir / "renders"
    for d in (audio_dir, clips_16_dir, clips_9_dir, renders_dir):
        d.mkdir(parents=True, exist_ok=True)

    # Clean stale per-scene intermediate renders/Foley on fresh renders; keep them when resuming a stitch!
    if not reuse_existing_clips:
        for stale_pat in ("scene_*_foley_*.wav", "scene_*_master.wav"):
            for fp in audio_dir.glob(stale_pat):
                fp.unlink(missing_ok=True)
        for fp in clips_16_dir.glob("scene_*_vis*.mp4"):
            fp.unlink(missing_ok=True)
    else:
        for fp in audio_dir.glob("scene_*_master.wav"):
            fp.unlink(missing_ok=True)
    for fp in clips_9_dir.glob("short_vid_*.mp4"):
        fp.unlink(missing_ok=True)

    scenes = agent2.scenes
    total_scenes = len(scenes)

    database.clear_project_jobs(project_id, job_type="media_stage")
    # Seed stage trackers so UI shows clean, readable progress immediately
    stage_defs = [
        ("voiceover", "1. Voiceover Narration"),
        ("thumbnail", "2. Video Thumbnail"),
        ("visuals_16x9", "3. AI Cinema Scenes"),
        ("bgm_mix", "4. Background Music & Sound Effects"),
        ("assemble_16x9", "5. Full HD Video & Subtitles"),
        ("assemble_9x16", "6. Vertical Shorts Cutdown"),
    ]
    for idx, (skey, slabel) in enumerate(stage_defs, start=1):
        database.upsert_job(
            job_id=f"{project_id}_{skey}",
            project_id=project_id,
            job_type="media_stage",
            scene_index=idx,
            label=slabel,
            status="queued",
            progress_pct=0,
            message="Queued",
        )

    # ------------------------------------------------------------------
    # STAGE 1: Voiceover Synthesis (Parallelized) + Exact Duration Anchor
    # ------------------------------------------------------------------
    database.upsert_job(
        job_id=f"{project_id}_voiceover",
        project_id=project_id,
        job_type="media_stage",
        scene_index=1,
        label=stage_defs[0][1],
        status="running",
        progress_pct=5,
        message=f"Recording narration (0/{total_scenes} scenes)...",
    )
    voice_results: Dict[int, Tuple[Path, float, str]] = {}

    # Quantize every scene to an EXACT integer frame count (`24000 Hz / 24 fps = 1000 samples/frame EXACTLY`)!
    # Eliminates cumulative floating-point A/V drift & visual/audio overlap across 30-50+ stitched scenes.
    scene_frame_counts: Dict[int, int] = {}

    def _synth_one(sc: SceneClipSpec) -> Tuple[int, Path, float, int, str]:
        wav_p = audio_dir / f"scene_{sc.scene_index:03d}_voice.wav"
        p, dur, eng = synthesize_scene_voiceover(
            sc.voiceover_text,
            sc.ssml_voice_cues,
            wav_p,
            language_tone=agent1.language_tone,
            target_duration_sec=sc.duration_sec,
            config=cfg,
            prefer_fast_local_tts=prefer_fast_local_tts,
        )
        n_frames = max(cfg.fps * 3, int(math.ceil((dur + 0.35) * cfg.fps)))
        exact_dur = n_frames / float(cfg.fps)
        return sc.scene_index, p, exact_dur, n_frames, eng

    with ThreadPoolExecutor(max_workers=2) as pool:
        futs = [pool.submit(_synth_one, sc) for sc in scenes]
        done_cnt = 0
        for fut in as_completed(futs):
            s_idx, wav_p, exact_dur, n_frames, eng = fut.result()
            voice_results[s_idx] = (wav_p, exact_dur, eng)
            scene_frame_counts[s_idx] = n_frames
            done_cnt += 1
            pct = int((done_cnt / float(total_scenes)) * 100)
            database.upsert_job(
                job_id=f"{project_id}_voiceover",
                project_id=project_id,
                job_type="media_stage",
                scene_index=1,
                label=stage_defs[0][1],
                status="running" if done_cnt < total_scenes else "completed",
                progress_pct=pct,
                message=f"{done_cnt}/{total_scenes} voiceovers ready ({pct}%)" if done_cnt < total_scenes else f"{total_scenes} voiceovers ready",
            )

    # Exact global offsets & YouTube Chapters derived from exact quantized frame counts (0.000ms drift!)
    scene_offsets: Dict[int, float] = {}
    cum_frames = 0
    chapter_seen: List[str] = []
    exact_chapter_lines: List[str] = []
    for sc in scenes:
        offset_sec = cum_frames / float(cfg.fps)
        scene_offsets[sc.scene_index] = offset_sec
        lbl = (sc.chapter_label or sc.beat_phase.replace("_", " ")).strip()
        if lbl and lbl not in chapter_seen:
            chapter_seen.append(lbl)
            exact_chapter_lines.append(f"{format_timestamp(offset_sec)} - {lbl}")
        cum_frames += scene_frame_counts[sc.scene_index]
    total_actual_duration = round(cum_frames / float(cfg.fps), 2)
    exact_chapters_text = "\n".join(exact_chapter_lines)

    # ------------------------------------------------------------------
    # STAGE 2: High-CTR Likeness-Locked Thumbnail (@jwalashiva)
    # ------------------------------------------------------------------
    database.upsert_job(
        job_id=f"{project_id}_thumbnail",
        project_id=project_id,
        job_type="media_stage",
        scene_index=2,
        label=stage_defs[1][1],
        status="running",
        progress_pct=25,
        message="Designing video thumbnail...",
    )
    thumb_path = renders_dir / "thumbnail_16x9.png"
    thumb_9x16_path_str = ""
    custom_t16 = Path(custom_thumbnail_16x9_path) if custom_thumbnail_16x9_path else None
    custom_t9 = Path(custom_thumbnail_9x16_path) if custom_thumbnail_9x16_path else None

    if custom_t16 and custom_t16.exists() and custom_t16.stat().st_size > 2048:
        try:
            with Image.open(custom_t16) as im_t16:
                im_t16.convert("RGB").save(thumb_path, format="PNG")
            thumb_engine = "custom_flow_thumbnail_16x9"
        except Exception:
            thumb_path.write_bytes(custom_t16.read_bytes())
            thumb_engine = "custom_flow_thumbnail_16x9"
    elif reuse_existing_clips and thumb_path.exists() and thumb_path.stat().st_size > 16384:
        thumb_engine = "cached_thumbnail"
    else:
        thumb_path, thumb_engine = generate_high_ctr_thumbnail(
            thumb_path,
            topic=agent1.topic,
            niche=agent1.niche,
            headline=agent1.thumbnail_hook_headline,
            badge_label=agent1.thumbnail_badge_label,
            graphic_concept=agent1.thumbnail_graphic_concept,
            include_creator_avatar=include_avatar_in_thumbnail,
            avatar_mode=avatar_thumbnail_mode,
            creator_side=creator_side,
            config=cfg,
            use_ai_image_api=use_ai_thumbnail,
        )

    if custom_t9 and custom_t9.exists() and custom_t9.stat().st_size > 2048:
        t9_dest = renders_dir / "thumbnail_9x16_short.png"
        try:
            with Image.open(custom_t9) as im_t9:
                im_t9.convert("RGB").save(t9_dest, format="PNG")
        except Exception:
            t9_dest.write_bytes(custom_t9.read_bytes())
        thumb_9x16_path_str = str(t9_dest)
    elif (renders_dir / "thumbnail_9x16_short.png").exists() and (renders_dir / "thumbnail_9x16_short.png").stat().st_size > 2048:
        thumb_9x16_path_str = str(renders_dir / "thumbnail_9x16_short.png")

    database.upsert_job(
        job_id=f"{project_id}_thumbnail",
        project_id=project_id,
        job_type="media_stage",
        scene_index=2,
        label=stage_defs[1][1],
        status="completed",
        progress_pct=100,
        message="Custom Flow 16:9 + 9:16 thumbnails ready" if (thumb_engine.startswith("custom_flow") and thumb_9x16_path_str) else "Thumbnail ready",
        output_path=str(thumb_path),
    )

    # ------------------------------------------------------------------
    # STAGE 3: Visual Generation & Procedural Motion Graphics (16:9)
    # ------------------------------------------------------------------
    sewn_p = Path(sewn_master_video_path) if sewn_master_video_path else None
    using_sewn_master = bool(sewn_p and sewn_p.exists() and sewn_p.stat().st_size > 16384)
    sewn_total_dur = _probe_video_duration_sec(sewn_p) if (using_sewn_master and sewn_p is not None) else 0.0
    if using_sewn_master and sewn_total_dur < 2.0:
        using_sewn_master = False

    database.upsert_job(
        job_id=f"{project_id}_visuals_16x9",
        project_id=project_id,
        job_type="media_stage",
        scene_index=3,
        label=stage_defs[2][1],
        status="running",
        progress_pct=5,
        message=f"Aligning sewn Google Flow video across {total_scenes} scenes..." if using_sewn_master else f"Creating scenes (0/{total_scenes})...",
    )
    visual_results: Dict[int, Tuple[Path, str]] = {}

    # Optional circular host PIP avatar overlay (only when user opted-in via `include_avatar_in_video=True`)
    host_pip_png: Optional[Path] = None
    if include_avatar_in_video:
        studio_portrait = cfg.likeness_dir / "image_13.png"
        if not studio_portrait.exists() and cfg.likeness_reference_paths:
            studio_portrait = cfg.likeness_reference_paths[0]
        if studio_portrait.exists():
            prof = get_niche_profile(agent1.niche)
            host_pip_png = _create_circular_host_pip_png(
                studio_portrait,
                renders_dir / "host_pip_badge.png",
                diameter=220,
                accent_rgb=_hex_to_rgb(prof["accent_hex"]),
            )

    hybrid_hero_ids = select_hybrid_hero_scene_indices(scenes) if render_quality == "hybrid_cinema" else set()

    # Character Identity Lock: Generate ONE Master Reference Portrait (~$0.04) once per project
    # (skipped if using sewn Flow master video, all custom uploads, or fast draft preview — zero wasted credits!)
    character_anchor_bytes: Optional[bytes] = None
    effective_character_bible: str = (agent1.character_bible or "").strip()
    character_keywords: List[str] = []
    has_explicit_char_flags = any(bool(s.features_main_character) for s in scenes)
    needs_ai_visuals = (not using_sewn_master) and any(
        not (s.custom_asset_path and Path(s.custom_asset_path).exists())
        for s in scenes
    )
    if render_quality != "fast_studio_preview" and needs_ai_visuals and cfg.has_valid_gemini_key:
        database.upsert_job(
            job_id=f"{project_id}_visuals_16x9",
            project_id=project_id,
            job_type="media_stage",
            scene_index=3,
            label=stage_defs[2][1],
            status="running",
            progress_pct=6,
            message="Locking main character appearance across scenes...",
        )
        anchor_file = renders_dir / "character_anchor.png"
        had_anchor = anchor_file.exists() and anchor_file.stat().st_size > 16384
        if not had_anchor:
            _check_daily_budget_or_raise(0.04, cost_limit_usd=cost_limit_usd, database=database)
        anchor_path, effective_character_bible = _generate_character_anchor_portrait(
            anchor_file,
            agent1=agent1,
            agent2=agent2,
            reuse_existing=True,
            config=cfg,
        )
        if anchor_path and anchor_path.exists():
            character_anchor_bytes = anchor_path.read_bytes()
            if not had_anchor:
                _record_paid_api_spend(project_id, "character_anchor", 0.04, model="gemini-3-pro-image", database=database)
        if effective_character_bible:
            character_keywords = _extract_character_keywords(effective_character_bible, agent1.topic)

    def _render_vis(sc: SceneClipSpec) -> Tuple[int, Path, str]:
        dur = voice_results[sc.scene_index][1]
        n_frames = scene_frame_counts[sc.scene_index]
        out_mp4 = clips_16_dir / f"scene_{sc.scene_index:03d}_vis.mp4"
        approved_kf = clips_16_dir / f"scene_{sc.scene_index:03d}_keyframe.png"
        foley_wav = (audio_dir / f"scene_{sc.scene_index:03d}_foley_native.wav") if enable_foley_sfx else None
        if using_sewn_master and sewn_p is not None and not (sc.custom_asset_path and Path(sc.custom_asset_path).exists()):
            # Single-pass proportional slice directly from the sewn Google Flow master video (ZERO double-encode, ZERO drift!)
            seg_len = sewn_total_dur / float(max(1, total_scenes))
            seg_start = max(0.0, (sc.scene_index - 1) * seg_len)
            if foley_wav is not None:
                extract_native_video_foley(
                    sewn_p,
                    foley_wav,
                    target_duration_sec=dur,
                    start_offset_sec=seg_start,
                    source_slice_sec=seg_len,
                )
            _normalize_video_clip_exact(
                sewn_p,
                out_mp4,
                w=1920,
                h=1080,
                fps=cfg.fps,
                exact_frames=n_frames,
                start_offset_sec=seg_start,
                trim_source_sec=seg_len,
            )
            p, src = out_mp4, "sewn_google_flow_master"
        elif reuse_existing_clips and out_mp4.exists() and out_mp4.stat().st_size > 16384:
            cached_dur = _probe_video_duration_sec(out_mp4)
            if abs(cached_dur - dur) > 0.08:
                resync_tmp = out_mp4.with_suffix(".resync_tmp.mp4")
                # If a legacy cached clip was ping-ponged (>=15s and >1.38x the clean voiceover duration),
                # keep ONLY its pure forward first half so reversed frames NEVER sneak into the resynced clip!
                forward_cap = (cached_dur * 0.5) if (cached_dur >= 15.0 and cached_dur > dur * 1.38) else None
                _normalize_video_clip_exact(
                    out_mp4,
                    resync_tmp,
                    w=1920,
                    h=1080,
                    fps=cfg.fps,
                    exact_frames=n_frames,
                    trim_source_sec=forward_cap,
                )
                resync_tmp.replace(out_mp4)
                p, src = out_mp4, "cached_ai_cinema(resynced)"
            else:
                p, src = out_mp4, "cached_ai_cinema"
        else:
            if render_quality == "fast_studio_preview":
                scene_quality = "fast_studio_preview"
            elif animate_scene_indices is not None:
                scene_quality = "full_omni_video" if sc.scene_index in animate_scene_indices else "ai_keyframes_kenburns"
            elif render_quality == "hybrid_cinema":
                scene_quality = "full_omni_video" if sc.scene_index in hybrid_hero_ids else "ai_keyframes_kenburns"
            else:
                scene_quality = render_quality
            use_char_lock = bool(
                character_anchor_bytes
                and _scene_mentions_character(
                    sc,
                    character_keywords,
                    has_explicit_flags=has_explicit_char_flags,
                )
            )
            p, src = _generate_ai_scene_visual(
                sc,
                out_mp4,
                topic=agent1.topic,
                niche=agent1.niche,
                duration_sec=dur,
                exact_frames=n_frames,
                aspect_ratio="16:9",
                render_quality=scene_quality,
                force_ai_cinema=force_ai_cinema,
                cinema_preset=cinema_preset,
                foley_out_wav=foley_wav,
                character_anchor_bytes=character_anchor_bytes,
                character_bible=effective_character_bible,
                use_character_anchor=use_char_lock,
                approved_keyframe_path=approved_kf if approved_kf.exists() else None,
                project_id=project_id,
                cost_limit_usd=cost_limit_usd,
                database=database,
                config=cfg,
            )
        # Apply optional presenter PIP badge cleanly on Opening Hook (Scene 1) & Final Outro scene
        if host_pip_png and sc.scene_index in (1, total_scenes):
            pip_mp4 = clips_16_dir / f"scene_{sc.scene_index:03d}_vis_pip.mp4"
            _overlay_host_pip_on_clip(p, host_pip_png, pip_mp4, fps=cfg.fps, exact_frames=n_frames)
            p = pip_mp4
            src = f"{src}+host_pip"
        return sc.scene_index, p, src

    # Run 1 sequential worker during Fast Resume or Sewn Flow Slicing (zero parallel FFmpeg RAM spikes on 1 GB cloud containers);
    # keep 2 concurrent workers during fresh AI video generation (FFmpeg itself is serialized by _FFMPEG_ENCODE_LOCK).
    gc.collect()
    vis_workers = 1 if (reuse_existing_clips or using_sewn_master) else 2
    engine_counts: Dict[str, int] = {}
    with ThreadPoolExecutor(max_workers=vis_workers) as pool:
        futs = [pool.submit(_render_vis, sc) for sc in scenes]
        done_v = 0
        for fut in as_completed(futs):
            s_idx, vp, src = fut.result()
            visual_results[s_idx] = (vp, src)
            engine_counts[src] = engine_counts.get(src, 0) + 1
            done_v += 1
            pct = int((done_v / float(total_scenes)) * 100)
            summary_str = ", ".join(f"{cnt}x {eng}" for eng, cnt in engine_counts.items())
            database.upsert_job(
                job_id=f"{project_id}_visuals_16x9",
                project_id=project_id,
                job_type="media_stage",
                scene_index=3,
                label=stage_defs[2][1],
                status="running" if done_v < total_scenes else "completed",
                progress_pct=pct,
                message=f"Scene {done_v}/{total_scenes} ready ({pct}%)" if done_v < total_scenes else f"{total_scenes} scenes ready",
            )

    # ------------------------------------------------------------------
    # STAGE 4: Topic-Matched Lyria Film Score + Frame-Synced Foley SFX + Smooth RMS Mixing (Zero Cut-Ting!)
    # ------------------------------------------------------------------
    effective_duck_db = float(bgm_duck_db) if bgm_duck_db is not None else float(cfg.bgm_duck_db)
    database.upsert_job(
        job_id=f"{project_id}_bgm_mix",
        project_id=project_id,
        job_type="media_stage",
        scene_index=4,
        label=stage_defs[3][1],
        status="running",
        progress_pct=20,
        message="Composing background music & balancing sound effects...",
    )
    bgm_stem_path = audio_dir / "topic_film_score_bgm.wav"
    generate_niche_bgm_stem(
        bgm_stem_path,
        topic=agent1.topic,
        niche=agent1.niche,
        bgm_style_reference=agent1.bgm_style_reference,
        duration_sec=total_actual_duration,
        bgm_preset=bgm_preset,
        custom_bgm_path=Path(custom_bgm_path) if custom_bgm_path else None,
        config=cfg,
        use_lyria_api=(render_quality != "fast_studio_preview"),
    )
    bgm_engine_note = (
        bgm_stem_path.with_suffix(".engine.txt").read_text(encoding="utf-8").strip()
        if bgm_stem_path.with_suffix(".engine.txt").exists()
        else "topic_score"
    )

    all_words_16x9: List[TimedWord] = []
    master_audio_paths: Dict[int, Path] = {}
    scene_artifacts: List[RenderedSceneArtifact] = []
    native_foley_cnt = 0
    cinema_foley_cnt = 0

    for sc in scenes:
        wav_p, actual_dur, _ = voice_results[sc.scene_index]
        offset = scene_offsets[sc.scene_index]
        master_wav = audio_dir / f"scene_{sc.scene_index:03d}_master.wav"

        # Resolve per-scene Foley SFX track (Priority 1: Native Omni/Veo Foley; Priority 2: Cinema Foley synth)
        active_foley: Optional[Path] = None
        if enable_foley_sfx:
            native_f = audio_dir / f"scene_{sc.scene_index:03d}_foley_native.wav"
            if native_f.exists() and native_f.stat().st_size > 2048:
                active_foley = native_f
                native_foley_cnt += 1
            else:
                synth_f = audio_dir / f"scene_{sc.scene_index:03d}_foley_cinema.wav"
                created_f = synthesize_scene_foley_fallback(
                    synth_f,
                    sfx_cue=sc.sfx_cue,
                    visual_prompt=sc.visual_prompt_veo_omni,
                    duration_sec=actual_dur,
                    scene_index=sc.scene_index,
                )
                if created_f is not None:
                    active_foley = created_f
                    cinema_foley_cnt += 1

        n_frames = scene_frame_counts[sc.scene_index]
        exact_audio_samples = int(round(n_frames * (24000.0 / float(cfg.fps))))
        mix_scene_master_audio(
            wav_p,
            bgm_stem_path,
            master_wav,
            bgm_offset_sec=offset,
            target_duration_sec=actual_dur,
            exact_samples=exact_audio_samples,
            duck_db=effective_duck_db,
            foley_wav_path=active_foley,
            foley_db=-13.5,
            add_cut_sfx=False,
        )
        master_audio_paths[sc.scene_index] = master_wav

        words = extract_scene_word_timestamps(
            wav_p,
            sc.voiceover_text,
            scene_start_offset_sec=offset,
            scene_duration_sec=actual_dur,
            scene_id=sc.scene_index,
            config=cfg,
            use_cloud_transcribe=False,
        )
        all_words_16x9.extend(words)
        scene_artifacts.append(
            RenderedSceneArtifact(
                scene_index=sc.scene_index,
                audio_path=str(master_wav),
                actual_audio_duration_sec=round(actual_dur, 2),
                visual_path=str(visual_results[sc.scene_index][0]),
                asset_source=visual_results[sc.scene_index][1],
            )
        )

    database.upsert_job(
        job_id=f"{project_id}_bgm_mix",
        project_id=project_id,
        job_type="media_stage",
        scene_index=4,
        label=stage_defs[3][1],
        status="completed",
        progress_pct=100,
        message="Music & sound effects mixed",
    )

    # ------------------------------------------------------------------
    # STAGE 5: Stitch 16:9 (1080p) + Continuous 44.1kHz Stereo Audio + Burn `.ass` Subtitles
    # ------------------------------------------------------------------
    gc.collect()
    database.upsert_job(
        job_id=f"{project_id}_assemble_16x9",
        project_id=project_id,
        job_type="media_stage",
        scene_index=5,
        label=stage_defs[4][1],
        status="running",
        progress_pct=30,
        message="Combining scenes, audio & captions into Full HD video...",
    )
    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    vid_16_list: List[Path] = []
    aud_16_list: List[Path] = []
    for sc in scenes:
        vid_16_list.append(visual_results[sc.scene_index][0])
        aud_16_list.append(master_audio_paths[sc.scene_index])

    # Seamless single continuous PCM master track (exact sample-locked to video frames!)
    full_master_16_wav = renders_dir / "master_audio_16x9.wav"
    concat_wav_segments(aud_16_list, full_master_16_wav)

    # Frame-exact concat manifest decoded directly into ONE clean CFR H.264 stream (ZERO -c:v copy overlap!)
    concat_16_lines: List[str] = []
    for sc, vp in zip(scenes, vid_16_list):
        exact_d = scene_frame_counts[sc.scene_index] / float(cfg.fps)
        concat_16_lines.append(f"file '{vp.resolve().as_posix()}'")
        concat_16_lines.append(f"duration {exact_d:.6f}")
    concat_16_txt = renders_dir / "concat_16x9.txt"
    concat_16_txt.write_text("\n".join(concat_16_lines) + "\n", encoding="utf-8")

    ass_16_path = renders_dir / "subtitles_16x9.ass"
    write_active_highlight_ass_file(all_words_16x9, ass_16_path, aspect_ratio="16:9")

    final_16x9_mp4 = renders_dir / "OMNI_FINAL_16x9_1080p.mp4"
    _mux_continuous_audio_and_burn_ass(
        concat_16_txt,
        full_master_16_wav,
        ass_16_path,
        final_16x9_mp4,
        fps=cfg.fps,
        is_concat_list=True,
    )
    database.upsert_job(
        job_id=f"{project_id}_assemble_16x9",
        project_id=project_id,
        job_type="media_stage",
        scene_index=5,
        label=stage_defs[4][1],
        status="completed",
        progress_pct=100,
        message=f"Full HD ready ({format_timestamp(total_actual_duration)})",
        output_path=str(final_16x9_mp4),
    )

    # ------------------------------------------------------------------
    # STAGE 6: 9:16 Viral Hook Short (Strict 10s–20s Curiosity/Fear Teaser -> Full Video Funnel!)
    # ------------------------------------------------------------------
    database.upsert_job(
        job_id=f"{project_id}_assemble_9x16",
        project_id=project_id,
        job_type="media_stage",
        scene_index=6,
        label=stage_defs[5][1],
        status="running",
        progress_pct=30,
        message="Crafting 10–20s viral curiosity hook Short...",
    )
    short_hook_text = _resolve_short_hook_script(agent1, agent2, cfg)
    raw_short_vo_wav = audio_dir / "shorts_hook_voice_raw.wav"
    short_vo_wav, raw_short_vo_dur, _ = synthesize_scene_voiceover(
        short_hook_text,
        short_hook_text,
        raw_short_vo_wav,
        language_tone=agent1.language_tone,
        target_duration_sec=15.0,
        config=cfg,
        prefer_fast_local_tts=prefer_fast_local_tts,
    )
    # Strictly enforce 10.0s <= Short Duration <= 20.0s!
    fitted_short_vo_wav = audio_dir / "shorts_hook_voice_fit.wav"
    short_vo_wav, fitted_vo_dur = _fit_wav_to_max_duration(short_vo_wav, fitted_short_vo_wav, max_sec=19.2)
    min_short_frames = int(round(10.5 * cfg.fps))
    max_short_frames = int(round(19.8 * cfg.fps))
    short_total_frames = max(
        min_short_frames,
        min(max_short_frames, int(math.ceil((fitted_vo_dur + 0.45) * cfg.fps))),
    )
    short_cursor = short_total_frames / float(cfg.fps)

    # Select 3 highest-impact rapid-cut scenes (Opening Hook + Climax Reveal + Hero Twist) — ₹0 extra video spend!
    short_candidates: List[SceneClipSpec] = []
    seen_sids: set = set()
    for sc_c in (
        [s for s in scenes if s.beat_phase == "Visual_Hook_0_45s"][:2]
        + [s for s in scenes if s.beat_phase == "Climax_Aha"][:2]
        + scenes[:3]
    ):
        if sc_c.scene_index not in seen_sids:
            seen_sids.add(sc_c.scene_index)
            short_candidates.append(sc_c)
        if len(short_candidates) >= 3:
            break
    if not short_candidates:
        short_candidates = scenes[:1]

    # Split total frames cleanly across the 3 rapid-fire visual cuts (exact frame sum == short_total_frames!)
    num_cuts = len(short_candidates)
    base_cut_frames = short_total_frames // num_cuts
    cut_frame_allocs = [base_cut_frames] * num_cuts
    cut_frame_allocs[-1] += short_total_frames - sum(cut_frame_allocs)

    vid_9_list: List[Path] = []
    concat_9_lines: List[str] = []
    for cut_idx, (sc, cut_frames) in enumerate(zip(short_candidates, cut_frame_allocs), start=1):
        vis_16 = visual_results[sc.scene_index][0]
        seg_9 = clips_9_dir / f"short_vid_{cut_idx:02d}_s{sc.scene_index:03d}.mp4"
        cut_dur_sec = cut_frames / float(cfg.fps)
        _normalize_video_clip_exact(
            vis_16,
            seg_9,
            w=1080,
            h=1920,
            fps=cfg.fps,
            exact_frames=cut_frames,
            trim_source_sec=cut_dur_sec,
        )
        vid_9_list.append(seg_9)
        concat_9_lines.append(f"file '{seg_9.resolve().as_posix()}'")
        concat_9_lines.append(f"duration {cut_dur_sec:.6f}")

    # Mix punchy hook narration + topic-matched film score to exact sample lock
    full_master_9_wav = renders_dir / "master_audio_9x16.wav"
    exact_short_samples = int(round(short_total_frames * (24000.0 / float(cfg.fps))))
    mix_scene_master_audio(
        short_vo_wav,
        bgm_stem_path,
        full_master_9_wav,
        bgm_offset_sec=0.0,
        target_duration_sec=short_cursor,
        exact_samples=exact_short_samples,
        duck_db=effective_duck_db,
        foley_wav_path=None,
        add_cut_sfx=False,
    )

    short_words = extract_scene_word_timestamps(
        short_vo_wav,
        short_hook_text,
        scene_start_offset_sec=0.0,
        scene_duration_sec=min(short_cursor, fitted_vo_dur + 0.15),
        scene_id=1,
        config=cfg,
        use_cloud_transcribe=False,
    )

    concat_9_txt = renders_dir / "concat_9x16.txt"
    concat_9_txt.write_text("\n".join(concat_9_lines) + "\n", encoding="utf-8")

    ass_9_path = renders_dir / "subtitles_9x16.ass"
    write_active_highlight_ass_file(short_words, ass_9_path, aspect_ratio="9:16")

    final_9x16_mp4 = renders_dir / "OMNI_SHORTS_9x16.mp4"
    _mux_continuous_audio_and_burn_ass(
        concat_9_txt,
        full_master_9_wav,
        ass_9_path,
        final_9x16_mp4,
        fps=cfg.fps,
        is_concat_list=True,
    )
    database.upsert_job(
        job_id=f"{project_id}_assemble_9x16",
        project_id=project_id,
        job_type="media_stage",
        scene_index=6,
        label=stage_defs[5][1],
        status="completed",
        progress_pct=100,
        message=f"Hook Short ready ({short_cursor:.1f}s)",
        output_path=str(final_9x16_mp4),
    )

    out = Agent3Output(
        project_dir=str(proj_dir),
        video_16x9_path=str(final_16x9_mp4),
        video_9x16_shorts_path=str(final_9x16_mp4),
        thumbnail_16x9_path=str(thumb_path),
        thumbnail_9x16_path=thumb_9x16_path_str,
        ass_subtitles_16x9_path=str(ass_16_path),
        ass_subtitles_9x16_path=str(ass_9_path),
        bgm_stem_path=str(bgm_stem_path),
        final_duration_sec=total_actual_duration,
        shorts_duration_sec=round(short_cursor, 2),
        short_hook_script=short_hook_text,
        scene_count_rendered=total_scenes,
        exact_chapters_text=exact_chapters_text,
        generation_mode="sewn_google_flow_enriched" if using_sewn_master else render_quality,
        scene_artifacts=scene_artifacts,
    )
    out_dict = out.model_dump()
    database.update_project_stage(project_id, status="step3_rendered", agent3_data=out_dict)
    # Persist rendered deliverables in background to the user's private Google Cloud bucket
    try:
        from storage.cloud_sync import upload_project_renders_to_gcs

        threading.Thread(
            target=upload_project_renders_to_gcs,
            args=(project_id, out_dict),
            daemon=True,
            name=f"gcs_renders_{project_id[:12]}",
        ).start()
    except Exception:
        pass
    return out
