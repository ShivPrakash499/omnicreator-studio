"""
OMNI STUDIO — Central Configuration, Multi-Niche Visual Taxonomy & Gemini SDK Helpers
=====================================================================================
100% generic across ANY topic or niche (Education, Entertainment, Finance, AI, Gadgets,
Tech, Stories, Business, History, Health & Science, Geopolitics, Self-Improvement).

Uses official `google-genai` SDK (`from google import genai`) and Interactions API
(`client.interactions.create(...)`) with latest GA Paid Tier 1 / Ultra models.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from google.auth.transport.requests import Request as GoogleAuthRequest
from google.oauth2.credentials import Credentials as GoogleUserCredentials

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


def sync_streamlit_secrets_to_env() -> None:
    """Copies top-level Streamlit Secrets into `os.environ` on the main thread so background worker threads always see them."""
    try:
        import streamlit as st
        if hasattr(st, "secrets"):
            for k, v in st.secrets.items():
                if isinstance(v, str) and v.strip() and k not in os.environ:
                    os.environ[k] = v.strip()
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
VERTEX_LYRIA_MODEL: str = os.getenv("VERTEX_LYRIA_MODEL", "lyria-002")

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
        "visual_style": (
            "IMAX prestige science documentary cinematography (Veritasium & BBC Earth caliber), shot on ARRI Alexa 65 "
            "with 35mm anamorphic lenses, tangible real-world experiments, atmospheric volumetric light beams, "
            "deep obsidian and electric cyan rim lighting, rich shallow f/1.4 depth of field, photorealistic cinema"
        ),
        "music_vibe": "Upbeat inquisitive electronic documentary pulse with warm arpeggio and crisp percussive drive, strictly instrumental",
        "accent_hex": "#00E5FF",
        "secondary_hex": "#FFD600",
        "badge_prefix": "EXPLAINED",
        "preferred_graphics": "manim_or_diagram",
    },
    "Finance & Investing": {
        "visual_style": (
            "Prestige financial thriller cinematography (Succession & The Big Short caliber), sweeping twilight metropolitan "
            "skylines, gleaming glass-and-marble architectural interiors, macro brushed gold and currency textures, "
            "dramatic chiaroscuro emerald and warm tungsten lighting, Kodak Vision3 500T film grade, shallow DOF"
        ),
        "music_vibe": "High-stakes modern financial documentary score, sleek sub-bass pulse, rhythmic muted synth, energetic and authoritative, strictly instrumental",
        "accent_hex": "#00E676",
        "secondary_hex": "#FFB300",
        "badge_prefix": "MONEY TRUTH",
        "preferred_graphics": "data_chart",
    },
    "AI & Future Tech": {
        "visual_style": (
            "Blade Runner 2049 & Ex Machina theatrical sci-fi cinema, shot on 65mm anamorphic glass, sleek obsidian "
            "research laboratories, hyper-real macro silicon wafers and fiber-optic light trails, wet rain-slicked "
            "modern highways and volumetric cyan-and-amber practical lighting, tactile physical materials and deep realism"
        ),
        "music_vibe": "Futuristic cyber-documentary synthwave with forward-driving arpeggio and subtle bass groove, strictly instrumental",
        "accent_hex": "#38BDF8",
        "secondary_hex": "#C084FC",
        "badge_prefix": "AI DEEP DIVE",
        "preferred_graphics": "data_chart",
    },
    "Gadgets & Reviews": {
        "visual_style": (
            "Ultra-premium commercial product cinema (Apple Keynote & MKBHD RED V-Raptor 8K caliber), motorized macro "
            "slider dolly shots, brushed titanium, anodized aluminum, and sapphire glass specular reflections on matte "
            "slate surfaces, dramatic edge rim lights, creamy f/1.4 bokeh, crisp micro-surface detail"
        ),
        "music_vibe": "Crisp modern lo-fi tech-beat with punchy percussive rhythm and clean bassline, energetic review pace, strictly instrumental",
        "accent_hex": "#FF3D5A",
        "secondary_hex": "#00E5FF",
        "badge_prefix": "TECH BREAKDOWN",
        "preferred_graphics": "comparison_chart",
    },
    "Business & Startups": {
        "visual_style": (
            "Netflix executive documentary cinematography, sweeping golden-hour skyscraper silhouettes, warm tungsten "
            "engineering labs and modern glass studios, dynamic Steadicam tracking shots, crisp anamorphic lens flares, "
            "high-contrast cinematic tungsten-and-teal color grade"
        ),
        "music_vibe": "Driven corporate-thriller documentary pulse, crisp percussion, motivating string/synth ostinato, strictly instrumental",
        "accent_hex": "#F59E0B",
        "secondary_hex": "#10B981",
        "badge_prefix": "CASE STUDY",
        "preferred_graphics": "data_chart",
    },
    "History & Geopolitics": {
        "visual_style": (
            "Epic Christopher Nolan & Ridley Scott 35mm historical film cinematography, sweeping mist-covered landscapes, "
            "golden-hour volumetric dust shafts, authentic weathered stone, brass, and archival textures, dramatic "
            "natural torchlight and stormy twilight skies, rich celluloid film grain and monumental scale"
        ),
        "music_vibe": "Cinematic orchestral hybrid documentary score with deep cello pulse, subtle war-drum tension, and dramatic swells, strictly instrumental",
        "accent_hex": "#F97316",
        "secondary_hex": "#FACC15",
        "badge_prefix": "UNTOLD HISTORY",
        "preferred_graphics": "timeline_chart",
    },
    "Stories & Mysteries": {
        "visual_style": (
            "David Fincher neo-noir thriller cinematography, moody chiaroscuro shadow play, rain-streaked glass "
            "reflections, sodium-vapor streetlights piercing misty midnight streets, slow hypnotic dolly push-ins, "
            "subtle anamorphic amber flares, palpable cinematic atmosphere and tension"
        ),
        "music_vibe": "Suspenseful investigative mystery score with ticking percussive motifs, deep ambient pads, and high-retention build-ups, strictly instrumental",
        "accent_hex": "#EF4444",
        "secondary_hex": "#FDE047",
        "badge_prefix": "TRUE MYSTERY",
        "preferred_graphics": "timeline_chart",
    },
    "Entertainment & Pop Culture": {
        "visual_style": (
            "A24 & Denis Villeneuve vibrant theatrical cinema, lush neon practical rim-lighting, fluid Steadicam "
            "tracking through atmospheric stages, rain-lit boulevards, and glowing studios, rich magenta-and-cyan "
            "color grading, dreamy anamorphic bokeh, pure visual storytelling"
        ),
        "music_vibe": "High-energy modern pop-electronic instrumental groove with bouncy bassline and snappy percussion",
        "accent_hex": "#EC4899",
        "secondary_hex": "#22D3EE",
        "badge_prefix": "DEEP DIVE",
        "preferred_graphics": "comparison_chart",
    },
    "Science & Space": {
        "visual_style": (
            "Interstellar & IMAX cosmic cinematography, photorealistic orbital planetary vistas, dramatic solar "
            "eclipses, razor-sharp laboratory laser optics, high-speed macro physical phenomena, deep obsidian "
            "space shadows with radiant amber and sapphire light bloom"
        ),
        "music_vibe": "Awe-inspiring cosmic ambient synth inspired by Christopher Nolan and Veritasium, deep sub-bass and crystalline harmonics, strictly instrumental",
        "accent_hex": "#06B6D4",
        "secondary_hex": "#FBBF24",
        "badge_prefix": "SCIENCE 3D",
        "preferred_graphics": "manim_or_diagram",
    },
    "Health & Psychology": {
        "visual_style": (
            "Intimate prestige documentary cinematography, warm golden-hour natural sunlight streaming through "
            "windows, poetic shallow-DOF human silhouettes and tranquil lived-in environments, luminous microscopic "
            "organic textures, serene teal and warm honey film color grade"
        ),
        "music_vibe": "Uplifting warm minimalist pulse with organic marimba/synth textures and steady engaging rhythm, strictly instrumental",
        "accent_hex": "#14B8A6",
        "secondary_hex": "#F59E0B",
        "badge_prefix": "MIND & BODY",
        "preferred_graphics": "data_chart",
    },
}

DEFAULT_NICHE_PROFILE: Dict[str, Any] = NICHE_VISUAL_PROFILES["AI & Future Tech"]

# Curated Hollywood Director-of-Photography Look Presets selectable across the pipeline
CINEMA_STYLE_PRESETS: Dict[str, Dict[str, str]] = {
    "🎬 Hollywood IMAX Documentary (Default)": {
        "camera_rig": "Shot on ARRI Alexa 65 with Panavision 35mm anamorphic prime glass, natural film grain, 24fps",
        "lighting_signature": "Motivated volumetric key light, crisp rim backlighting, specular wet/metallic reflections, atmospheric depth haze",
        "color_grade": "Rich theatrical IMAX teal-and-amber dynamic range, deep velvety shadows, luminous highlights",
        "motion_feel": "Silky stabilized cinema dolly, crane, and aerial gimbal choreography with natural physical physics",
    },
    "🚀 Sci-Fi Cyberpunk Feature (Blade Runner)": {
        "camera_rig": "Shot on 65mm anamorphic cinema lens with subtle horizontal optical flares, shallow f/1.4 DOF, 24fps",
        "lighting_signature": "Rain-soaked neon cyan and sodium-amber street reflections, dense volumetric fog beams, high-contrast silhouette lighting",
        "color_grade": "Moody neo-futuristic obsidian, electric cyan, and molten amber theatrical color grade",
        "motion_feel": "Gliding low-angle tracking shots and sweeping nocturnal drone reveals through mist",
    },
    "🎞️ 35mm Prestige Drama (Christopher Nolan)": {
        "camera_rig": "Shot on 35mm Kodak Vision3 500T film stock, organic celluloid texture, crisp prime lenses, 24fps",
        "lighting_signature": "Natural golden-hour shafts, dramatic overcast skies, authentic practical tungsten lamps, chiaroscuro contrast",
        "color_grade": "Timeless theatrical celluloid grade with warm skin tones, earthy highlights, and deep ink shadows",
        "motion_feel": "Deliberate grounded Steadicam push-ins, sweeping crane arcs, and monumental wide establishing frames",
    },
    "💎 Commercial Studio Luxury (Apple Keynote)": {
        "camera_rig": "Shot on RED V-Raptor 8K with robotic Bolt motion-control macro lens, razor-sharp focus rack, 24fps",
        "lighting_signature": "Sculpted softbox rim lights, flawless specular highlights across glass, carbon fiber, and anodized metal",
        "color_grade": "Ultra-clean obsidian matte blacks, crisp neutral whites, and surgical jewel-tone accent light",
        "motion_feel": "Precision motorized micro-dolly glides, smooth orbital product reveals, zero camera shake",
    },
    "🌌 Epic Cosmic & Nature (Interstellar / BBC)": {
        "camera_rig": "Shot on IMAX 70mm large-format lens with breathtaking scale, crisp foreground-to-horizon depth, 24fps",
        "lighting_signature": "Radiant cosmic rim eclipses, atmospheric golden god-rays, shimmering particulate dust and light refraction",
        "color_grade": "Awe-inspiring deep indigo shadows, luminous solar gold highlights, expansive theatrical contrast",
        "motion_feel": "Majestic weightless orbital drift, soaring aerial sweeps, and hypnotic slow-motion 120fps physics",
    },
}

DEFAULT_CINEMA_PRESET: str = "🎬 Hollywood IMAX Documentary (Default)"

# Rotating 8-shot theatrical editing grammar enforcing authentic visual resets every 8-12 seconds
CINEMATIC_SHOT_CHOREOGRAPHY: List[Dict[str, str]] = [
    {
        "shot_type": "Sweeping Wide Establishing",
        "camera_move": "Smooth elevated crane descent gliding forward into the scene, 24mm anamorphic wide lens, layered foreground-to-horizon atmospheric depth",
        "lighting": "Dramatic golden-hour / twilight volumetric light rays cutting through fine mist with crisp rim highlights",
    },
    {
        "shot_type": "Low-Angle Hero Tracking",
        "camera_move": "Dynamic low-angle gimbal tracking shot gliding alongside the main subject, 35mm prime lens, subtle speed-blur on background elements",
        "lighting": "High-contrast motivated side lighting with gleaming wet-surface reflections and rich theatrical shadows",
    },
    {
        "shot_type": "Intimate 100mm Macro Detail",
        "camera_move": "Ultra-smooth motorized macro push-in with shallow f/1.4 focus rack revealing intricate mechanical, optical, or physical textures",
        "lighting": "Sculpted precision rim backlighting catching micro-particles, specular edges, and subtle light bloom",
    },
    {
        "shot_type": "Orbital 180° Steadicam Arc",
        "camera_move": "Fluid 50mm anamorphic Steadicam orbiting smoothly around the central subject, creating rich parallax across background depth layers",
        "lighting": "Atmospheric chiaroscuro key light with luminous practical accents and creamy out-of-focus bokeh orbs",
    },
    {
        "shot_type": "Overhead Aerial God's-Eye Reveal",
        "camera_move": "Majestic stabilized overhead top-down drone pull-back gradually revealing grand architectural, geographic, or systemic scale",
        "lighting": "Crisp directional raking light casting long dramatic shadows and glowing ambient movement trails",
    },
    {
        "shot_type": "Slow-Motion 120fps Physical Drama",
        "camera_move": "Silky 85mm telephoto medium close-up capturing hyper-real slow-motion physics (sparks, light pulses, droplets, dust motes, or motion dynamics)",
        "lighting": "Dramatic split-tone amber-and-cyan rim illumination carving crisp silhouettes out of dark atmospheric haze",
    },
    {
        "shot_type": "Over-the-Shoulder Foreground Parallax",
        "camera_move": "Subtle handheld-stabilized dolly slide passing softly blurred foreground glass or architecture to unveil the focal revelation cleanly",
        "lighting": "Warm interior practical lamps contrasting cool blue exterior twilight through glass and mist",
    },
    {
        "shot_type": "Monumental Pull-Back Horizon Finale",
        "camera_move": "Expansive reverse aerial crane rise smoothly pulling away from the subject toward a glowing cinematic horizon, serene dramatic closure",
        "lighting": "Radiant horizon backlight, atmospheric lens bloom, deep theatrical contrast, timeless filmic finish",
    },
]

# Global strict language & anti-hallucination guard applied to EVERY video & image generation call
STRICT_ENGLISH_NO_FOREIGN_TEXT_RULE: str = (
    "STRICT VISUAL LANGUAGE RULE: NEVER render any Chinese, Mandarin, Kanji, Japanese, Korean, "
    "Cyrillic, Arabic, or garbled gibberish characters anywhere on vehicles, windshields, license plates, "
    "screens, billboards, signs, HUDs, or objects. Prefer completely textless photorealistic cinema; "
    "if any real-world label or HUD text is shown, it MUST be ONLY clean, accurately spelled standard English."
)

VEO_STRICT_NEGATIVE_PROMPT: str = (
    "Chinese text, Mandarin characters, Hanzi, Kanji, Japanese text, Korean Hangul, Cyrillic text, "
    "gibberish letters, garbled text, distorted license plates, watermarks, floating subtitles, text overlays, "
    "PowerPoint slides, flat 2D clipart, infographic bar charts, wireframe grid floor, neon grid clipart, "
    "cheesy plastic CGI, UI dashboard panels, split screen collage, abrupt jump cuts, blurry low resolution"
)


def get_cinema_preset(preset_name: Optional[str] = None) -> Dict[str, str]:
    if preset_name and preset_name in CINEMA_STYLE_PRESETS:
        return CINEMA_STYLE_PRESETS[preset_name]
    return CINEMA_STYLE_PRESETS[DEFAULT_CINEMA_PRESET]


def build_cinematic_video_prompt(
    raw_prompt: str,
    *,
    niche: str,
    cinema_preset: Optional[str] = None,
    camera_cue: str = "",
    sfx_cue: str = "",
    aspect_ratio: str = "16:9",
    duration_sec: float = 8.0,
    scene_index: int = 1,
) -> str:
    """
    Elevates ANY scene prompt (new, user-edited, or legacy) into Hollywood-grade cinematography
    optimized for Gemini Omni 1.2 Flash & Vertex Veo 3.1:
    - Strips anti-cinema chart/UI clichés (`wireframe grid`, `summary card`, `analytical chart`, etc.)
    - Injects concrete lens/rig, motivated lighting, film color grade, and smooth continuous motion
    - Embeds frame-synced pure-Foley sound design (NO spoken dialogue, NO singing, NO background music)
    - Enforces Omni's single-unbroken-shot rule (zero jump cuts) + zero foreign glyphs.
    """
    prof = get_niche_profile(niche)
    preset = get_cinema_preset(cinema_preset)
    choreo = CINEMATIC_SHOT_CHOREOGRAPHY[(max(1, scene_index) - 1) % len(CINEMATIC_SHOT_CHOREOGRAPHY)]

    cleaned = (raw_prompt or "").strip()
    # Idempotently strip prior appended boilerplate so re-enhancing (Agent 2 -> Agent 3) never duplicates clauses
    for marker in ("Sound design:", "Execution:", "STRICT VISUAL LANGUAGE RULE:"):
        if marker in cleaned:
            cleaned = cleaned.split(marker)[0].strip()

    # Replace chart/slide/grid clichés with photorealistic physical cinema language
    anti_cinema_replacements = [
        (r"\banalytical data chart\b", "photorealistic physical visual metaphor in real-world light"),
        (r"\bmotion graphic[s]?\b", "photorealistic live-action and IMAX CGI cinematography"),
        (r"\bkinetic summary card\b", "sweeping twilight architectural vista"),
        (r"\benergetic outro motion backdrop\b", "expansive golden-hour horizon pull-back"),
        (r"\bwireframe grid\b", "rain-slicked asphalt and sleek architectural reflections"),
        (r"\btypography panels?\b", "clean atmospheric practical lighting"),
        (r"\bcomparison scorecard\b", "dramatic real-world side-by-side physical contrast"),
        (r"\bannotated diagram reveal\b", "intimate macro physical cutaway in dramatic studio lighting"),
        (r"\binfographic\b", "tangible physical 3D real-world scene"),
    ]
    for pat, repl in anti_cinema_replacements:
        cleaned = re.sub(pat, repl, cleaned, flags=re.IGNORECASE)

    low = cleaned.lower()
    parts: List[str] = [cleaned.rstrip(".") + "."]

    # Inject camera choreography if missing concrete lens/movement guidance
    has_lens_or_cam = any(
        tok in low for tok in ("35mm", "50mm", "65mm", "85mm", "100mm", "anamorphic", "dolly", "steadicam", "crane", "drone", "tracking", "macro")
    )
    if not has_lens_or_cam:
        cam_desc = camera_cue.strip() if camera_cue and len(camera_cue.strip()) > 20 else choreo["camera_move"]
        parts.append(f"Cinematography: {cam_desc}.")

    # Inject theatrical lighting, film rig & color grade if not already specified
    has_lighting_grade = any(
        tok in low for tok in ("arri", "kodak", "red v-raptor", "imax", "chiaroscuro", "volumetric", "color grade", "anamorphic")
    )
    if not has_lighting_grade:
        parts.append(
            f"Look & Lighting: {preset['camera_rig']}; {preset['lighting_signature']}; "
            f"{preset['color_grade']}. Visual tone anchored to {prof['visual_style']}."
        )

    # Inject rich frame-synced physical Foley sound design (strictly NO dialogue/music so it blends cleanly!)
    clean_sfx = (sfx_cue or "").strip()
    if clean_sfx.lower() in ("", "subtle whoosh transition", "crisp whoosh riser", "subtle kinetic click"):
        clean_sfx = "subtle realistic environmental ambience and physical foley matching the visible on-screen motion"
    parts.append(
        f"Sound design: {clean_sfx}; authentic frame-synced realistic foley sound effects matching every visible "
        f"physical motion, strictly NO spoken dialogue, NO human voices, NO singing, NO background music."
    )

    dur_int = max(4, min(12, int(round(duration_sec))))
    aspect_phrase = "16:9 widescreen theatrical" if aspect_ratio == "16:9" else "9:16 vertical cinematic"
    parts.append(
        f"Execution: Single unbroken continuous {dur_int}-second {aspect_phrase} shot with lived-in natural micro-motion "
        f"(drifting atmospheric haze, realistic reflections, fluid physics). No scene cuts, no split screens, "
        f"no UI overlays. {STRICT_ENGLISH_NO_FOREIGN_TEXT_RULE}"
    )
    return " ".join(parts)


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
    bgm_duck_db: float = field(default_factory=lambda: float(os.getenv("OMNI_BGM_DUCK_DB", "-13.5")))
    max_workers: int = field(default_factory=lambda: int(os.getenv("OMNI_MAX_WORKERS", "4")))
    use_cloud_tts_chirp3: bool = field(
        default_factory=lambda: os.getenv("USE_CLOUD_TTS_CHIRP3", "false").strip().lower() in ("1", "true", "yes")
    )

    def __post_init__(self) -> None:
        self.projects_dir.mkdir(parents=True, exist_ok=True)
        self.likeness_dir.mkdir(parents=True, exist_ok=True)

    @property
    def has_valid_gemini_key(self) -> bool:
        """Returns True when either Vertex AI ADC credentials (Priority 1) or GEMINI_API_KEY is available."""
        creds, proj = get_vertex_adc_credentials()
        if creds is not None and proj:
            return True
        return bool(self.gemini_api_key) and self.gemini_api_key != "your_gemini_api_key_here"

    @property
    def active_auth_summary(self) -> str:
        creds, proj = get_vertex_adc_credentials()
        if creds is not None and proj:
            return f"Vertex AI ADC ({proj} • global)"
        if self.gemini_api_key and self.gemini_api_key != "your_gemini_api_key_here":
            return "AI Studio API Key"
        return "Local Fallback Mode"

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


_VERTEX_ADC_CACHE: Dict[str, Any] = {"checked": False, "creds": None, "project": ""}


def get_vertex_adc_credentials(force_refresh: bool = False) -> Tuple[Optional[GoogleUserCredentials], str]:
    """
    Priority-1 Google AI Ultra / Cloud Credits Auth via Vertex AI ADC (identical to `coindcx_box_bot`).
    Resolution order:
    1. Streamlit Server Secrets (`VERTEX_ADC_JSON` or `[vertex_adc]`)
    2. `VERTEX_ADC_JSON` environment variable
    3. `GOOGLE_APPLICATION_CREDENTIALS` or `config/credentials/vertex_adc.json`
    4. Local gcloud ADC (`%APPDATA%/gcloud/application_default_credentials.json` or `~/.config/gcloud/...`)
    """
    if not force_refresh and _VERTEX_ADC_CACHE["checked"] and _VERTEX_ADC_CACHE["creds"] is not None:
        creds = _VERTEX_ADC_CACHE["creds"]
        try:
            if creds.expired and creds.refresh_token:
                creds.refresh(GoogleAuthRequest())
        except Exception:
            pass
        return creds, str(_VERTEX_ADC_CACHE["project"])

    raw_dict: Optional[Dict[str, Any]] = None

    # 1. Streamlit Cloud Secrets
    try:
        import streamlit as st
        if hasattr(st, "secrets"):
            if "VERTEX_ADC_JSON" in st.secrets:
                val = st.secrets["VERTEX_ADC_JSON"]
                raw_dict = json.loads(val) if isinstance(val, str) else dict(val)
            elif "vertex_adc" in st.secrets:
                raw_dict = dict(st.secrets["vertex_adc"])
    except Exception:
        pass

    # 2. Environment variable JSON
    if raw_dict is None and os.getenv("VERTEX_ADC_JSON", "").strip():
        try:
            raw_dict = json.loads(os.getenv("VERTEX_ADC_JSON", "").strip())
        except Exception:
            pass

    # 3. Local credential files
    if raw_dict is None:
        cand_paths: List[Path] = []
        env_cred = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "").strip()
        if env_cred:
            cand_paths.append(Path(env_cred))
        cand_paths.append(Path("config/credentials/vertex_adc.json"))
        appdata = os.environ.get("APPDATA", "")
        if appdata:
            cand_paths.append(Path(appdata) / "gcloud" / "application_default_credentials.json")
        cand_paths.append(Path.home() / ".config" / "gcloud" / "application_default_credentials.json")

        for p in cand_paths:
            if p.exists():
                try:
                    data = json.loads(p.read_text(encoding="utf-8"))
                    if data.get("type") == "authorized_user" and data.get("refresh_token"):
                        raw_dict = data
                        break
                except Exception:
                    continue

    if raw_dict and raw_dict.get("type") == "authorized_user" and raw_dict.get("refresh_token"):
        try:
            project_id = (
                raw_dict.get("quota_project_id")
                or os.getenv("GOOGLE_CLOUD_PROJECT", "").strip()
                or os.getenv("VERTEX_PROJECT_ID", "").strip()
                or "gen-lang-client-0777980903"
            )
            creds = GoogleUserCredentials.from_authorized_user_info(
                raw_dict,
                scopes=["https://www.googleapis.com/auth/cloud-platform"],
            )
            if not creds.valid or creds.expired:
                creds.refresh(GoogleAuthRequest())
            _VERTEX_ADC_CACHE.update({"checked": True, "creds": creds, "project": project_id})
            return creds, project_id
        except Exception as exc:
            logger.warning("Vertex AI ADC credential load/refresh skipped: %s", exc)

    _VERTEX_ADC_CACHE.update({"checked": True, "creds": None, "project": ""})
    return None, ""


def get_genai_client(api_key: Optional[str] = None, location: str = "global") -> genai.Client:
    """
    Returns a `google.genai.Client`:
    - Priority 1: Vertex AI ADC (`vertexai=True`, `location='global'`) using Google AI Ultra / Cloud credits.
    - Priority 2: Developer API key (`GEMINI_API_KEY`).
    """
    v_creds, v_proj = get_vertex_adc_credentials()
    if v_creds is not None and v_proj:
        return genai.Client(vertexai=True, credentials=v_creds, project=v_proj, location=location)

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
    Calls `client.interactions.create(...)` with exponential backoff and smart fast-fail model fallback.
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
                    logger.warning("Model '%s' billing/credit exhausted (HTTP 402); trying next fallback.", model_name)
                    break
                if any(tok in err_low for tok in ("403", "permission_denied", "404", "not found", "invalid model", "unsupported")):
                    logger.warning("Model '%s' unavailable/restricted on current tier; trying next model.", model_name)
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
