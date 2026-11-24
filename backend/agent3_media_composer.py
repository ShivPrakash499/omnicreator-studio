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
import logging
import math
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import imageio_ffmpeg
from PIL import Image, ImageDraw, ImageFont

from backend.config import (
    IMAGE_CONTINUITY_MODEL,
    IMAGE_PRO_MODEL,
    VERTEX_VEO_MODEL,
    VIDEO_OMNI_MODEL,
    OmniStudioConfig,
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
from render_engine.motion_graphics import render_motion_graphic_clip
from render_engine.subtitle_engine import (
    TimedWord,
    extract_scene_word_timestamps,
    write_active_highlight_ass_file,
)
from render_engine.thumbnail_studio import generate_high_ctr_thumbnail
from storage.db import OmniDatabase, get_db

logger = logging.getLogger("omni_studio.agent3")


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


def _generate_ai_scene_visual(
    scene: SceneClipSpec,
    output_mp4: Path,
    *,
    topic: str,
    niche: str,
    duration_sec: float,
    aspect_ratio: str,
    render_quality: str,
    config: OmniStudioConfig,
) -> Tuple[Path, str]:
    """
    Produces a single scene's visual MP4 clip:
    - `custom_upload`: normalizes user's uploaded MP4/image directly.
    - `motion_graphics`: calls zero-hallucination procedural motion graphics engine.
    - `ai_video`:
        - `full_omni_video`: calls `gemini-omni-1.2-flash` (`client.interactions.create`) for live AI video clips.
        - `ai_keyframes_kenburns`: calls `gemini-nano-banana-2.1` / `gemini-3-pro-image` to generate sharp
          AI keyframes and animates smooth 24fps camera motion via FFmpeg.
        - `fast_studio_preview`: fast local kinetic broadcast plate + procedural graphics (zero API wait/cost).
    """
    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    w, h = (1920, 1080) if aspect_ratio == "16:9" else (1080, 1920)
    fps = config.fps
    dur = max(2.5, float(duration_sec))
    output_mp4.parent.mkdir(parents=True, exist_ok=True)

    # 1. Custom User Asset Override
    if scene.custom_asset_path and Path(scene.custom_asset_path).exists():
        custom_p = Path(scene.custom_asset_path)
        if custom_p.suffix.lower() in (".mp4", ".mov", ".mkv", ".webm"):
            subprocess.run(
                [
                    ffmpeg_exe, "-y",
                    "-stream_loop", "-1", "-i", str(custom_p),
                    "-vf", f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},format=yuv420p",
                    "-t", f"{dur:.2f}", "-r", str(fps), "-an",
                    "-c:v", "libx264", "-preset", "ultrafast", "-crf", "20",
                    str(output_mp4),
                ],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            return output_mp4, "custom_uploaded_video"
        else:
            vf = (
                f"scale={int(w*1.08)}:{int(h*1.08)}:force_original_aspect_ratio=increase,"
                f"crop={w}:{h}:x='(iw-ow)/2+((iw-ow)/4)*sin(2*PI*t/{dur:.2f})':y='(ih-oh)/2',format=yuv420p"
            )
            subprocess.run(
                [
                    ffmpeg_exe, "-y", "-loop", "1", "-i", str(custom_p),
                    "-vf", vf, "-t", f"{dur:.2f}", "-r", str(fps), "-an",
                    "-c:v", "libx264", "-preset", "ultrafast", "-crf", "20",
                    str(output_mp4),
                ],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            return output_mp4, "custom_uploaded_image"

    # 2. Procedural Motion Graphics (Manim / Matplotlib / Vector Telemetry — zero hallucination!)
    if scene.asset_mode == "motion_graphics" and scene.motion_graphic_type and scene.motion_graphic_type != "none":
        render_motion_graphic_clip(
            output_mp4,
            graphic_type=scene.motion_graphic_type,
            title=scene.chapter_label or topic,
            callout=scene.on_screen_callout or scene.voiceover_text[:72],
            niche=niche,
            duration_sec=dur,
            payload=scene.motion_graphic_payload,
            aspect_ratio=aspect_ratio,
            fps=fps,
        )
        return output_mp4, f"procedural_{scene.motion_graphic_type}"

    # 3. Full AI Video via Vertex Veo 3.1 (`veo-3.1-generate-001`) OR `gemini-omni-1.2-flash`
    if render_quality == "full_omni_video" and config.has_valid_gemini_key:
        v_creds, v_proj = get_vertex_adc_credentials()
        if v_creds is not None and v_proj:
            try:
                import time as _time
                v_us = get_genai_client(config.gemini_api_key, location="us-central1")
                veo_dur = 8 if dur >= 7.0 else 6
                op = v_us.models.generate_videos(
                    model=VERTEX_VEO_MODEL,
                    source=genai_types.GenerateVideosSource(
                        prompt=f"{scene.visual_prompt_veo_omni} Single continuous 24fps shot, no garbled text."
                    ),
                    config=genai_types.GenerateVideosConfig(aspect_ratio=aspect_ratio, duration_seconds=veo_dur),
                )
                deadline = _time.time() + 180.0
                while not getattr(op, "done", False) and _time.time() < deadline:
                    _time.sleep(6.0)
                    op = v_us.operations.get(op)
                gen_vids = getattr(getattr(op, "response", None), "generated_videos", None) or []
                if gen_vids and getattr(gen_vids[0], "video", None) and getattr(gen_vids[0].video, "video_bytes", None):
                    raw_tmp = output_mp4.with_suffix(".veo_raw.mp4")
                    raw_tmp.write_bytes(gen_vids[0].video.video_bytes)
                    subprocess.run(
                        [
                            ffmpeg_exe, "-y",
                            "-stream_loop", "-1", "-i", str(raw_tmp),
                            "-vf", f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},format=yuv420p",
                            "-t", f"{dur:.2f}", "-r", str(fps), "-an",
                            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "20",
                            str(output_mp4),
                        ],
                        check=True,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                    )
                    raw_tmp.unlink(missing_ok=True)
                    return output_mp4, f"vertex_veo({VERTEX_VEO_MODEL})"
            except Exception as exc:
                logger.info("Scene %d Vertex Veo 3.1 fell back to AI keyframe animation: %s", scene.scene_index, exc)
        else:
            try:
                client = get_genai_client(config.gemini_api_key)
                omni_dur = max(3, min(15, int(round(dur))))
                interaction = call_interaction_with_fallback(
                    client,
                    models=[resolve_current_model(VIDEO_OMNI_MODEL, "gemini-omni-1.2-flash")],
                    max_retries=2,
                    input=f"{scene.visual_prompt_veo_omni} In a single continuous unbroken 24fps shot. No dialogue, no garbled text.",
                    response_format={
                        "type": "video",
                        "aspect_ratio": aspect_ratio,
                        "resolution": "720p" if aspect_ratio == "9:16" else "1080p",
                        "duration": omni_dur,
                    },
                )
                out_vid = getattr(interaction, "output_video", None)
                if out_vid and getattr(out_vid, "data", None):
                    raw_vid = base64.b64decode(out_vid.data) if isinstance(out_vid.data, str) else bytes(out_vid.data)
                    raw_tmp = output_mp4.with_suffix(".omni_raw.mp4")
                    raw_tmp.write_bytes(raw_vid)
                    subprocess.run(
                        [
                            ffmpeg_exe, "-y",
                            "-stream_loop", "-1", "-i", str(raw_tmp),
                            "-vf", f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},format=yuv420p",
                            "-t", f"{dur:.2f}", "-r", str(fps), "-an",
                            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "20",
                            str(output_mp4),
                        ],
                        check=True,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                    )
                    raw_tmp.unlink(missing_ok=True)
                    return output_mp4, f"gemini_omni({VIDEO_OMNI_MODEL})"
            except Exception as exc:
                logger.info("Scene %d Omni video fell back to AI keyframe animation: %s", scene.scene_index, exc)

    # 4. AI Keyframe Generation (`gemini-nano-banana-2.1` / `gemini-3-pro-image`) + Kinetic Camera Motion
    frame_png = output_mp4.with_suffix(".png")
    source_tag = "kinetic_studio_plate"
    if render_quality in ("full_omni_video", "ai_keyframes_kenburns") and config.has_valid_gemini_key:
        try:
            client = get_genai_client(config.gemini_api_key)
            v_creds, v_proj = get_vertex_adc_credentials()
            if v_creds is not None and v_proj:
                for m_kf in (
                    resolve_current_model(IMAGE_CONTINUITY_MODEL, "gemini-nano-banana-2.1"),
                    resolve_current_model(IMAGE_PRO_MODEL, "gemini-3-pro-image"),
                ):
                    try:
                        resp = client.models.generate_content(
                            model=m_kf,
                            contents=f"{scene.visual_prompt_veo_omni} Photorealistic widescreen frame, no text, no watermarks.",
                            config=genai_types.GenerateContentConfig(
                                response_modalities=["IMAGE"],
                                image_config=genai_types.ImageConfig(aspect_ratio=aspect_ratio),
                            ),
                        )
                        for cand in getattr(resp, "candidates", []) or []:
                            for part in getattr(getattr(cand, "content", None), "parts", []) or []:
                                if getattr(part, "inline_data", None) and part.inline_data.data:
                                    frame_png.write_bytes(bytes(part.inline_data.data))
                                    source_tag = f"vertex_keyframe({m_kf})"
                                    break
                            if frame_png.exists():
                                break
                        if frame_png.exists():
                            break
                    except Exception:
                        continue
            else:
                interaction = call_interaction_with_fallback(
                    client,
                    models=[
                        resolve_current_model(IMAGE_CONTINUITY_MODEL, "gemini-nano-banana-2.1"),
                        resolve_current_model(IMAGE_PRO_MODEL, "gemini-3-pro-image"),
                    ],
                    max_retries=2,
                    input=f"{scene.visual_prompt_veo_omni} Photorealistic widescreen frame, no text, no watermarks.",
                    response_format={"type": "image", "aspect_ratio": aspect_ratio, "image_size": "1K"},
                )
                out_img = getattr(interaction, "output_image", None)
                if out_img and getattr(out_img, "data", None):
                    raw_img = base64.b64decode(out_img.data) if isinstance(out_img.data, str) else bytes(out_img.data)
                    frame_png.write_bytes(raw_img)
                    source_tag = f"ai_keyframe({IMAGE_CONTINUITY_MODEL})"
        except Exception as exc:
            logger.info("Scene %d AI keyframe fell back to studio plate: %s", scene.scene_index, exc)

    if not frame_png.exists():
        _render_kinetic_cinematic_plate(frame_png, scene=scene, topic=topic, niche=niche, size=(w, h))

    # Animate smooth broadcast Ken-Burns drift keeping centered safe zone intact
    vf = (
        f"scale={int(w * 1.05)}:{int(h * 1.05)}:force_original_aspect_ratio=increase,"
        f"crop={w}:{h}:x='(iw-ow)/2+((iw-ow)/4)*sin(2*PI*t/{dur:.2f})':y='(ih-oh)/2+((ih-oh)/4)*cos(2*PI*t/{dur:.2f})',"
        f"format=yuv420p"
    )
    subprocess.run(
        [
            ffmpeg_exe, "-y",
            "-loop", "1", "-i", str(frame_png),
            "-vf", vf,
            "-t", f"{dur:.2f}",
            "-r", str(fps),
            "-an",
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "20",
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
) -> Path:
    """Overlays the optional circular host PIP cleanly into the bottom-left safe zone."""
    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    subprocess.run(
        [
            ffmpeg_exe, "-y",
            "-i", str(input_mp4),
            "-i", str(pip_png),
            "-filter_complex", "[0:v][1:v]overlay=44:H-h-180[outv]",
            "-map", "[outv]",
            "-an",
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "20",
            str(output_mp4),
        ],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return output_mp4


def _mux_continuous_audio_and_burn_ass(
    video_only_mp4: Path,
    continuous_master_wav: Path,
    ass_path: Path,
    output_mp4: Path,
) -> Path:
    """
    Single-pass broadcast mux: combines concatenated silent video + ONE continuous PCM master WAV,
    burns word-level active-highlight `.ass` subtitles (with bundled Devanagari fontsdir),
    encodes browser-universal 44.1kHz STEREO AAC-LC (`-ar 44100 -ac 2 -c:a aac -b:a 192k`)
    with `-movflags +faststart` so Chrome, Edge, Safari, Mobile & YouTube ALWAYS play crystal-clear sound!
    """
    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    escaped_ass = _ffmpeg_ass_filter_escape(ass_path)
    fonts_dir = Path("assets/fonts")
    vf_str = (
        f"ass='{escaped_ass}':fontsdir='{_ffmpeg_ass_filter_escape(fonts_dir)}'"
        if fonts_dir.exists()
        else f"ass='{escaped_ass}'"
    )
    try:
        subprocess.run(
            [
                ffmpeg_exe, "-y",
                "-i", str(video_only_mp4),
                "-i", str(continuous_master_wav),
                "-map", "0:v:0", "-map", "1:a:0",
                "-vf", vf_str,
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-ar", "44100", "-ac", "2", "-b:a", "192k",
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
    except Exception as exc:
        logger.warning("FFmpeg ASS burn pass failed (%s); muxing clean stereo audio without ASS filter.", exc)

    # Guaranteed fallback WITH full 44.1kHz stereo audio (never drops audio!)
    subprocess.run(
        [
            ffmpeg_exe, "-y",
            "-i", str(video_only_mp4),
            "-i", str(continuous_master_wav),
            "-map", "0:v:0", "-map", "1:a:0",
            "-c:v", "copy",
            "-c:a", "aac", "-ar", "44100", "-ac", "2", "-b:a", "192k",
            "-movflags", "+faststart",
            "-shortest",
            str(output_mp4),
        ],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return output_mp4


def run_agent3_media_pipeline(
    project_id: str,
    agent1: Agent1Output,
    agent2: Agent2Output,
    *,
    render_quality: str = "ai_keyframes_kenburns",
    include_avatar_in_thumbnail: bool = False,
    avatar_thumbnail_mode: str = "real_photo",
    include_avatar_in_video: bool = False,
    creator_side: str = "left",
    prefer_fast_local_tts: bool = False,
    use_ai_thumbnail: bool = True,
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

    scenes = agent2.scenes
    total_scenes = len(scenes)

    database.clear_project_jobs(project_id, job_type="media_stage")
    # Seed stage trackers in SQLite so UI shows live progress immediately
    stage_defs = [
        ("voiceover", "1. Indian Voiceover Synthesis & Duration Anchoring"),
        ("thumbnail", "2. High-CTR @jwalashiva Likeness Thumbnail Studio"),
        ("visuals_16x9", "3. Scene Visuals & Procedural Motion Graphics (16:9)"),
        ("bgm_mix", "4. Niche BGM (-24dB Ducking) & Master Audio Mixing"),
        ("assemble_16x9", "5. 1080p Final Assembly & Active-Highlight .ass Subtitles"),
        ("assemble_9x16", "6. 9:16 Vertical Shorts Cutdown & Vertical Subtitles"),
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
            message="Waiting...",
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
        message=f"Synthesizing 0/{total_scenes} scene voiceovers...",
    )
    voice_results: Dict[int, Tuple[Path, float, str]] = {}

    def _synth_one(sc: SceneClipSpec) -> Tuple[int, Path, float, str]:
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
        return sc.scene_index, p, max(3.0, dur + 0.25), eng

    with ThreadPoolExecutor(max_workers=2) as pool:
        futs = [pool.submit(_synth_one, sc) for sc in scenes]
        done_cnt = 0
        for fut in as_completed(futs):
            s_idx, wav_p, actual_dur, eng = fut.result()
            voice_results[s_idx] = (wav_p, actual_dur, eng)
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
                message=f"Processing ({pct}%) — {done_cnt}/{total_scenes} clips anchored ({eng})" if done_cnt < total_scenes else f"Completed ✅ ({total_scenes} voiceovers anchored)",
            )

    # Exact global offsets & YouTube Chapters derived from measured WAV durations
    scene_offsets: Dict[int, float] = {}
    cursor = 0.0
    chapter_seen: List[str] = []
    exact_chapter_lines: List[str] = []
    for sc in scenes:
        scene_offsets[sc.scene_index] = round(cursor, 3)
        lbl = (sc.chapter_label or sc.beat_phase.replace("_", " ")).strip()
        if lbl and lbl not in chapter_seen:
            chapter_seen.append(lbl)
            exact_chapter_lines.append(f"{format_timestamp(cursor)} - {lbl}")
        cursor += voice_results[sc.scene_index][1]
    total_actual_duration = round(cursor, 2)
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
        message="Generating High-CTR Thumbnail preserving @jwalashiva likeness (image_12..14.png)...",
    )
    thumb_path = renders_dir / "thumbnail_16x9.png"
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
    database.upsert_job(
        job_id=f"{project_id}_thumbnail",
        project_id=project_id,
        job_type="media_stage",
        scene_index=2,
        label=stage_defs[1][1],
        status="completed",
        progress_pct=100,
        message=f"Completed ✅ ({thumb_engine})",
        output_path=str(thumb_path),
    )

    # ------------------------------------------------------------------
    # STAGE 3: Visual Generation & Procedural Motion Graphics (16:9)
    # ------------------------------------------------------------------
    database.upsert_job(
        job_id=f"{project_id}_visuals_16x9",
        project_id=project_id,
        job_type="media_stage",
        scene_index=3,
        label=stage_defs[2][1],
        status="running",
        progress_pct=5,
        message=f"Rendering 0/{total_scenes} visual scenes...",
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

    def _render_vis(sc: SceneClipSpec) -> Tuple[int, Path, str]:
        dur = voice_results[sc.scene_index][1]
        out_mp4 = clips_16_dir / f"scene_{sc.scene_index:03d}_vis.mp4"
        p, src = _generate_ai_scene_visual(
            sc,
            out_mp4,
            topic=agent1.topic,
            niche=agent1.niche,
            duration_sec=dur,
            aspect_ratio="16:9",
            render_quality=render_quality,
            config=cfg,
        )
        # Apply optional presenter PIP badge cleanly on Opening Hook (Scene 1) & Final Outro scene
        if host_pip_png and sc.scene_index in (1, total_scenes):
            pip_mp4 = clips_16_dir / f"scene_{sc.scene_index:03d}_vis_pip.mp4"
            _overlay_host_pip_on_clip(p, host_pip_png, pip_mp4)
            p = pip_mp4
            src = f"{src}+host_pip"
        return sc.scene_index, p, src

    with ThreadPoolExecutor(max_workers=min(3, cfg.max_workers)) as pool:
        futs = [pool.submit(_render_vis, sc) for sc in scenes]
        done_v = 0
        for fut in as_completed(futs):
            s_idx, vp, src = fut.result()
            visual_results[s_idx] = (vp, src)
            done_v += 1
            pct = int((done_v / float(total_scenes)) * 100)
            database.upsert_job(
                job_id=f"{project_id}_visuals_16x9",
                project_id=project_id,
                job_type="media_stage",
                scene_index=3,
                label=stage_defs[2][1],
                status="running" if done_v < total_scenes else "completed",
                progress_pct=pct,
                message=f"Processing ({pct}%) — {done_v}/{total_scenes} visual clips ready" if done_v < total_scenes else f"Completed ✅ ({total_scenes} 1080p visual clips)",
            )

    # ------------------------------------------------------------------
    # STAGE 4: Niche BGM Stem (-24dB Ducking) + Scene Master Audio & Word Alignment
    # ------------------------------------------------------------------
    database.upsert_job(
        job_id=f"{project_id}_bgm_mix",
        project_id=project_id,
        job_type="media_stage",
        scene_index=4,
        label=stage_defs[3][1],
        status="running",
        progress_pct=20,
        message="Generating high-spirited niche BGM stem & ducking to -24dB...",
    )
    bgm_stem_path = audio_dir / "niche_bgm_stem.wav"
    generate_niche_bgm_stem(
        bgm_stem_path,
        niche=agent1.niche,
        bgm_style_reference=agent1.bgm_style_reference,
        duration_sec=total_actual_duration,
        config=cfg,
        use_lyria_api=(render_quality != "fast_studio_preview"),
    )

    all_words_16x9: List[TimedWord] = []
    master_audio_paths: Dict[int, Path] = {}
    scene_artifacts: List[RenderedSceneArtifact] = []

    for sc in scenes:
        wav_p, actual_dur, _ = voice_results[sc.scene_index]
        offset = scene_offsets[sc.scene_index]
        master_wav = audio_dir / f"scene_{sc.scene_index:03d}_master.wav"
        mix_scene_master_audio(
            wav_p,
            bgm_stem_path,
            master_wav,
            bgm_offset_sec=offset,
            target_duration_sec=actual_dur,
            duck_db=cfg.bgm_duck_db,
            add_cut_sfx=True,
        )
        master_audio_paths[sc.scene_index] = master_wav

        words = extract_scene_word_timestamps(
            wav_p,
            sc.voiceover_text,
            scene_start_offset_sec=offset,
            scene_duration_sec=actual_dur,
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
        message=f"Completed ✅ (BGM ducked strictly at {cfg.bgm_duck_db}dB + {len(all_words_16x9)} word timestamps)",
    )

    # ------------------------------------------------------------------
    # STAGE 5: Stitch 16:9 (1080p) + Continuous 44.1kHz Stereo Audio + Burn `.ass` Subtitles
    # ------------------------------------------------------------------
    database.upsert_job(
        job_id=f"{project_id}_assemble_16x9",
        project_id=project_id,
        job_type="media_stage",
        scene_index=5,
        label=stage_defs[4][1],
        status="running",
        progress_pct=30,
        message="Stitching video + continuous 44.1kHz stereo audio + active-highlight .ass subtitles (1080p)...",
    )
    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    vid_16_list: List[Path] = []
    aud_16_list: List[Path] = []
    for sc in scenes:
        vid_16_list.append(visual_results[sc.scene_index][0])
        aud_16_list.append(master_audio_paths[sc.scene_index])

    # Seamless single continuous PCM master track (zero AAC concat discontinuities!)
    full_master_16_wav = renders_dir / "master_audio_16x9.wav"
    concat_wav_segments(aud_16_list, full_master_16_wav)

    concat_16_txt = renders_dir / "concat_16x9.txt"
    concat_16_txt.write_text("\n".join(f"file '{p.resolve().as_posix()}'" for p in vid_16_list), encoding="utf-8")
    raw_vid_16x9 = renders_dir / "raw_video_only_16x9.mp4"
    subprocess.run(
        [ffmpeg_exe, "-y", "-f", "concat", "-safe", "0", "-i", str(concat_16_txt), "-c:v", "copy", "-an", str(raw_vid_16x9)],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    ass_16_path = renders_dir / "subtitles_16x9.ass"
    write_active_highlight_ass_file(all_words_16x9, ass_16_path, aspect_ratio="16:9")

    final_16x9_mp4 = renders_dir / "OMNI_FINAL_16x9_1080p.mp4"
    _mux_continuous_audio_and_burn_ass(raw_vid_16x9, full_master_16_wav, ass_16_path, final_16x9_mp4)
    database.upsert_job(
        job_id=f"{project_id}_assemble_16x9",
        project_id=project_id,
        job_type="media_stage",
        scene_index=5,
        label=stage_defs[4][1],
        status="completed",
        progress_pct=100,
        message=f"Completed ✅ (1080p 16:9 • 44.1kHz Stereo AAC • {total_actual_duration:.1f}s)",
        output_path=str(final_16x9_mp4),
    )

    # ------------------------------------------------------------------
    # STAGE 6: 9:16 Vertical Shorts Cutdown (Continuous Stereo Audio + Active Captions <= 58s)
    # ------------------------------------------------------------------
    database.upsert_job(
        job_id=f"{project_id}_assemble_9x16",
        project_id=project_id,
        job_type="media_stage",
        scene_index=6,
        label=stage_defs[5][1],
        status="running",
        progress_pct=35,
        message="Building 9:16 vertical Shorts cutdown with stereo audio & active captions...",
    )
    short_scenes: List[SceneClipSpec] = []
    short_dur_acc = 0.0
    prioritized = (
        [s for s in scenes if s.beat_phase == "Visual_Hook_0_45s"][:3]
        + [s for s in scenes if s.beat_phase == "Climax_Aha"][:2]
        + [s for s in scenes if s.beat_phase == "Outro_CTA"][-1:]
    )
    if not prioritized:
        prioritized = scenes[:5]
    seen_sids = set()
    for sc in prioritized:
        if sc.scene_index in seen_sids:
            continue
        sdur = voice_results[sc.scene_index][1]
        if short_dur_acc + sdur <= 58.0 or not short_scenes:
            short_scenes.append(sc)
            seen_sids.add(sc.scene_index)
            short_dur_acc += sdur

    vid_9_list: List[Path] = []
    aud_9_list: List[Path] = []
    short_words: List[TimedWord] = []
    short_cursor = 0.0
    for sc in short_scenes:
        dur = voice_results[sc.scene_index][1]
        vis_16 = visual_results[sc.scene_index][0]
        seg_9 = clips_9_dir / f"short_vid_{sc.scene_index:03d}.mp4"
        subprocess.run(
            [
                ffmpeg_exe, "-y",
                "-i", str(vis_16),
                "-vf", "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,format=yuv420p",
                "-t", f"{dur:.2f}",
                "-r", str(cfg.fps),
                "-an",
                "-c:v", "libx264", "-preset", "ultrafast", "-crf", "21",
                str(seg_9),
            ],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        vid_9_list.append(seg_9)
        aud_9_list.append(master_audio_paths[sc.scene_index])
        short_words.extend(
            extract_scene_word_timestamps(
                voice_results[sc.scene_index][0],
                sc.voiceover_text,
                scene_start_offset_sec=short_cursor,
                scene_duration_sec=dur,
                config=cfg,
                use_cloud_transcribe=False,
            )
        )
        short_cursor += dur

    full_master_9_wav = renders_dir / "master_audio_9x16.wav"
    concat_wav_segments(aud_9_list, full_master_9_wav)

    concat_9_txt = renders_dir / "concat_9x16.txt"
    concat_9_txt.write_text("\n".join(f"file '{p.resolve().as_posix()}'" for p in vid_9_list), encoding="utf-8")
    raw_vid_9x16 = renders_dir / "raw_video_only_9x16.mp4"
    subprocess.run(
        [ffmpeg_exe, "-y", "-f", "concat", "-safe", "0", "-i", str(concat_9_txt), "-c:v", "copy", "-an", str(raw_vid_9x16)],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    ass_9_path = renders_dir / "subtitles_9x16.ass"
    write_active_highlight_ass_file(short_words, ass_9_path, aspect_ratio="9:16")

    final_9x16_mp4 = renders_dir / "OMNI_SHORTS_9x16.mp4"
    _mux_continuous_audio_and_burn_ass(raw_vid_9x16, full_master_9_wav, ass_9_path, final_9x16_mp4)
    database.upsert_job(
        job_id=f"{project_id}_assemble_9x16",
        project_id=project_id,
        job_type="media_stage",
        scene_index=6,
        label=stage_defs[5][1],
        status="completed",
        progress_pct=100,
        message=f"Completed ✅ (9:16 Shorts • 44.1kHz Stereo AAC • {short_cursor:.1f}s)",
        output_path=str(final_9x16_mp4),
    )

    out = Agent3Output(
        project_dir=str(proj_dir),
        video_16x9_path=str(final_16x9_mp4),
        video_9x16_shorts_path=str(final_9x16_mp4),
        thumbnail_16x9_path=str(thumb_path),
        ass_subtitles_16x9_path=str(ass_16_path),
        ass_subtitles_9x16_path=str(ass_9_path),
        bgm_stem_path=str(bgm_stem_path),
        final_duration_sec=total_actual_duration,
        shorts_duration_sec=round(short_cursor, 2),
        scene_count_rendered=total_scenes,
        exact_chapters_text=exact_chapters_text,
        generation_mode=render_quality,
        scene_artifacts=scene_artifacts,
    )
    database.update_project_stage(project_id, status="step3_rendered", agent3_data=out.model_dump())
    return out
