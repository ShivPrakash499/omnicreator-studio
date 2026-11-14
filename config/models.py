"""
OMNI CREATOR — Central Model & API Stack Configuration (Paid Tier 1 / Ultra Models Only)
========================================================================================
Uses the official `google-genai` SDK (`from google import genai`) and `client.interactions.create(...)`
across all generation modalities.

STRICT MODEL POLICY:
- Curriculum, Script, Exam-Tips & SEO Frontier Brain: `gemini-4-carbon` (fallback: `gemini-4-argon`)
  with `google_search` grounding enabled.
- Orchestrator & Pydantic Schema Validator: `gemini-4-hydrogen` (thinking_level="high")
  with automatic fallback to `gemini-4-argon`.
- 4K Thumbnails & 3D Start/End Keyframes: `gemini-3-pro-image` and `gemini-nano-banana-2.1`
  for multi-turn scene/object continuity across consecutive shots.
- Ultra-Realistic 3D Video Simulation Engine: `gemini-omni-1.2-flash` via `client.interactions.create(...)`
  (NEVER use deprecated `veo-2.0` or `veo-3.1-preview` endpoints).
- Expressive Hinglish Narration: `gemini-3.8-flash-tts` configured for a sharp, charismatic
  24-28 yr old Indian "Cool Senior / Mentor" (@jwalashiv) voice.
- Word-Level Alignment & Transcription: `gemini-3.5-transcribe`.
- Subtle Background Score: `lyria-3.5` low-profile dark-synth / Christopher Nolan-meets-Veritasium
  ambient stems (ducked to -22dB under voiceover).
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

from google import genai

logger = logging.getLogger("omni_creator.models")

# ==============================================================================
# 1. PAID TIER 1 / ULTRA MODEL IDENTIFIERS
# ==============================================================================
FRONTIER_BRAIN_MODEL: str = "gemini-4-carbon"
FRONTIER_BRAIN_FALLBACK_MODEL: str = "gemini-4-argon"

ORCHESTRATOR_MODEL: str = "gemini-4-hydrogen"
ORCHESTRATOR_FALLBACK_MODEL: str = "gemini-4-argon"

IMAGE_4K_PRO_MODEL: str = "gemini-3-pro-image"
IMAGE_CONTINUITY_MODEL: str = "gemini-nano-banana-2.1"

VIDEO_OMNI_MODEL: str = "gemini-omni-1.2-flash"

TTS_EXPRESSIVE_MODEL: str = "gemini-3.8-flash-tts"
TRANSCRIBE_MODEL: str = "gemini-3.5-transcribe"
MUSIC_LYRIA_MODEL: str = "lyria-3.5"

# ==============================================================================
# 2. GLOBAL NON-KIDDISH 3D VISUAL & AUDIO AESTHETIC RULES (CLASSES 9-12)
# ==============================================================================
GLOBAL_3D_SCIENCE_STYLE_PROMPT: str = (
    "Photorealistic Unreal Engine 5 and Octane Render 3D scientific cinema, "
    "macro-lens optical physics (f/1.8 shallow depth of field with crisp focal plane), "
    "dark obsidian and brushed-titanium laboratory environment, dramatic volumetric rim lighting, "
    "glowing holographic glassmorphic HUD data callouts with razor-sharp typography, "
    "hyper-detailed subatomic, molecular, optical, or anatomical 3D cross-sections "
    "inspired by Veritasium, Melodysheep, and 3Blue1Brown, 8K textures, physically based rendering (PBR)."
)

GLOBAL_NEGATIVE_CONSTRAINTS: str = (
    "HARD BAN / DO NOT INCLUDE: NO 2D kiddish cartoons, NO chibi or Pixar toy mascots, "
    "NO bright nursery pastel backgrounds, NO clipart chalkboard drawings, "
    "NO childish flat vector illustrations, NO deformed text, NO blurry watermarks."
)

HINGLISH_VOICE_STYLE_PROMPT: str = (
    "Sharp, charismatic 24 to 28 year old Indian 'Cool Senior / IIT-AIIMS Mentor' (@jwalashiv persona). "
    "Energetic, conversational Hinglish delivery at 1.12x natural brisk pace, crisp and authoritative "
    "pronunciation of standard English NCERT scientific terms, units, and formulas, "
    "with a dramatic 350ms pause right before hooks, plot twists, and key exam formulas. "
    "Zero robotic textbook tone."
)

LYRIA_DARK_SYNTH_PROMPT: str = (
    "Low-profile dark-synth ambient documentary score inspired by Christopher Nolan (Oppenheimer / Tenet) "
    "and Veritasium. Deep sub-bass pulse, subtle analog warm arpeggio, tension-building minimalist "
    "cinematic textures, strictly instrumental, no vocals, clean midrange for -22dB voiceover ducking."
)

# ==============================================================================
# 3. GOOGLE ADS / KEYWORD PLANNER GEO & LANGUAGE CONSTANTS
# ==============================================================================
GOOGLE_ADS_GEO_INDIA: str = "2356"          # India Geo Target Constant
GOOGLE_ADS_LANG_ENGLISH: str = "1000"       # English Language Constant
GOOGLE_ADS_LANG_HINDI: str = "1023"         # Hindi Language Constant

# ==============================================================================
# 4. CENTRAL SDK CLIENT & RETRY / BACKOFF CONFIG
# ==============================================================================
@dataclass
class OmniModelConfig:
    """Central runtime configuration for Omni Creator modules."""
    api_key: str = field(default_factory=lambda: os.getenv("GEMINI_API_KEY", ""))
    project_id: str = field(default_factory=lambda: os.getenv("GOOGLE_CLOUD_PROJECT", "gen-lang-client-0777980903"))
    default_resolution: str = field(default_factory=lambda: os.getenv("OMNI_DEFAULT_RESOLUTION", "4k"))
    default_fps: int = field(default_factory=lambda: int(os.getenv("OMNI_DEFAULT_FPS", "24")))
    bgm_duck_db: float = field(default_factory=lambda: float(os.getenv("OMNI_BGM_DUCK_DB", "-22.0")))
    cache_dir: Path = field(default_factory=lambda: Path(os.getenv("OMNI_CACHE_DIR", "workspaces/omni_cache")))
    output_dir: Path = field(default_factory=lambda: Path(os.getenv("OMNI_OUTPUT_DIR", "output")))
    max_retries: int = 4
    base_backoff_sec: float = 2.0
    max_backoff_sec: float = 32.0

    def __post_init__(self) -> None:
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.output_dir.mkdir(parents=True, exist_ok=True)


def get_genai_client(api_key: Optional[str] = None) -> genai.Client:
    """Returns an initialized `google.genai.Client` for Interactions API calls."""
    resolved_key = api_key or os.getenv("GEMINI_API_KEY", "").strip()
    if resolved_key:
        return genai.Client(api_key=resolved_key)
    return genai.Client()


def compute_content_sha256(*parts: Any) -> str:
    """Computes a deterministic SHA-256 hex digest across prompt/model/config parameters for local caching."""
    hasher = hashlib.sha256()
    for part in parts:
        if isinstance(part, (bytes, bytearray)):
            hasher.update(part)
        else:
            hasher.update(str(part).encode("utf-8"))
        hasher.update(b"||")
    return hasher.hexdigest()


def call_interaction_with_backoff(
    client: genai.Client,
    *,
    model: str,
    fallback_model: Optional[str] = None,
    max_retries: int = 4,
    base_delay: float = 2.0,
    **interaction_kwargs: Any,
) -> Any:
    """
    Executes `client.interactions.create(...)` with exponential backoff for Tier 1 rate limits
    (HTTP 429 / 503 / ResourceExhausted) and automatic fallback model support.
    """
    models_to_try: List[str] = [model]
    if fallback_model and fallback_model not in models_to_try:
        models_to_try.append(fallback_model)

    last_exc: Optional[Exception] = None
    for active_model in models_to_try:
        for attempt in range(1, max_retries + 1):
            try:
                return client.interactions.create(
                    model=active_model,
                    **interaction_kwargs,
                )
            except Exception as exc:
                last_exc = exc
                err_str = str(exc).lower()
                is_model_not_found = (
                    "not found" in err_str
                    or "404" in err_str
                    or "invalid model" in err_str
                    or "not supported" in err_str
                )
                if is_model_not_found and active_model != models_to_try[-1]:
                    logger.warning(
                        "Model '%s' unavailable (%s); switching immediately to fallback '%s'.",
                        active_model,
                        exc,
                        models_to_try[-1],
                    )
                    break

                if attempt < max_retries:
                    sleep_sec = min(32.0, base_delay * (2 ** (attempt - 1)))
                    logger.warning(
                        "[Tier-1 Retry %d/%d] %s failed (%s). Backing off %.1fs...",
                        attempt,
                        max_retries,
                        active_model,
                        exc,
                        sleep_sec,
                    )
                    time.sleep(sleep_sec)
                else:
                    logger.error("Exhausted %d retries for model '%s': %s", max_retries, active_model, exc)

    if last_exc is not None:
        raise last_exc
    raise RuntimeError("Interaction call failed without exception details.")


async def async_call_interaction_with_backoff(
    client: genai.Client,
    *,
    model: str,
    fallback_model: Optional[str] = None,
    max_retries: int = 4,
    base_delay: float = 2.0,
    **interaction_kwargs: Any,
) -> Any:
    """Async wrapper around `call_interaction_with_backoff` for concurrent keyframe/clip generation."""
    return await asyncio.to_thread(
        call_interaction_with_backoff,
        client,
        model=model,
        fallback_model=fallback_model,
        max_retries=max_retries,
        base_delay=base_delay,
        **interaction_kwargs,
    )


def estimate_pipeline_credits(
    num_scenes: int,
    total_duration_sec: float,
    num_thumbnails: int = 3,
    resolution: str = "4k",
    dry_run: bool = False,
) -> Dict[str, Any]:
    """
    Computes an itemised Paid Tier 1 API credit & USD cost estimation prior to invoking
    heavy `gemini-omni-1.2-flash` 4K video generation.
    """
    keyframes_count = num_scenes * 2  # Start + End / Continuity frames
    res_multiplier = 1.6 if resolution.lower() == "4k" else 1.0

    cost_frontier_seo_script = 0.045
    cost_orchestrator_validation = 0.015
    cost_keyframes_usd = round(keyframes_count * 0.04 * res_multiplier, 3)
    cost_thumbnails_usd = round(num_thumbnails * 0.05 * res_multiplier, 3)
    cost_omni_video_usd = 0.0 if dry_run else round(total_duration_sec * 0.12 * res_multiplier, 3)
    cost_tts_transcribe_usd = round((total_duration_sec / 60.0) * 0.03, 3)
    cost_lyria_bgm_usd = 0.04

    total_usd = round(
        cost_frontier_seo_script
        + cost_orchestrator_validation
        + cost_keyframes_usd
        + cost_thumbnails_usd
        + cost_omni_video_usd
        + cost_tts_transcribe_usd
        + cost_lyria_bgm_usd,
        3,
    )

    return {
        "mode": "DRY_RUN_NO_VIDEO_CREDITS" if dry_run else "FULL_4K_PRODUCTION",
        "models_invoked": {
            "frontier_brain": FRONTIER_BRAIN_MODEL,
            "orchestrator": ORCHESTRATOR_MODEL,
            "keyframes": f"{IMAGE_4K_PRO_MODEL} + {IMAGE_CONTINUITY_MODEL}",
            "video_simulation": "SKIPPED (--dry-run)" if dry_run else VIDEO_OMNI_MODEL,
            "narration_tts": TTS_EXPRESSIVE_MODEL,
            "word_alignment": TRANSCRIBE_MODEL,
            "ambient_score": MUSIC_LYRIA_MODEL,
        },
        "counts": {
            "scenes": num_scenes,
            "keyframes": keyframes_count,
            "ab_thumbnails": num_thumbnails,
            "target_video_seconds": round(total_duration_sec, 1),
            "resolution": resolution.upper(),
        },
        "estimated_cost_usd": {
            "seo_and_script_brain": cost_frontier_seo_script,
            "pydantic_orchestrator": cost_orchestrator_validation,
            "keyframes_3d": cost_keyframes_usd,
            "thumbnails_4k_ab": cost_thumbnails_usd,
            "omni_1_2_flash_video": cost_omni_video_usd,
            "hinglish_tts_and_alignment": cost_tts_transcribe_usd,
            "lyria_3_5_dark_synth": cost_lyria_bgm_usd,
            "total_estimated_usd": total_usd,
        },
    }
