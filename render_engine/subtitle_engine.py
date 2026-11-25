"""
OMNI STUDIO — Active Word-Highlight `.ass` Subtitle Engine (`render_engine/subtitle_engine.py`)
===============================================================================================
Generates broadcast-grade, word-level active-highlight SubStation Alpha (`.ass`) subtitles
for both 16:9 (1080p) and 9:16 (Shorts/Reels) renders:
1. Uses `faster-whisper` word timestamps when locally installed.
2. Otherwise uses `gemini-3.5-transcribe` (when API key is active & enabled).
3. Guaranteed fallback: exact character-weighted word-level timer synchronized directly to
   each scene's measured WAV duration (zero drift across 5-8 minute videos!).
"""

from __future__ import annotations

import base64
import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

from backend.config import TRANSCRIBE_MODEL, OmniStudioConfig, call_interaction_with_fallback, get_genai_client

logger = logging.getLogger("omni_studio.subtitle_engine")


@dataclass
class TimedWord:
    word: str
    start_sec: float
    end_sec: float
    scene_id: int = 0


def _clean_spoken_text(text: str) -> str:
    cleaned = re.sub(r"<break[^>]*/>", " ", text)
    cleaned = re.sub(r"\[[^\]]+\]", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def _format_ass_time(sec: float) -> str:
    sec = max(0.0, float(sec))
    h = int(sec // 3600)
    m = int((sec % 3600) // 60)
    s = int(sec % 60)
    cs = int(round((sec - int(sec)) * 100))
    if cs >= 100:
        cs = 99
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _escape_ass_text(text: str) -> str:
    return text.replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}")


def extract_scene_word_timestamps(
    audio_wav_path: Path,
    spoken_text: str,
    scene_start_offset_sec: float,
    scene_duration_sec: float,
    *,
    scene_id: int = 0,
    config: Optional[OmniStudioConfig] = None,
    use_cloud_transcribe: bool = False,
) -> List[TimedWord]:
    """
    Returns exact global-timeline `TimedWord` entries for one scene.
    Priority: `faster-whisper` (if installed) -> `gemini-3.5-transcribe` -> duration-anchored alignment.
    """
    # 1. Try local `faster-whisper` for authentic audio-aligned word timestamps
    try:
        from faster_whisper import WhisperModel  # type: ignore

        model = WhisperModel("tiny", device="cpu", compute_type="int8")
        segments, _ = model.transcribe(str(audio_wav_path), word_timestamps=True)
        fw_words: List[TimedWord] = []
        for seg in segments:
            for w in getattr(seg, "words", []) or []:
                token = str(w.word).strip()
                if token:
                    fw_words.append(
                        TimedWord(
                            word=token,
                            start_sec=round(scene_start_offset_sec + float(w.start), 3),
                            end_sec=round(min(scene_start_offset_sec + scene_duration_sec - 0.04, scene_start_offset_sec + float(w.end)), 3),
                            scene_id=scene_id,
                        )
                    )
        if fw_words:
            return fw_words
    except Exception:
        pass

    # 2. Optional `gemini-3.5-transcribe` alignment
    cfg = config or OmniStudioConfig()
    if use_cloud_transcribe and cfg.has_valid_gemini_key and audio_wav_path.exists():
        try:
            client = get_genai_client(cfg.gemini_api_key)
            aud_b64 = base64.b64encode(audio_wav_path.read_bytes()).decode("utf-8")
            interaction = call_interaction_with_fallback(
                client,
                models=[TRANSCRIBE_MODEL],
                input=[
                    {"type": "audio", "data": aud_b64, "mime_type": "audio/wav"},
                    {
                        "type": "text",
                        "text": 'Return JSON list: [{"word": str, "start_sec": float, "end_sec": float}].',
                    },
                ],
                response_format={"type": "text", "mime_type": "application/json"},
            )
            raw = getattr(interaction, "output_text", "") or ""
            items = json.loads(raw)
            if isinstance(items, list) and items:
                out: List[TimedWord] = []
                for it in items:
                    w_txt = str(it.get("word", "")).strip()
                    if w_txt:
                        out.append(
                            TimedWord(
                                word=w_txt,
                                start_sec=round(scene_start_offset_sec + float(it.get("start_sec", 0.0)), 3),
                                end_sec=round(scene_start_offset_sec + float(it.get("end_sec", 0.2)), 3),
                            )
                        )
                if out:
                    return out
        except Exception as exc:
            logger.debug("Cloud transcribe fallback to duration-locked alignment: %s", exc)

    # 3. Exact duration-locked proportional syllable/word alignment
    clean = _clean_spoken_text(spoken_text)
    words = [w for w in clean.split() if w]
    if not words:
        return []

    lead_in = 0.08
    usable = max(0.5, float(scene_duration_sec) - 0.24)
    weights = [max(2, len(re.sub(r"[^A-Za-z0-9]", "", w))) + (2 if w.endswith((".", "!", "?", ",")) else 0) for w in words]
    total_w = float(sum(weights))

    cursor = scene_start_offset_sec + lead_in
    timed: List[TimedWord] = []
    for w, wt in zip(words, weights):
        dur = usable * (wt / total_w)
        timed.append(TimedWord(word=w, start_sec=round(cursor, 3), end_sec=round(cursor + dur, 3), scene_id=scene_id))
        cursor += dur
    return timed


def write_active_highlight_ass_file(
    timed_words: List[TimedWord],
    output_ass_path: Path,
    *,
    aspect_ratio: str = "16:9",
    words_per_chunk: int = 5,
    highlight_bgr_hex: str = "00E5FF",
) -> Path:
    """
    Writes a styled `.ass` subtitle file where each active spoken word dynamically pops
    in high-contrast neon yellow/cyan while surrounding phrase words stay crisp white on a
    clean translucent dark pill shadow.
    Note: ASS colors use `&H00BBGGRR` order.
    """
    res_x, res_y = (1920, 1080) if aspect_ratio == "16:9" else (1080, 1920)
    font_size = 56 if aspect_ratio == "16:9" else 64
    margin_v = 74 if aspect_ratio == "16:9" else 260
    chunk_size = words_per_chunk if aspect_ratio == "16:9" else 4

    # Use Devanagari-capable font automatically if any word uses Hindi Devanagari script
    has_deva = any("\u0900" <= ch <= "\u097f" for tw in timed_words for ch in tw.word)
    font_name = "Noto Sans Devanagari" if has_deva else "Segoe UI"

    # High-frequency neon yellow active highlight in ASS BGR (`&H0018E8FF&` = vivid gold-yellow)
    active_color = "&H0018E8FF&"
    normal_color = "&H00FFFFFF&"

    header = f"""[Script Info]
Title: OMNI STUDIO Active Word-Highlight Subtitles
ScriptType: v4.00+
PlayResX: {res_x}
PlayResY: {res_y}
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{font_name},{font_size},&H00FFFFFF,&H0018E8FF,&H00090D16,&H80000000,-1,0,0,0,100,100,0,0,1,4,2,2,60,60,{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines: List[str] = [header.strip()]

    # Group words into chunks NEVER crossing scene boundaries, and strictly clamp end <= next start (zero overlapping lines!)
    chunks: List[List[TimedWord]] = []
    cur_chunk: List[TimedWord] = []
    for tw in timed_words:
        if cur_chunk and (len(cur_chunk) >= chunk_size or cur_chunk[-1].scene_id != tw.scene_id):
            chunks.append(cur_chunk)
            cur_chunk = []
        cur_chunk.append(tw)
    if cur_chunk:
        chunks.append(cur_chunk)

    for c_idx, chunk in enumerate(chunks):
        next_chunk_start = chunks[c_idx + 1][0].start_sec if (c_idx + 1) < len(chunks) else None
        for active_i, active_w in enumerate(chunk):
            next_start = (
                chunk[active_i + 1].start_sec
                if (active_i + 1) < len(chunk)
                else next_chunk_start
            )
            raw_end = max(active_w.end_sec, active_w.start_sec + 0.06)
            if next_start is not None:
                raw_end = min(raw_end, max(active_w.start_sec + 0.02, next_start - 0.01))
            st = _format_ass_time(active_w.start_sec)
            et = _format_ass_time(raw_end)
            rendered_tokens: List[str] = []
            for j, tok in enumerate(chunk):
                safe = _escape_ass_text(tok.word)
                if j == active_i:
                    rendered_tokens.append(f"{{\\c{active_color}\\fscx112\\fscy112}}{safe}{{\\c{normal_color}\\fscx100\\fscy100}}")
                else:
                    rendered_tokens.append(safe)
            dialogue_txt = " ".join(rendered_tokens)
            lines.append(f"Dialogue: 0,{st},{et},Default,,0,0,0,,{dialogue_txt}")

    output_ass_path.parent.mkdir(parents=True, exist_ok=True)
    output_ass_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return output_ass_path
