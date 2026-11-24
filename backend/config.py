"""
OMNI STUDIO — Central Configuration, Multi-Niche Visual Taxonomy & Gemini SDK Helpers
=====================================================================================
100% generic across ANY topic or niche (Education, Entertainment, Finance, AI, Gadgets,
Tech, Stories, Business, History, Health & Science, Geopolitics, Self-Improvement).

Uses official `google-genai` SDK (`from google import genai`) and Interactions API
(`client.interactions.create(...)`) with latest GA Paid Tier 1 / Ultra models.
"""

from __future__ import annotations

import logging
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

def _load_local_dotenv() -> None:
    """Loads `.env` via python-dotenv if installed, or via a zero-dependency parser fallback."""
    try:
        from dotenv import load_dotenv
        load_dotenv()
        return
    except Exception:
        pass
    env_path = Path(".env")
    if not env_path.exists():
        return
    try:
        for raw_line in env_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k = k.strip()
            v = v.strip().strip('"').strip("'")
            if k and k not in os.environ:
                os.environ[k] = v
    except Exception:
        pass


_load_local_dotenv()

from google import genai

logger = logging.getLogger("omni_studio.config")

# ==============================================================================
# 1. LATEST GA / PAID TIER 1 MODEL STACK (Interactions API)
# ==============================================================================
SCRIPT_FRONTIER_MODEL: str = os.getenv("SCRIPT_MODEL", "gemini-4-carbon")
REASONING_FALLBACK_MODEL: str = os.getenv("REASONING_MODEL", "gemini-4-argon")
FAST_AGENT_MODEL: str = os.getenv("FAST_MODEL", "gemini-3.8-flash")

IMAGE_PRO_MODEL: str = os.getenv("IMAGE_MODEL", "gemini-3-pro-image")
IMAGE_CONTINUITY_MODEL: str = os.getenv("IMAGE_CONTINUITY_MODEL", "gemini-nano-banana-2.1")

VIDEO_OMNI_MODEL: str = os.getenv("VIDEO_MODEL", "gemini-omni-1.2-flash")
VERTEX_VEO_MODEL: str = os.getenv("VERTEX_VEO_MODEL", "veo-3.1-generate-001")

TTS_EXPRESSIVE_MODEL: str = os.getenv("TTS_MODEL", "gemini-3.8-flash-tts")
TRANSCRIBE_MODEL: str = os.getenv("TRANSCRIBE_MODEL", "gemini-3.5-transcribe")
MUSIC_LYRIA_MODEL: str = os.getenv("MUSIC_MODEL", "lyria-3.5")

# Safety guard against legacy deprecated models in `.env`
_DEPRECATED_PREFIXES = ("gemini-1.5-", "gemini-2.0-", "gemini-2.5-", "gemini-3.1-flash-image")


def resolve_current_model(configured_name: str, default_name: str) -> str:
    name = (configured_name or "").strip()
    if not name or any(name.lower().startswith(p) for p in _DEPRECATED_PREFIXES):
        return default_name
    return name


# ==============================================================================
# 2. GENERIC MULTI-NICHE VISUAL, AUDIO & GRAPHICS STYLE PROFILES
# ==============================================================================
SUPPORTED_NICHES: List[str] = [
    "Education",
    "Finance & Investing",
    "AI & Future Tech",
    "Gadgets & Reviews",
    "Business & Startups",
    "History & Geopolitics",
    "Stories & Mysteries",
    "Entertainment & Pop Culture",
    "Science & Space",
    "Health & Psychology",
]

SUPPORTED_LANGUAGES: List[str] = [
    "Hinglish (Spirited Indian Mentor)",
    "Hindi (Expressive Storytelling)",
    "English (Global Dynamic)",
]

NICHE_VISUAL_PROFILES: Dict[str, Dict[str, Any]] = {
    "Education": {
        "visual_style": "Clean modern 3D studio motion graphics, crisp volumetric diagrams, glowing conceptual callouts, dark-slate & neon-cyan educational cinema (Veritasium / 3Blue1Brown caliber), zero visual hallucination",
        "music_vibe": "Upbeat inquisitive electronic documentary pulse with warm arpeggio and crisp percussive drive, strictly instrumental",
        "accent_hex": "#00E5FF",
        "secondary_hex": "#FFD600",
        "badge_prefix": "EXPLAINED",
        "preferred_graphics": "manim_or_diagram",
    },
    "Finance & Investing": {
        "visual_style": "Sleek editorial motion animation, glassmorphic 3D financial dashboards, dark emerald & gold architectural lighting, cinematic macro currency/market metaphors, clean typography",
        "music_vibe": "High-stakes modern financial documentary score, sleek sub-bass pulse, rhythmic muted synth, energetic and authoritative, strictly instrumental",
        "accent_hex": "#00E676",
        "secondary_hex": "#FFB300",
        "badge_prefix": "MONEY TRUTH",
        "preferred_graphics": "data_chart",
    },
    "AI & Future Tech": {
        "visual_style": "Ultra-sharp futuristic 3D UI animations, glowing neural network topologies, obsidian glass laboratories, volumetric cyan and violet rim lighting, clean macro silicon shots",
        "music_vibe": "Futuristic cyber-documentary synthwave with forward-driving arpeggio and subtle bass groove, strictly instrumental",
        "accent_hex": "#38BDF8",
        "secondary_hex": "#C084FC",
        "badge_prefix": "AI DEEP DIVE",
        "preferred_graphics": "data_chart",
    },
    "Gadgets & Reviews": {
        "visual_style": "Commercial studio product macro cinematography (MKBHD caliber), matte black tabletops, dramatic edge-lit hardware silhouettes, crisp 3D internal teardown callouts, shallow f/1.4 DOF",
        "music_vibe": "Crisp modern lo-fi tech-beat with punchy percussive rhythm and clean bassline, energetic review pace, strictly instrumental",
        "accent_hex": "#FF3D5A",
        "secondary_hex": "#00E5FF",
        "badge_prefix": "TECH BREAKDOWN",
        "preferred_graphics": "comparison_chart",
    },
    "Business & Startups": {
        "visual_style": "High-contrast executive documentary cinematography, sleek boardroom & skyline b-roll blended with clean isometric 3D strategy diagrams, bold crimson and gold highlights",
        "music_vibe": "Driven corporate-thriller documentary pulse, crisp percussion, motivating string/synth ostinato, strictly instrumental",
        "accent_hex": "#F59E0B",
        "secondary_hex": "#10B981",
        "badge_prefix": "CASE STUDY",
        "preferred_graphics": "data_chart",
    },
    "History & Geopolitics": {
        "visual_style": "Epic 35mm cinema documentary aesthetics, atmospheric volumetric dust and golden-hour backlighting, animated 3D topographic maps, archival-grade dramatic lighting",
        "music_vibe": "Cinematic orchestral hybrid documentary score with deep cello pulse, subtle war-drum tension, and dramatic swells, strictly instrumental",
        "accent_hex": "#F97316",
        "secondary_hex": "#FACC15",
        "badge_prefix": "UNTOLD HISTORY",
        "preferred_graphics": "timeline_chart",
    },
    "Stories & Mysteries": {
        "visual_style": "Neo-noir dramatic storytelling cinematography, moody chiaroscuro lighting, rich anamorphic lens flares, atmospheric rain/fog environments, suspenseful slow push-ins",
        "music_vibe": "Suspenseful investigative mystery score with ticking percussive motifs, deep ambient pads, and high-retention build-ups, strictly instrumental",
        "accent_hex": "#EF4444",
        "secondary_hex": "#FDE047",
        "badge_prefix": "TRUE MYSTERY",
        "preferred_graphics": "timeline_chart",
    },
    "Entertainment & Pop Culture": {
        "visual_style": "Vibrant high-energy editorial video essay aesthetic, kinetic typography panels, neon studio rim-lighting, bold magenta/cyan color grading, rapid punch-in framing",
        "music_vibe": "High-energy modern pop-electronic instrumental groove with bouncy bassline and snappy percussion",
        "accent_hex": "#EC4899",
        "secondary_hex": "#22D3EE",
        "badge_prefix": "DEEP DIVE",
        "preferred_graphics": "comparison_chart",
    },
    "Science & Space": {
        "visual_style": "Photorealistic Unreal Engine 5 / Octane cosmic & laboratory cinema, macro optical physics, glowing planetary & subatomic cross-sections, deep obsidian studio aesthetics",
        "music_vibe": "Awe-inspiring cosmic ambient synth inspired by Christopher Nolan and Veritasium, deep sub-bass and crystalline harmonics, strictly instrumental",
        "accent_hex": "#06B6D4",
        "secondary_hex": "#FBBF24",
        "badge_prefix": "SCIENCE 3D",
        "preferred_graphics": "manim_or_diagram",
    },
    "Health & Psychology": {
        "visual_style": "Warm cinematic human-centric storytelling paired with crystal-clear 3D anatomical/neural light visualizations, soft teal and amber studio lighting, clean minimalist overlays",
        "music_vibe": "Uplifting warm minimalist pulse with organic marimba/synth textures and steady engaging rhythm, strictly instrumental",
        "accent_hex": "#14B8A6",
        "secondary_hex": "#F59E0B",
        "badge_prefix": "MIND & BODY",
        "preferred_graphics": "data_chart",
    },
}

DEFAULT_NICHE_PROFILE: Dict[str, Any] = NICHE_VISUAL_PROFILES["AI & Future Tech"]


def get_niche_profile(niche: str) -> Dict[str, Any]:
    return NICHE_VISUAL_PROFILES.get(niche, DEFAULT_NICHE_PROFILE)


def get_language_voice_profile(language_tone: str) -> Dict[str, str]:
    low = language_tone.lower()
    if "hinglish" in low:
        return {
            "language_code": "hi-IN",
            "gemini_voice": "Charon",
            "chirp3_voice": "hi-IN-Chirp3-HD-Charon",
            "edge_voice": "hi-IN-MadhurNeural",
            "edge_fallback": "en-IN-PrabhatNeural",
            "style_prompt": (
                "Spirited, charismatic Indian creator (@jwalashiva persona) speaking natural conversational "
                "Hinglish (Roman-script Hindi sentence flow with crisp English keywords). Warm authoritative "
                "baritone, brisk engaging YouTube pacing, lively emphasis on curiosity hooks and dramatic "
                "pauses before key insights. Zero robotic monotone."
            ),
        }
    if "hindi" in low:
        return {
            "language_code": "hi-IN",
            "gemini_voice": "Charon",
            "chirp3_voice": "hi-IN-Chirp3-HD-Charon",
            "edge_voice": "hi-IN-MadhurNeural",
            "edge_fallback": "hi-IN-SwaraNeural",
            "style_prompt": (
                "Spirited, expressive Indian storyteller speaking clean, engaging modern Hindi with natural "
                "YouTube cadence, crisp diction, dynamic emotional shifts, and dramatic pauses before twists."
            ),
        }
    return {
        "language_code": "en-IN",
        "gemini_voice": "Charon",
        "chirp3_voice": "en-IN-Chirp3-HD-Charon",
        "edge_voice": "en-IN-PrabhatNeural",
        "edge_fallback": "en-US-AndrewMultilingualNeural",
        "style_prompt": (
            "Dynamic, crisp, high-retention global YouTube documentary host with warm Indian-English "
            "articulation, authoritative pacing, punchy curiosity delivery, and expressive pauses."
        ),
    }


@dataclass
class OmniStudioConfig:
    """Runtime configuration loaded from `.env` and environment variables."""
    gemini_api_key: str = field(default_factory=lambda: os.getenv("GEMINI_API_KEY", "").strip())
    youtube_api_key: str = field(default_factory=lambda: os.getenv("YOUTUBE_API_KEY", "").strip())
    youtube_client_secrets: Path = field(
        default_factory=lambda: Path(os.getenv("YOUTUBE_CLIENT_SECRETS_FILE", "config/credentials/client_secret.json"))
    )
    youtube_token_file: Path = field(
        default_factory=lambda: Path(os.getenv("YOUTUBE_TOKEN_FILE", "config/credentials/youtube_oauth_token.json"))
    )
    youtube_redirect_uri: str = field(
        default_factory=lambda: os.getenv("YOUTUBE_REDIRECT_URI", "http://localhost:8501").strip()
    )
    creator_handle: str = field(default_factory=lambda: os.getenv("CREATOR_HANDLE", "@jwalashiva").strip())
    likeness_dir: Path = field(default_factory=lambda: Path(os.getenv("LIKENESS_DIR", "assets/likeness")))
    projects_dir: Path = field(default_factory=lambda: Path(os.getenv("OMNI_PROJECTS_DIR", "storage/projects")))
    resolution: str = field(default_factory=lambda: os.getenv("OMNI_VIDEO_RESOLUTION", "1080p").strip())
    fps: int = field(default_factory=lambda: int(os.getenv("OMNI_VIDEO_FPS", "24")))
    bgm_duck_db: float = field(default_factory=lambda: float(os.getenv("OMNI_BGM_DUCK_DB", "-24.0")))
    max_workers: int = field(default_factory=lambda: int(os.getenv("OMNI_MAX_WORKERS", "4")))
    use_cloud_tts_chirp3: bool = field(
        default_factory=lambda: os.getenv("USE_CLOUD_TTS_CHIRP3", "false").strip().lower() in ("1", "true", "yes")
    )

    def __post_init__(self) -> None:
        self.projects_dir.mkdir(parents=True, exist_ok=True)
        self.likeness_dir.mkdir(parents=True, exist_ok=True)

    @property
    def has_valid_gemini_key(self) -> bool:
        return bool(self.gemini_api_key) and self.gemini_api_key != "your_gemini_api_key_here"

    @property
    def likeness_reference_paths(self) -> List[Path]:
        """Returns user's on-disk likeness references (`image_12.png`, `image_13.png`, `image_14.png`)."""
        paths: List[Path] = []
        for fname in ("image_12.png", "image_13.png", "image_14.png"):
            p = self.likeness_dir / fname
            if p.exists():
                paths.append(p)
        return paths

    @property
    def thumbnail_style_sample_path(self) -> Optional[Path]:
        p = self.likeness_dir / "image_11.png"
        return p if p.exists() else None


def get_genai_client(api_key: Optional[str] = None) -> genai.Client:
    key = (api_key or os.getenv("GEMINI_API_KEY", "")).strip()
    if key:
        return genai.Client(api_key=key)
    return genai.Client()


def call_interaction_with_fallback(
    client: genai.Client,
    *,
    models: List[str],
    max_retries: int = 3,
    base_delay: float = 1.8,
    **kwargs: Any,
) -> Any:
    """
    Calls `client.interactions.create(...)` with exponential backoff and clean model fallback.
    """
    last_err: Optional[Exception] = None
    for model_name in models:
        for attempt in range(1, max_retries + 1):
            try:
                return client.interactions.create(model=model_name, **kwargs)
            except Exception as exc:
                last_err = exc
                err_low = str(exc).lower()
                if any(tok in err_low for tok in ("402", "prepayment credits", "billing")):
                    logger.warning("Model '%s' billing/credit exhausted (HTTP 402); falling back immediately.", model_name)
                    break
                if any(tok in err_low for tok in ("404", "not found", "invalid model", "unsupported")):
                    logger.warning("Model '%s' unavailable; trying fallback next.", model_name)
                    break
                if attempt < max_retries:
                    delay = min(16.0, base_delay * (2 ** (attempt - 1)))
                    logger.warning("Retry %d/%d for %s after error: %s", attempt, max_retries, model_name, exc)
                    time.sleep(delay)
    if last_err:
        raise last_err
    raise RuntimeError("No Gemini model succeeded for interaction.")


def sanitize_slug(text: str, max_len: int = 44) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "_", text.strip()).strip("_").lower()
    return cleaned[:max_len] or "omni_project"


def format_timestamp(seconds: float) -> str:
    sec_int = max(0, int(round(seconds)))
    mins, secs = divmod(sec_int, 60)
    hrs, mins = divmod(mins, 60)
    if hrs > 0:
        return f"{hrs:02d}:{mins:02d}:{secs:02d}"
    return f"{mins:02d}:{secs:02d}"
