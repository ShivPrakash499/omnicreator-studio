"""
Module E: `omni_creator/compositor_and_packager.py`
===================================================
FFmpeg/MoviePy Compositor + Glassmorphic HUD Overlays + Expressive Hinglish Narration (`gemini-3.8-flash-tts`) +
Word-Level Timestamps (`gemini-3.5-transcribe`) + `-22dB` Ducked `lyria-3.5` Dark-Synth Ambient Score +
YouTube Publish Bundle (`final_video_4k.mp4`, `thumbnails/variant_1..3.png`, `youtube_seo_package.json`,
and `youtube_publish_sheet.md`).
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import math
import re
import shutil
import struct
import subprocess
import wave
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from PIL import Image, ImageDraw, ImageFont

from config.models import (
    HINGLISH_VOICE_STYLE_PROMPT,
    LYRIA_DARK_SYNTH_PROMPT,
    MUSIC_LYRIA_MODEL,
    TRANSCRIBE_MODEL,
    TTS_EXPRESSIVE_MODEL,
    OmniModelConfig,
    call_interaction_with_backoff,
    compute_content_sha256,
    estimate_pipeline_credits,
    get_genai_client,
)
from omni_creator.thumbnail_hook_studio import generate_ab_thumbnail_suite
from omni_creator.visual_3d_generator import (
    Visual3DBundle,
    generate_all_3d_visuals_for_blueprint,
    render_dark_obsidian_3d_keyframe,
    render_smooth_24fps_3d_clip_from_keyframes,
)
from schemas.blueprint import ChapterVideoBlueprint

logger = logging.getLogger("omni_creator.compositor_and_packager")


@dataclass
class WordTimestamp:
    word: str
    start_sec: float
    end_sec: float


@dataclass
class OmniProductionOutput:
    """Result bundle exported to `output/{class}_{subject}_{chapter}/`."""
    bundle_dir: Path
    final_video_path: Optional[Path]
    thumbnail_paths: Dict[str, Path]
    seo_json_path: Path
    publish_sheet_md_path: Path
    credit_estimate: Dict[str, Any]
    dry_run: bool = False
    word_timestamps_count: int = 0


def _sanitize_slug(text: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", text.strip()).strip("_").lower()
    return slug[:48] or "chapter"


def _load_hud_font(size: int, bold: bool = True) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for p in [
        "C:/Windows/Fonts/segoeuib.ttf" if bold else "C:/Windows/Fonts/segoeui.ttf",
        "C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/calibrib.ttf",
    ]:
        if Path(p).exists():
            try:
                return ImageFont.truetype(p, size=size)
            except Exception:
                pass
    return ImageFont.load_default()


# ==============================================================================
# 1. EXPRESSIVE HINGLISH NARRATION (`gemini-3.8-flash-tts` + `@jwalashiv` Persona)
# ==============================================================================
def synthesize_hinglish_narration_segment(
    spoken_text: str,
    output_wav_path: Path,
    *,
    target_duration_sec: float,
    config: Optional[OmniModelConfig] = None,
    dry_run: bool = False,
) -> Path:
    """
    Synthesizes charismatic 24-28 yr old Indian 'Cool Senior / Mentor' (@jwalashiv) Hinglish voiceover
    via `gemini-3.8-flash-tts` (`client.interactions.create(...)`), with automatic fallback to
    Edge-TTS `en-IN-PrabhatNeural` (@jwalashiv baritone profile) or PCM synthesizer.
    """
    if output_wav_path.exists() and output_wav_path.stat().st_size > 1024:
        return output_wav_path

    cfg = config or OmniModelConfig()
    output_wav_path.parent.mkdir(parents=True, exist_ok=True)
    clean_text = re.sub(r"\[350ms pause\]", "... ", spoken_text).strip()

    if not dry_run and cfg.api_key and cfg.api_key != "your_gemini_paid_tier1_api_key_here":
        try:
            client = get_genai_client(cfg.api_key)
            interaction = call_interaction_with_backoff(
                client,
                model=TTS_EXPRESSIVE_MODEL,
                input=[
                    {
                        "type": "user_input",
                        "content": [
                            {
                                "type": "text",
                                "text": clean_text,
                                "annotations": [
                                    {
                                        "type": "speech_metadata",
                                        "style": HINGLISH_VOICE_STYLE_PROMPT,
                                    }
                                ],
                            }
                        ],
                    }
                ],
                response_format={"type": "audio"},
                generation_config={
                    "speech_config": [
                        {
                            "voice": "Puck",
                        }
                    ]
                },
            )
            out_aud = getattr(interaction, "output_audio", None)
            if out_aud and getattr(out_aud, "data", None):
                aud_bytes = (
                    base64.b64decode(out_aud.data)
                    if isinstance(out_aud.data, str)
                    else bytes(out_aud.data)
                )
                tmp_raw = output_wav_path.with_suffix(".tts_raw")
                tmp_raw.write_bytes(aud_bytes)
                import imageio_ffmpeg
                ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
                subprocess.run(
                    [
                        ffmpeg_exe, "-y", "-i", str(tmp_raw),
                        "-ar", "24000", "-ac", "1", str(output_wav_path),
                    ],
                    check=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
                tmp_raw.unlink(missing_ok=True)
                return output_wav_path
        except Exception as exc:
            logger.info("gemini-3.8-flash-tts API call fell back to @jwalashiv Edge-TTS baritone: %s", exc)

    # Local Edge-TTS @jwalashiv baritone mentor fallback (`en-IN-PrabhatNeural` at +12% rate, -4Hz pitch)
    try:
        import edge_tts
        import imageio_ffmpeg

        mp3_tmp = output_wav_path.with_suffix(".mp3")

        async def _run_edge() -> None:
            comm = edge_tts.Communicate(
                text=clean_text,
                voice="en-IN-PrabhatNeural",
                rate="+12%",
                pitch="-4Hz",
            )
            await comm.save(str(mp3_tmp))

        asyncio.run(_run_edge())
        if mp3_tmp.exists() and mp3_tmp.stat().st_size > 256:
            ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
            subprocess.run(
                [
                    ffmpeg_exe, "-y", "-i", str(mp3_tmp),
                    "-ar", "24000", "-ac", "1", str(output_wav_path),
                ],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            mp3_tmp.unlink(missing_ok=True)
            return output_wav_path
    except Exception as exc:
        logger.debug("Edge-TTS fallback skipped: %s", exc)

    # Deterministic warm voice-envelope WAV fallback if completely offline
    sr = 24000
    n_samples = int(max(2.0, target_duration_sec) * sr)
    with wave.open(str(output_wav_path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        buf = bytearray(n_samples * 2)
        for i in range(n_samples):
            t = i / float(sr)
            env = 0.35 * (0.5 + 0.5 * math.sin(2 * math.pi * 3.2 * t))
            val = int(4200 * env * (math.sin(2 * math.pi * 135.0 * t) + 0.5 * math.sin(2 * math.pi * 270.0 * t)))
            struct.pack_into("<h", buf, i * 2, max(-32767, min(32767, val)))
        wf.writeframes(buf)
    return output_wav_path


# ==============================================================================
# 2. WORD-LEVEL ALIGNMENT & TIMESTAMPS (`gemini-3.5-transcribe`)
# ==============================================================================
def extract_word_level_timestamps(
    audio_wav_path: Path,
    spoken_text: str,
    duration_sec: float,
    *,
    config: Optional[OmniModelConfig] = None,
    dry_run: bool = False,
) -> List[WordTimestamp]:
    """
    Extracts word-level timestamps using `gemini-3.5-transcribe` (`client.interactions.create`),
    with deterministic proportional syllable/word-boundary alignment fallback.
    """
    cfg = config or OmniModelConfig()
    words = [w for w in re.sub(r"\[350ms pause\]", "", spoken_text).split() if w.strip()]
    if not words:
        return []

    if not dry_run and cfg.api_key and cfg.api_key != "your_gemini_paid_tier1_api_key_here" and audio_wav_path.exists():
        try:
            client = get_genai_client(cfg.api_key)
            aud_b64 = base64.b64encode(audio_wav_path.read_bytes()).decode("utf-8")
            interaction = call_interaction_with_backoff(
                client,
                model=TRANSCRIBE_MODEL,
                input=[
                    {"type": "audio", "data": aud_b64, "mime_type": "audio/wav"},
                    {
                        "type": "text",
                        "text": (
                            "Transcribe this Hinglish audio and return JSON list of objects "
                            "[{\"word\": str, \"start_sec\": float, \"end_sec\": float}]."
                        ),
                    },
                ],
                response_format={"type": "text", "mime_type": "application/json"},
            )
            raw_txt = getattr(interaction, "output_text", None) or ""
            if raw_txt.strip():
                items = json.loads(raw_txt)
                if isinstance(items, list) and items:
                    return [
                        WordTimestamp(
                            word=str(it.get("word", "")),
                            start_sec=float(it.get("start_sec", 0.0)),
                            end_sec=float(it.get("end_sec", 0.2)),
                        )
                        for it in items
                        if it.get("word")
                    ]
        except Exception as exc:
            logger.debug("gemini-3.5-transcribe alignment fell back to proportional timer: %s", exc)

    # Proportional character-weighted word-level timestamp alignment
    total_chars = sum(max(2, len(w)) for w in words)
    cursor = 0.08
    usable_dur = max(1.0, duration_sec - 0.16)
    aligned: List[WordTimestamp] = []
    for w in words:
        w_dur = usable_dur * (max(2, len(w)) / float(total_chars))
        aligned.append(
            WordTimestamp(
                word=w,
                start_sec=round(cursor, 3),
                end_sec=round(cursor + w_dur, 3),
            )
        )
        cursor += w_dur
    return aligned


# ==============================================================================
# 3. SUBTLE DARK-SYNTH SCORE (`lyria-3.5` DUCKED TO -22dB) + WHOOSH/RISER SFX
# ==============================================================================
def generate_lyria_dark_synth_stem(
    output_wav_path: Path,
    duration_sec: float,
    *,
    config: Optional[OmniModelConfig] = None,
    dry_run: bool = False,
) -> Path:
    """
    Generates a low-profile dark-synth Christopher Nolan-meets-Veritasium ambient stem
    via `lyria-3.5` (`client.interactions.create`), or synthesizes a clean analog sub-bass
    dark-synth stem locally.
    """
    if output_wav_path.exists() and output_wav_path.stat().st_size > 2048:
        return output_wav_path

    cfg = config or OmniModelConfig()
    output_wav_path.parent.mkdir(parents=True, exist_ok=True)

    if not dry_run and cfg.api_key and cfg.api_key != "your_gemini_paid_tier1_api_key_here":
        try:
            client = get_genai_client(cfg.api_key)
            interaction = call_interaction_with_backoff(
                client,
                model=MUSIC_LYRIA_MODEL,
                input=LYRIA_DARK_SYNTH_PROMPT,
                response_format={"type": "audio"},
            )
            out_aud = getattr(interaction, "output_audio", None)
            if out_aud and getattr(out_aud, "data", None):
                raw_bytes = (
                    base64.b64decode(out_aud.data)
                    if isinstance(out_aud.data, str)
                    else bytes(out_aud.data)
                )
                tmp_stem = output_wav_path.with_suffix(".lyria_raw")
                tmp_stem.write_bytes(raw_bytes)
                import imageio_ffmpeg
                ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
                subprocess.run(
                    [
                        ffmpeg_exe, "-y", "-stream_loop", "-1", "-i", str(tmp_stem),
                        "-t", f"{duration_sec:.2f}", "-ar", "24000", "-ac", "1", str(output_wav_path),
                    ],
                    check=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
                tmp_stem.unlink(missing_ok=True)
                return output_wav_path
        except Exception as exc:
            logger.info("lyria-3.5 API stem fell back to local Oppenheimer/Veritasium dark-synth engine: %s", exc)

    # Synthesize a non-childish dark-synth ambient stem (deep D2/A2 drone + subtle tension pulse)
    sr = 24000
    n_samples = int(max(3.0, duration_sec) * sr)
    buf = bytearray(n_samples * 2)
    f_root = 73.42   # D2 deep cinematic bass
    f_fifth = 110.0  # A2 warm harmonic fifth
    f_arp = 220.0    # A3 subtle pulse

    for i in range(n_samples):
        t = i / float(sr)
        pulse = 0.65 + 0.35 * math.sin(2.0 * math.pi * 0.5 * t)
        arp_gate = max(0.0, math.sin(2.0 * math.pi * 2.0 * t)) ** 4
        drone = (
            0.55 * math.sin(2.0 * math.pi * f_root * t)
            + 0.30 * math.sin(2.0 * math.pi * f_fifth * t)
            + 0.15 * arp_gate * math.sin(2.0 * math.pi * f_arp * t)
        )
        sample = int(8500 * pulse * drone)
        struct.pack_into("<h", buf, i * 2, max(-32767, min(32767, sample)))

    with wave.open(str(output_wav_path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(buf)
    return output_wav_path


def mix_master_audio_with_ducked_bgm_and_sfx(
    voice_wav_path: Path,
    bgm_wav_path: Path,
    output_master_wav: Path,
    *,
    target_duration_sec: float,
    duck_db: float = -22.0,
    include_transition_sfx: bool = True,
) -> Path:
    """
    Mixes the Hinglish voiceover with the `-22dB` ducked `lyria-3.5` dark-synth stem and
    injects a crisp metallic riser/whoosh SFX at the start of the beat.
    """
    sr = 24000
    n_total = int(max(2.0, target_duration_sec) * sr)

    def _read_pcm16_mono(path: Path) -> List[int]:
        if not path.exists():
            return [0] * n_total
        with wave.open(str(path), "rb") as wf:
            raw = wf.readframes(wf.getnframes())
            count = len(raw) // 2
            samples = list(struct.unpack(f"<{count}h", raw[: count * 2]))
        if len(samples) < n_total:
            samples.extend([0] * (n_total - len(samples)))
        return samples[:n_total]

    v_samples = _read_pcm16_mono(voice_wav_path)
    b_samples = _read_pcm16_mono(bgm_wav_path)

    # -22dB linear amplitude ratio = 10^(-22 / 20) ≈ 0.0794
    duck_gain = math.pow(10.0, duck_db / 20.0)
    out_buf = bytearray(n_total * 2)

    sfx_samples = min(n_total, int(0.42 * sr))  # 420ms transition whoosh/riser

    for i in range(n_total):
        v = v_samples[i]
        # Sidechain ducking: when voice is active, keep BGM strictly at -22dB; slightly lift in pauses
        voice_active = abs(v) > 450
        bgm_mult = duck_gain if voice_active else min(0.18, duck_gain * 1.65)
        b = int(b_samples[i] * bgm_mult)

        sfx = 0
        if include_transition_sfx and i < sfx_samples:
            prog = i / float(sfx_samples)
            freq = 110.0 + 520.0 * (prog ** 1.8)
            env = math.sin(math.pi * prog)
            sfx = int(3200 * env * math.sin(2.0 * math.pi * freq * (i / float(sr))))

        mixed = max(-32767, min(32767, v + b + sfx))
        struct.pack_into("<h", out_buf, i * 2, mixed)

    output_master_wav.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(output_master_wav), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(out_buf)
    return output_master_wav


# ==============================================================================
# 4. SEMI-TRANSPARENT DARK GLASSMORPHIC HUD OVERLAY COMPOSITOR
# ==============================================================================
def render_glassmorphic_hud_beat_card(
    base_frame_path: Path,
    output_frame_path: Path,
    *,
    aspect_ratio: str,
    beat_badge: str,
    headline: str,
    primary_box_title: str,
    primary_box_lines: List[str],
    caption_line: str,
    accent_rgb: Tuple[int, int, int] = (0, 230, 255),
) -> Path:
    """
    Overlays semi-transparent dark glassmorphic HUD cards (for Beat 1 Hook, Beat 2 Concept,
    Beat 3 Formula Vault, Beat 4 CBSE Exam Trap Badge, Beat 5 Gamified Puzzle, and
    Dynamic Highlighted Hinglish Captions) onto a 3D frame.
    """
    w, h = (1920, 1080) if aspect_ratio == "16:9" else (1080, 1920)
    if base_frame_path.exists():
        img = Image.open(base_frame_path).convert("RGBA").resize((w, h), Image.Resampling.LANCZOS)
    else:
        img = Image.new("RGBA", (w, h), (8, 12, 22, 255))

    draw = ImageDraw.Draw(img, "RGBA")
    f_badge = _load_hud_font(24, bold=True)
    f_head = _load_hud_font(38, bold=True)
    f_box_title = _load_hud_font(28, bold=True)
    f_box_line = _load_hud_font(26, bold=False)
    f_cap = _load_hud_font(32, bold=True)

    # Top Glassmorphic Header Banner
    draw.rounded_rectangle(
        [44, 32, w - 44, 142],
        radius=18,
        fill=(8, 14, 26, 218),
        outline=(*accent_rgb, 225),
        width=3,
    )
    draw.text((72, 44), beat_badge.upper()[:70], fill=(*accent_rgb, 255), font=f_badge)
    draw.text((72, 80), headline[:62], fill=(255, 255, 255, 255), font=f_head)

    # Floating Glassmorphic HUD Card (Formula Vault / Exam Sniper Trap / PYQ Puzzle)
    if primary_box_lines:
        card_top = int(h * 0.56) if aspect_ratio == "16:9" else int(h * 0.58)
        card_bot = h - 148
        draw.rounded_rectangle(
            [44, card_top, int(w * 0.64) if aspect_ratio == "16:9" else w - 44, card_bot],
            radius=20,
            fill=(10, 16, 30, 222),
            outline=(*accent_rgb, 210),
            width=3,
        )
        draw.text((72, card_top + 18), primary_box_title.upper()[:58], fill=(255, 215, 55, 255), font=f_box_title)
        y_cursor = card_top + 60
        for line in primary_box_lines[:4]:
            if y_cursor + 34 < card_bot - 10:
                draw.text((72, y_cursor), line[:78], fill=(235, 245, 255, 255), font=f_box_line)
                y_cursor += 38

    # Bottom Dynamic Highlighted Hinglish Caption Bar
    draw.rounded_rectangle(
        [44, h - 122, w - 44, h - 30],
        radius=16,
        fill=(6, 10, 18, 236),
        outline=(255, 215, 55, 230),
        width=2,
    )
    draw.text((72, h - 94), f"[VOICE @jwalashiv]:  {caption_line[:82]}", fill=(255, 242, 130, 255), font=f_cap)

    output_frame_path.parent.mkdir(parents=True, exist_ok=True)
    img.convert("RGB").save(output_frame_path, format="PNG", optimize=True)
    return output_frame_path


def _mux_visual_and_audio_segment(
    video_or_frame_path: Path,
    audio_wav_path: Path,
    output_segment_mp4: Path,
    *,
    duration_sec: float,
    aspect_ratio: str = "16:9",
    fps: int = 24,
) -> Path:
    """Combines a 3D video clip (or HUD keyframe) with its mastered audio into a normalized 24fps MP4 segment."""
    import imageio_ffmpeg

    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    w, h = (1920, 1080) if aspect_ratio == "16:9" else (1080, 1920)
    output_segment_mp4.parent.mkdir(parents=True, exist_ok=True)

    is_video = video_or_frame_path.suffix.lower() in (".mp4", ".mov", ".webm")
    if is_video:
        cmd = [
            ffmpeg_exe, "-y",
            "-stream_loop", "-1", "-i", str(video_or_frame_path),
            "-i", str(audio_wav_path),
            "-vf", f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},format=yuv420p",
            "-map", "0:v:0", "-map", "1:a:0",
            "-t", f"{duration_sec:.2f}",
            "-r", str(fps),
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "20",
            "-c:a", "aac", "-b:a", "192k",
            str(output_segment_mp4),
        ]
    else:
        cmd = [
            ffmpeg_exe, "-y",
            "-loop", "1", "-i", str(video_or_frame_path),
            "-i", str(audio_wav_path),
            "-vf", f"scale={w}:{h},format=yuv420p",
            "-map", "0:v:0", "-map", "1:a:0",
            "-t", f"{duration_sec:.2f}",
            "-r", str(fps),
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "20",
            "-c:a", "aac", "-b:a", "192k",
            str(output_segment_mp4),
        ]
    subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return output_segment_mp4


# ==============================================================================
# 5. YOUTUBE PUBLISH SHEET MARKDOWN & JSON BUNDLE EXPORTER
# ==============================================================================
def write_youtube_publish_bundle(
    blueprint: ChapterVideoBlueprint,
    output_dir: Path,
    credit_estimate: Dict[str, Any],
) -> Tuple[Path, Path]:
    """
    Writes `youtube_seo_package.json` and `youtube_publish_sheet.md` inside
    `output/{class}_{subject}_{chapter}/`.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    seo_json_path = output_dir / "youtube_seo_package.json"
    publish_md_path = output_dir / "youtube_publish_sheet.md"

    payload = {
        "input_spec": blueprint.input_spec.model_dump(),
        "keyword_strategy": blueprint.keyword_strategy.model_dump(),
        "youtube_seo_package": blueprint.youtube_seo_package.model_dump(),
        "thumbnail_variants": [t.model_dump() for t in blueprint.thumbnail_variants],
        "total_planned_duration_sec": blueprint.total_planned_duration_sec,
        "credit_estimate": credit_estimate,
    }
    seo_json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    seo = blueprint.youtube_seo_package
    kw = blueprint.keyword_strategy
    f_vault = blueprint.beat_3_hud_formula_vault
    sniper = blueprint.beat_4_exam_sniper_tip

    md_lines = [
        f"# 🚀 OMNI CREATOR — YouTube Publish Sheet ({blueprint.input_spec.class_level} • {blueprint.input_spec.subject})",
        "",
        f"- **Chapter:** `{blueprint.input_spec.chapter_name}`",
        f"- **Section:** `{blueprint.input_spec.chapter_section}`",
        f"- **Format:** `{blueprint.input_spec.video_format}` (`{blueprint.total_planned_duration_sec}s`)",
        f"- **Primary Focus Keyword:** `{kw.primary_focus_keyword}`",
        f"- **Geo & Language Target:** `{kw.geo_target}`",
        "",
        "---",
        "",
        "## 1. High-CTR Title Variations (`< 60` chars, Primary Keyword Front-Loaded)",
    ]
    for idx, t in enumerate(seo.title_variations, 1):
        md_lines.append(f"{idx}. **`{t}`** *({len(t)} chars)*")

    md_lines.extend(
        [
            "",
            "## 2. A/B 4K Thumbnail Variants (`thumbnails/variant_1..3.png`)",
        ]
    )
    for tv in blueprint.thumbnail_variants:
        md_lines.append(
            f"- **`{tv.variant_id}.png` ({tv.archetype}):** Hook Text `\"{tv.hook_text_max_3_words}\"` | Badge `\"{tv.sub_badge_text}\"`"
        )

    md_lines.extend(
        [
            "",
            "## 3. SEO Description (Copy-Paste Ready)",
            "```text",
            seo.seo_description,
            "```",
            "",
            "## 4. Exact 500-Character YouTube Tag Block",
            f"*(Length: {len(seo.tags_500_chars)} / 500 chars)*",
            "```text",
            seo.tags_500_chars,
            "```",
            "",
            "## 5. Interactive Pinned Comment Quiz (Gamified Engagement Trigger)",
            "```text",
            seo.pinned_comment_quiz,
            "```",
            f"- **Creator Pin Hint / Correct Answer:** {blueprint.beat_5_gamified_engagement.correct_answer_hint_for_pin}",
            "",
            "## 6. 5-Beat Hinglish Pedagogical Script Summary",
            f"### Beat 1 (0:00–0:03): 3-Second Pattern-Interrupt Hook",
            f"- **Visual:** {blueprint.beat_1_pattern_interrupt_hook.visual_macro_3d_prompt}",
            f"- **Spoken Hinglish:** *\"{blueprint.beat_1_pattern_interrupt_hook.spoken_hinglish_hook}\"*",
            "",
            "### Beat 2: Core Concept in 3D Visual Mode (Indian Analogies)",
        ]
    )
    for sc in blueprint.beat_2_simulation_scenes:
        md_lines.append(
            f"- **Scene {sc.scene_id} ({sc.duration_sec}s) — {sc.scene_title}:** "
            f"*Analogy:* {sc.indian_everyday_analogy} | *Spoken:* \"{sc.spoken_hinglish_narration}\""
        )

    md_lines.extend(
        [
            "",
            f"### Beat 3: HUD Formula Vault & Memory Hack ({f_vault.formula_title})",
            f"- **Formula:** `{f_vault.exact_formula_expression}`",
            f"- **SI Units:** {f_vault.si_units_and_variables}",
            f"- **Sign Conventions:** {f_vault.vector_scalar_sign_conventions}",
            f"- **Sticky Hinglish Mnemonic:** *{f_vault.sticky_hinglish_mnemonic}*",
            "",
            f"### Beat 4: Exam Sniper Tip ({sniper.exam_target_badge})",
            f"- **#1 Silly Mistake:** {sniper.number_one_silly_mistake}",
            f"- **NCERT Step-Marking Keywords:** `{', '.join(sniper.exact_ncert_step_marking_keywords)}`",
            f"- **PYQ Competency / Assertion-Reason Angle:** {sniper.pyq_competency_assertion_reason_angle}",
            "",
        ]
    )
    publish_md_path.write_text("\n".join(md_lines), encoding="utf-8")
    return seo_json_path, publish_md_path


# ==============================================================================
# 6. END-TO-END COMPOSITOR & PACKAGER ENTRYPOINT
# ==============================================================================
def run_compositor_and_packager(
    blueprint: ChapterVideoBlueprint,
    *,
    visual_bundle: Optional[Visual3DBundle] = None,
    config: Optional[OmniModelConfig] = None,
    dry_run: bool = False,
) -> OmniProductionOutput:
    """
    Executes Module E (`compositor_and_packager.py`):
    - Generates A/B 4K thumbnails (`thumbnails/variant_1..3.png`)
    - Exports `youtube_seo_package.json` and `youtube_publish_sheet.md`
    - When `dry_run=False`, synthesizes all 5 beats of Hinglish narration (`gemini-3.8-flash-tts`),
      word-level timestamps (`gemini-3.5-transcribe`), `-22dB` ducked `lyria-3.5` dark-synth stem,
      semi-transparent glassmorphic HUD overlays, and renders `final_video_4k.mp4`.
    """
    cfg = config or OmniModelConfig()
    folder_slug = (
        f"{_sanitize_slug(blueprint.input_spec.class_level)}_"
        f"{_sanitize_slug(blueprint.input_spec.subject)}_"
        f"{_sanitize_slug(blueprint.input_spec.chapter_name)}"
    )
    bundle_dir = cfg.output_dir / folder_slug
    thumbs_dir = bundle_dir / "thumbnails"
    work_dir = cfg.cache_dir / "compositor" / folder_slug
    bundle_dir.mkdir(parents=True, exist_ok=True)
    thumbs_dir.mkdir(parents=True, exist_ok=True)
    work_dir.mkdir(parents=True, exist_ok=True)

    credit_report = estimate_pipeline_credits(
        num_scenes=len(blueprint.beat_2_simulation_scenes) + 3,
        total_duration_sec=blueprint.total_planned_duration_sec,
        num_thumbnails=3,
        resolution=cfg.default_resolution,
        dry_run=dry_run,
    )

    # 1. Generate 3 A/B 4K Thumbnails (Module D)
    thumb_paths = generate_ab_thumbnail_suite(
        blueprint,
        output_thumbnails_dir=thumbs_dir,
        config=cfg,
        dry_run=dry_run,
    )

    # 2. Write YouTube SEO Package JSON + Markdown Publish Sheet
    seo_json_path, publish_md_path = write_youtube_publish_bundle(
        blueprint,
        output_dir=bundle_dir,
        credit_estimate=credit_report,
    )

    if dry_run:
        # In --dry-run mode, generate keyframes and metadata without spending video credits
        generate_all_3d_visuals_for_blueprint(
            blueprint,
            config=cfg,
            dry_run=True,
            render_preview_clips_in_dry_run=False,
        )
        return OmniProductionOutput(
            bundle_dir=bundle_dir,
            final_video_path=None,
            thumbnail_paths=thumb_paths,
            seo_json_path=seo_json_path,
            publish_sheet_md_path=publish_md_path,
            credit_estimate=credit_report,
            dry_run=True,
            word_timestamps_count=0,
        )

    # 3. Ensure 3D Visual Keyframes & Clips are generated (Module C)
    v_bundle = visual_bundle or generate_all_3d_visuals_for_blueprint(
        blueprint,
        config=cfg,
        dry_run=False,
        render_preview_clips_in_dry_run=True,
    )

    aspect = blueprint.input_spec.aspect_ratio
    total_dur = blueprint.total_planned_duration_sec
    bgm_stem_path = generate_lyria_dark_synth_stem(
        work_dir / "lyria_dark_synth_stem.wav",
        duration_sec=total_dur + 10.0,
        config=cfg,
        dry_run=False,
    )

    segment_mp4s: List[Path] = []
    all_word_timestamps: List[WordTimestamp] = []

    # --- BEAT 1: 0:00-0:03 PATTERN-INTERRUPT HOOK ---
    b1 = blueprint.beat_1_pattern_interrupt_hook
    b1_dur = max(3.0, b1.end_sec - b1.start_sec)
    b1_voice = synthesize_hinglish_narration_segment(
        b1.spoken_hinglish_hook,
        work_dir / "beat1_hook_voice.wav",
        target_duration_sec=b1_dur,
        config=cfg,
    )
    all_word_timestamps.extend(extract_word_level_timestamps(b1_voice, b1.spoken_hinglish_hook, b1_dur, config=cfg))
    b1_master_aud = mix_master_audio_with_ducked_bgm_and_sfx(
        b1_voice, bgm_stem_path, work_dir / "beat1_hook_master.wav",
        target_duration_sec=b1_dur, duck_db=cfg.bgm_duck_db, include_transition_sfx=True,
    )
    b1_hud_frame = render_glassmorphic_hud_beat_card(
        v_bundle.hook_assets.start_keyframe_path,
        work_dir / "beat1_hook_hud.png",
        aspect_ratio=aspect,
        beat_badge="0:00-0:03 • PATTERN-INTERRUPT 3D HOOK",
        headline=b1.on_screen_hud_callout,
        primary_box_title=f"PRIMARY FOCUS: {blueprint.keyword_strategy.primary_focus_keyword}",
        primary_box_lines=[b1.spoken_hinglish_hook[:75], b1.spoken_hinglish_hook[75:150]],
        caption_line=b1.spoken_hinglish_hook,
        accent_rgb=(255, 75, 95),
    )
    b1_clip = render_smooth_24fps_3d_clip_from_keyframes(
        b1_hud_frame, None, work_dir / "beat1_hook_visual.mp4",
        duration_sec=b1_dur, aspect_ratio=aspect, fps=cfg.default_fps,
    )
    segment_mp4s.append(
        _mux_visual_and_audio_segment(
            b1_clip, b1_master_aud, work_dir / "seg_01_hook.mp4",
            duration_sec=b1_dur, aspect_ratio=aspect, fps=cfg.default_fps,
        )
    )

    # --- BEAT 2: CORE CONCEPT IN 3D VISUAL MODE (SCENES 1..N) ---
    for idx, sc in enumerate(blueprint.beat_2_simulation_scenes):
        sc_asset = v_bundle.scene_assets[idx]
        v_wav = synthesize_hinglish_narration_segment(
            sc.spoken_hinglish_narration,
            work_dir / f"beat2_s{sc.scene_id:02d}_voice.wav",
            target_duration_sec=sc.duration_sec,
            config=cfg,
        )
        all_word_timestamps.extend(
            extract_word_level_timestamps(v_wav, sc.spoken_hinglish_narration, sc.duration_sec, config=cfg)
        )
        m_wav = mix_master_audio_with_ducked_bgm_and_sfx(
            v_wav, bgm_stem_path, work_dir / f"beat2_s{sc.scene_id:02d}_master.wav",
            target_duration_sec=sc.duration_sec, duck_db=cfg.bgm_duck_db, include_transition_sfx=(idx == 0),
        )
        hud_start = render_glassmorphic_hud_beat_card(
            sc_asset.start_keyframe_path,
            work_dir / f"beat2_s{sc.scene_id:02d}_hud_start.png",
            aspect_ratio=aspect,
            beat_badge=f"3D VISUAL SIMULATION • SCENE {sc.scene_id} • {sc.hud_overlay_label}",
            headline=sc.scene_title,
            primary_box_title="INDIAN ANALOGY & 3D CAUSE-EFFECT",
            primary_box_lines=[
                f"Analogy: {sc.indian_everyday_analogy[:70]}",
                f"Formula Lock: {blueprint.beat_3_hud_formula_vault.exact_formula_expression}",
            ],
            caption_line=sc.spoken_hinglish_narration,
            accent_rgb=(0, 230, 255),
        )
        hud_end: Optional[Path] = None
        if sc_asset.end_keyframe_path and sc_asset.end_keyframe_path.exists():
            hud_end = render_glassmorphic_hud_beat_card(
                sc_asset.end_keyframe_path,
                work_dir / f"beat2_s{sc.scene_id:02d}_hud_end.png",
                aspect_ratio=aspect,
                beat_badge=f"3D PHASE TRANSITION • SCENE {sc.scene_id}",
                headline=sc.scene_title,
                primary_box_title="NCERT KEYWORD & VECTOR LOCK",
                primary_box_lines=[
                    f"Key Concept: {blueprint.beat_4_exam_sniper_tip.exact_ncert_step_marking_keywords[0]}",
                    f"Mid-Roll Check: {blueprint.beat_5_gamified_engagement.mid_roll_micro_check_hinglish[:68]}",
                ],
                caption_line=sc.spoken_hinglish_narration[len(sc.spoken_hinglish_narration) // 2 :],
                accent_rgb=(255, 200, 45),
            )
        sc_vis_mp4 = render_smooth_24fps_3d_clip_from_keyframes(
            hud_start, hud_end, work_dir / f"beat2_s{sc.scene_id:02d}_vis.mp4",
            duration_sec=sc.duration_sec, aspect_ratio=aspect, fps=cfg.default_fps,
        )
        segment_mp4s.append(
            _mux_visual_and_audio_segment(
                sc_vis_mp4, m_wav, work_dir / f"seg_02_scene_{sc.scene_id:02d}.mp4",
                duration_sec=sc.duration_sec, aspect_ratio=aspect, fps=cfg.default_fps,
            )
        )

    # --- BEAT 3: HUD FORMULA VAULT & MEMORY HACK ---
    b3 = blueprint.beat_3_hud_formula_vault
    b3_base = render_dark_obsidian_3d_keyframe(
        work_dir / "beat3_formula_base.png",
        subject=blueprint.input_spec.subject,
        chapter_name=blueprint.input_spec.chapter_name,
        scene_title=b3.formula_title,
        hud_label="BEAT 3 • HUD FORMULA VAULT",
        formula_expr=b3.exact_formula_expression,
        aspect_ratio=aspect,
        phase=2.4,
    )
    b3_hud = render_glassmorphic_hud_beat_card(
        b3_base,
        work_dir / "beat3_formula_hud.png",
        aspect_ratio=aspect,
        beat_badge="HUD FORMULA VAULT & TOPPER MEMORY HACK",
        headline=b3.formula_title,
        primary_box_title=f"EXACT FORMULA:  {b3.exact_formula_expression}",
        primary_box_lines=[
            f"SI Units: {b3.si_units_and_variables[:72]}",
            f"Sign Rule: {b3.vector_scalar_sign_conventions[:72]}",
            f"Memory Hack: {b3.sticky_hinglish_mnemonic[:72]}",
        ],
        caption_line=b3.spoken_hinglish_explanation,
        accent_rgb=(255, 210, 45),
    )
    b3_voice = synthesize_hinglish_narration_segment(
        b3.spoken_hinglish_explanation,
        work_dir / "beat3_formula_voice.wav",
        target_duration_sec=b3.duration_sec,
        config=cfg,
    )
    all_word_timestamps.extend(extract_word_level_timestamps(b3_voice, b3.spoken_hinglish_explanation, b3.duration_sec, config=cfg))
    b3_master = mix_master_audio_with_ducked_bgm_and_sfx(
        b3_voice, bgm_stem_path, work_dir / "beat3_formula_master.wav",
        target_duration_sec=b3.duration_sec, duck_db=cfg.bgm_duck_db, include_transition_sfx=True,
    )
    segment_mp4s.append(
        _mux_visual_and_audio_segment(
            b3_hud, b3_master, work_dir / "seg_03_formula_vault.mp4",
            duration_sec=b3.duration_sec, aspect_ratio=aspect, fps=cfg.default_fps,
        )
    )

    # --- BEAT 4: EXAM SNIPER TIP (CBSE BOARDS / JEE / NEET) ---
    b4 = blueprint.beat_4_exam_sniper_tip
    b4_base = render_dark_obsidian_3d_keyframe(
        work_dir / "beat4_sniper_base.png",
        subject=blueprint.input_spec.subject,
        chapter_name=blueprint.input_spec.chapter_name,
        scene_title=b4.exam_target_badge,
        hud_label="BEAT 4 • EXAM SNIPER TRAP",
        formula_expr=b3.exact_formula_expression,
        aspect_ratio=aspect,
        phase=3.6,
    )
    b4_hud = render_glassmorphic_hud_beat_card(
        b4_base,
        work_dir / "beat4_sniper_hud.png",
        aspect_ratio=aspect,
        beat_badge=f"EXAM SNIPER ALERT • {b4.exam_target_badge}",
        headline="#1 Silly Mistake & NCERT Step-Marking Keywords",
        primary_box_title="EXAMINER STEP-MARKING CHECKLIST",
        primary_box_lines=[
            f"Trap Warning: {b4.number_one_silly_mistake[:70]}",
            f"NCERT Keywords: {', '.join(b4.exact_ncert_step_marking_keywords[:3])[:70]}",
            f"PYQ Twist: {b4.pyq_competency_assertion_reason_angle[:70]}",
        ],
        caption_line=b4.spoken_hinglish_sniper_warning,
        accent_rgb=(255, 85, 95),
    )
    b4_voice = synthesize_hinglish_narration_segment(
        b4.spoken_hinglish_sniper_warning,
        work_dir / "beat4_sniper_voice.wav",
        target_duration_sec=b4.duration_sec,
        config=cfg,
    )
    all_word_timestamps.extend(extract_word_level_timestamps(b4_voice, b4.spoken_hinglish_sniper_warning, b4.duration_sec, config=cfg))
    b4_master = mix_master_audio_with_ducked_bgm_and_sfx(
        b4_voice, bgm_stem_path, work_dir / "beat4_sniper_master.wav",
        target_duration_sec=b4.duration_sec, duck_db=cfg.bgm_duck_db, include_transition_sfx=True,
    )
    segment_mp4s.append(
        _mux_visual_and_audio_segment(
            b4_hud, b4_master, work_dir / "seg_04_exam_sniper.mp4",
            duration_sec=b4.duration_sec, aspect_ratio=aspect, fps=cfg.default_fps,
        )
    )

    # --- BEAT 5: GAMIFIED ENGAGEMENT TRIGGER (10s PYQ PUZZLE OUTRO) ---
    b5 = blueprint.beat_5_gamified_engagement
    b5_base = render_dark_obsidian_3d_keyframe(
        work_dir / "beat5_puzzle_base.png",
        subject=blueprint.input_spec.subject,
        chapter_name=blueprint.input_spec.chapter_name,
        scene_title="10-SECOND PYQ BRAIN-TEASER CHALLENGE!",
        hud_label="BEAT 5 • COMMENT & WIN PIN!",
        formula_expr=b3.exact_formula_expression,
        aspect_ratio=aspect,
        phase=4.8,
    )
    b5_hud = render_glassmorphic_hud_beat_card(
        b5_base,
        work_dir / "beat5_puzzle_hud.png",
        aspect_ratio=aspect,
        beat_badge="GAMIFIED PYQ CHALLENGE • PAUSE & COMMENT NOW!",
        headline="Fastest Correct Answer Gets Heart + Pinned!",
        primary_box_title="CHOOSE YOUR ANSWER (A / B / C / D):",
        primary_box_lines=b5.options_hud[:4],
        caption_line=b5.outro_10s_tricky_pyq_puzzle,
        accent_rgb=(50, 255, 175),
    )
    b5_voice = synthesize_hinglish_narration_segment(
        b5.outro_10s_tricky_pyq_puzzle,
        work_dir / "beat5_puzzle_voice.wav",
        target_duration_sec=b5.duration_sec,
        config=cfg,
    )
    all_word_timestamps.extend(extract_word_level_timestamps(b5_voice, b5.outro_10s_tricky_pyq_puzzle, b5.duration_sec, config=cfg))
    b5_master = mix_master_audio_with_ducked_bgm_and_sfx(
        b5_voice, bgm_stem_path, work_dir / "beat5_puzzle_master.wav",
        target_duration_sec=b5.duration_sec, duck_db=cfg.bgm_duck_db, include_transition_sfx=True,
    )
    segment_mp4s.append(
        _mux_visual_and_audio_segment(
            b5_hud, b5_master, work_dir / "seg_05_gamified_outro.mp4",
            duration_sec=b5.duration_sec, aspect_ratio=aspect, fps=cfg.default_fps,
        )
    )

    # Concatenate all 5 beat segments into `final_video_4k.mp4`
    import imageio_ffmpeg
    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    concat_txt = work_dir / "concat_segments.txt"
    concat_txt.write_text(
        "\n".join(f"file '{p.resolve().as_posix()}'" for p in segment_mp4s),
        encoding="utf-8",
    )
    final_video_path = bundle_dir / "final_video_4k.mp4"
    subprocess.run(
        [
            ffmpeg_exe, "-y",
            "-f", "concat", "-safe", "0",
            "-i", str(concat_txt),
            "-c", "copy",
            str(final_video_path),
        ],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    # Save word-level alignment manifest alongside SEO package
    alignment_path = bundle_dir / "word_timestamps.json"
    alignment_path.write_text(
        json.dumps([w.__dict__ for w in all_word_timestamps], indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    return OmniProductionOutput(
        bundle_dir=bundle_dir,
        final_video_path=final_video_path,
        thumbnail_paths=thumb_paths,
        seo_json_path=seo_json_path,
        publish_sheet_md_path=publish_md_path,
        credit_estimate=credit_report,
        dry_run=False,
        word_timestamps_count=len(all_word_timestamps),
    )
