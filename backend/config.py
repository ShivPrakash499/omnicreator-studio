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
    "Religious & Devotional",
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
            "Prestige theatrical science documentary aesthetic (BBC Earth & Veritasium caliber), "
            "tangible real-world physical experiments, atmospheric volumetric light beams, "
            "deep obsidian and electric cyan rim lighting, rich shallow depth of field, photorealistic cinema"
        ),
        "music_vibe": "Upbeat inquisitive electronic documentary pulse with warm arpeggio and crisp percussive drive, strictly instrumental",
        "accent_hex": "#00E5FF",
        "secondary_hex": "#FFD600",
        "badge_prefix": "EXPLAINED",
        "preferred_graphics": "manim_or_diagram",
    },
    "Finance & Investing": {
        "visual_style": (
            "Prestige financial drama visual aesthetic, sweeping twilight metropolitan "
            "skylines, gleaming glass-and-marble architectural interiors, macro brushed gold and currency textures, "
            "dramatic chiaroscuro emerald and warm tungsten lighting, rich celluloid film grade, shallow depth of field"
        ),
        "music_vibe": "High-stakes modern financial documentary score, sleek sub-bass pulse, rhythmic muted synth, energetic and authoritative, strictly instrumental",
        "accent_hex": "#00E676",
        "secondary_hex": "#FFB300",
        "badge_prefix": "MONEY TRUTH",
        "preferred_graphics": "data_chart",
    },
    "AI & Future Tech": {
        "visual_style": (
            "Theatrical neo-futuristic sci-fi cinema aesthetic, sleek obsidian "
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
            "Ultra-premium commercial product cinema aesthetic, smooth sweeping macro close-ups, "
            "brushed titanium, anodized aluminum, and sapphire glass specular reflections on matte "
            "slate surfaces, dramatic edge rim lights, creamy shallow bokeh, crisp micro-surface detail"
        ),
        "music_vibe": "Crisp modern lo-fi tech-beat with punchy percussive rhythm and clean bassline, energetic review pace, strictly instrumental",
        "accent_hex": "#FF3D5A",
        "secondary_hex": "#00E5FF",
        "badge_prefix": "TECH BREAKDOWN",
        "preferred_graphics": "comparison_chart",
    },
    "Business & Startups": {
        "visual_style": (
            "Prestige executive documentary aesthetic, sweeping golden-hour skyscraper silhouettes, warm tungsten "
            "engineering labs and modern glass interiors, fluid forward-moving perspectives, subtle warm light flares, "
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
            "Epic theatrical historical film aesthetic, sweeping mist-covered landscapes, "
            "golden-hour volumetric dust shafts, authentic weathered stone, brass, and period-accurate textures, dramatic "
            "natural torchlight and stormy twilight skies, subtle film grain and monumental scale, strictly era-authentic"
        ),
        "music_vibe": "Cinematic orchestral hybrid documentary score with deep cello pulse, subtle war-drum tension, and dramatic swells, strictly instrumental",
        "accent_hex": "#F97316",
        "secondary_hex": "#FACC15",
        "badge_prefix": "UNTOLD HISTORY",
        "preferred_graphics": "timeline_chart",
    },
    "Stories & Mysteries": {
        "visual_style": (
            "Atmospheric neo-noir thriller aesthetic, moody chiaroscuro shadow play, rain-streaked glass "
            "reflections, warm amber streetlights piercing misty midnight streets, slow hypnotic forward motion, "
            "palpable cinematic atmosphere and tension"
        ),
        "music_vibe": "Suspenseful investigative mystery score with ticking percussive motifs, deep ambient pads, and high-retention build-ups, strictly instrumental",
        "accent_hex": "#EF4444",
        "secondary_hex": "#FDE047",
        "badge_prefix": "TRUE MYSTERY",
        "preferred_graphics": "timeline_chart",
    },
    "Religious & Devotional": {
        "visual_style": (
            "Epic sacred Indian mythological theatrical film aesthetic, golden-hour ancient sandstone temple architecture, "
            "radiant divine sunbeams piercing swirling sandalwood incense, glowing brass diyas and sacred river reflections, "
            "rich saffron-gold and deep twilight indigo film color grade, majestic reverent ancient atmosphere, strictly era-authentic"
        ),
        "music_vibe": (
            "Soulful Indian devotional cinematic film score with expressive bansuri bamboo flute melody, warm "
            "meditative tanpura drone, resonant sitar and sarangi, subtle deep temple pakhawaj percussion, and "
            "sweeping reverent orchestral strings, strictly instrumental, zero vocals"
        ),
        "accent_hex": "#FF9900",
        "secondary_hex": "#FFD700",
        "badge_prefix": "DIVINE KATHA",
        "preferred_graphics": "timeline_chart",
    },
    "Entertainment & Pop Culture": {
        "visual_style": (
            "Vibrant theatrical cinema aesthetic, lush neon practical rim-lighting, fluid forward motion "
            "through atmospheric stages and rain-lit boulevards, rich magenta-and-cyan "
            "color grading, dreamy shallow bokeh, pure visual storytelling"
        ),
        "music_vibe": "High-energy modern pop-electronic instrumental groove with bouncy bassline and snappy percussion",
        "accent_hex": "#EC4899",
        "secondary_hex": "#22D3EE",
        "badge_prefix": "DEEP DIVE",
        "preferred_graphics": "comparison_chart",
    },
    "Science & Space": {
        "visual_style": (
            "Monumental cosmic cinema aesthetic, photorealistic orbital planetary vistas, dramatic solar "
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
            "Intimate prestige documentary aesthetic, warm golden-hour natural sunlight streaming through "
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

# Curated Theatrical Look Presets (ZERO physical camera brand/rig names so video models NEVER draw cameras on screen!)
CINEMA_STYLE_PRESETS: Dict[str, Dict[str, str]] = {
    "🎬 Hollywood IMAX Documentary (Default)": {
        "camera_rig": "Widescreen theatrical feature-film aesthetic with razor-sharp detail, subtle organic film grain, and natural shallow depth of field",
        "lighting_signature": "Motivated volumetric key light, crisp rim backlighting, specular wet/metallic reflections, atmospheric depth haze",
        "color_grade": "Rich theatrical teal-and-amber dynamic range, deep velvety shadows, luminous highlights",
        "motion_feel": "Silky smooth gliding perspective with natural physical motion and zero jitter",
    },
    "🚀 Sci-Fi Cyberpunk Feature (Blade Runner)": {
        "camera_rig": "Widescreen neo-noir sci-fi film aesthetic with subtle horizontal light flares, shallow depth of field, and atmospheric realism",
        "lighting_signature": "Rain-soaked neon cyan and sodium-amber reflections, dense volumetric fog beams, high-contrast silhouette lighting",
        "color_grade": "Moody neo-futuristic obsidian, electric cyan, and molten amber theatrical color grade",
        "motion_feel": "Gliding low-angle forward perspective and sweeping nocturnal aerial views through mist",
    },
    "🎞️ 35mm Prestige Drama (Christopher Nolan)": {
        "camera_rig": "Classic theatrical celluloid drama aesthetic with authentic organic film texture, natural clarity, and deep tonal range",
        "lighting_signature": "Natural golden-hour shafts, dramatic overcast skies, authentic warm practical firelight or lamps, chiaroscuro contrast",
        "color_grade": "Timeless theatrical film grade with warm natural skin tones, earthy highlights, and deep ink shadows",
        "motion_feel": "Deliberate grounded slow push-ins, sweeping wide arcs, and monumental establishing views",
    },
    "💎 Commercial Studio Luxury (Apple Keynote)": {
        "camera_rig": "Ultra-clean luxury commercial film aesthetic with surgical focus clarity, silky smooth micro-glides, and tactile surfaces",
        "lighting_signature": "Sculpted soft rim lights, flawless specular highlights across glass, metal, and brushed surfaces",
        "color_grade": "Ultra-clean obsidian matte blacks, crisp neutral whites, and surgical jewel-tone accent light",
        "motion_feel": "Precision smooth micro-glides and fluid circular product reveals with zero shake",
    },
    "🌌 Epic Cosmic & Nature (Interstellar / BBC)": {
        "camera_rig": "Large-format theatrical epic film aesthetic with breathtaking scale and crisp foreground-to-horizon depth",
        "lighting_signature": "Radiant golden god-rays, dramatic rim eclipses, shimmering particulate dust and natural light refraction",
        "color_grade": "Awe-inspiring deep indigo shadows, luminous solar gold highlights, expansive theatrical contrast",
        "motion_feel": "Majestic weightless drifting views, soaring aerial sweeps, and graceful slow-motion physics",
    },
}

DEFAULT_CINEMA_PRESET: str = "🎬 Hollywood IMAX Documentary (Default)"

# Dedicated Selectable Background Music / Film Score Styles (powered by Vertex AI `lyria-002` + Custom Upload)
BGM_SCORE_PRESETS: Dict[str, str] = {
    "🤖 Auto-Match Topic & Niche (Smart AI Composer)": "",
    "🪔 Indian Devotional & Bhakti (Bansuri Flute, Tanpura, Sitar & Strings)": (
        "Soulful Indian devotional cinematic orchestral score at 74 BPM, expressive bansuri bamboo flute leading a "
        "reverent melody over a warm meditative tanpura drone, delicate sitar and sarangi harmonies, soft deep temple "
        "pakhawaj rhythm, and sweeping emotional strings, majestic bhakti atmosphere, strictly instrumental, no vocals"
    ),
    "⚔️ Epic Mythological & Mahabharata War (Shankh, Pakhawaj, Taiko & Brass)": (
        "Heroic Indian mythological epic cinema score at 92 BPM, resonant sacred shankh horn swells, thunderous deep "
        "pakhawaj and orchestral taiko war drums, dramatic soaring strings, bold low brass motifs, and intense ancient "
        "battlefield grandeur, strictly instrumental, no vocals"
    ),
    "🌿 Calm Spiritual Meditation & Healing (Soft Flute, Singing Bowls & Pads)": (
        "Serene spiritual meditation soundtrack at 62 BPM, airy gentle bansuri flute phrases, warm crystalline Tibetan "
        "singing bowl resonance, lush ethereal ambient string pads, deeply peaceful and uplifting temple morning mood, "
        "strictly instrumental, no vocals"
    ),
    "🎻 Hollywood Hans Zimmer Epic (Deep Cello, Brass Swells & Percussion)": (
        "Monumental Hollywood IMAX film score inspired by Hans Zimmer at 86 BPM, urgent deep cello ostinato, warm "
        "French horn brass swells, pulsing orchestral percussion, soaring emotional string crescendos, rich theatrical "
        "dynamic range, strictly instrumental, no vocals"
    ),
    "🕵️ Suspense & Dark Mystery (Ticking Pulse, Sub-Bass & Tense Strings)": (
        "Gripping investigative thriller documentary score at 96 BPM, crisp subtle clockwork ticking percussion, "
        "deep atmospheric sub-bass pulse, tense muted cello and dark piano motifs building continuous curiosity, "
        "strictly instrumental, no vocals"
    ),
    "🚀 Sci-Fi & Future Tech (Blade Runner Synth, Arpeggio & Deep Bass)": (
        "Futuristic Blade Runner style cyber-documentary soundtrack at 104 BPM, warm analog Vangelis-inspired synth "
        "pads, sleek driving bassline, crisp crystalline arpeggios, sleek modern sci-fi atmosphere, strictly instrumental, no vocals"
    ),
    "💼 Executive Finance & Documentary (Sleek Piano, Strings & Modern Pulse)": (
        "High-stakes modern financial documentary score at 100 BPM, crisp minimal grand piano motif, taut rhythmic "
        "pizzicato strings, punchy muted electronic beat, authoritative and energetic corporate storytelling mood, "
        "strictly instrumental, no vocals"
    ),
    "🎵 Upload My Own Custom BGM Track (.mp3 / .wav)": "__CUSTOM_UPLOAD__",
}

DEFAULT_BGM_PRESET: str = "🤖 Auto-Match Topic & Niche (Smart AI Composer)"


def get_bgm_preset_prompt(preset_name: Optional[str]) -> str:
    if preset_name and preset_name in BGM_SCORE_PRESETS:
        return BGM_SCORE_PRESETS[preset_name]
    return ""

# Rotating 8-shot theatrical framing grammar (strictly pure viewpoint motion — ZERO physical camera hardware terms!)
CINEMATIC_SHOT_CHOREOGRAPHY: List[Dict[str, str]] = [
    {
        "shot_type": "Sweeping Wide Establishing",
        "camera_move": "Smooth high sweeping aerial view gliding gently forward into the scene, expansive wide vista with layered foreground-to-horizon depth",
        "lighting": "Dramatic golden-hour or twilight volumetric light rays cutting through fine mist with crisp rim highlights",
    },
    {
        "shot_type": "Low-Angle Hero Tracking",
        "camera_move": "Dynamic low-angle forward-moving view gliding alongside the main subject at heroic eye-level with natural background motion blur",
        "lighting": "High-contrast motivated side lighting with gleaming natural reflections and rich theatrical shadows",
    },
    {
        "shot_type": "Intimate Macro Detail",
        "camera_move": "Ultra-smooth close-up view slowly gliding closer with razor-sharp focus and creamy blurred background revealing intricate physical textures",
        "lighting": "Sculpted precision rim backlighting catching micro-particles, specular edges, and subtle light bloom",
    },
    {
        "shot_type": "Smooth Circular Orbital Arc",
        "camera_move": "Fluid graceful 180-degree circular arc orbiting smoothly around the central subject, creating rich parallax across background depth layers",
        "lighting": "Atmospheric chiaroscuro key light with luminous practical accents and creamy out-of-focus background glow",
    },
    {
        "shot_type": "High Bird's-Eye Overhead Reveal",
        "camera_move": "Majestic top-down overhead view rising slowly upward to gradually reveal grand architectural, geographic, or natural scale",
        "lighting": "Crisp directional raking light casting long dramatic shadows across the scene below",
    },
    {
        "shot_type": "Graceful Slow-Motion Close-Up",
        "camera_move": "Silky slow-motion medium close-up capturing lifelike physical detail (floating embers, water droplets, wind-blown fabric, or dust motes)",
        "lighting": "Dramatic split-tone warm amber and twilight rim illumination carving crisp depth out of soft atmospheric haze",
    },
    {
        "shot_type": "Foreground Parallax Reveal",
        "camera_move": "Gentle sideways gliding view passing softly blurred foreground pillars, foliage, or architecture to unveil the focal subject cleanly",
        "lighting": "Warm interior firelight or lamp glow contrasting cool twilight atmosphere through soft mist",
    },
    {
        "shot_type": "Monumental Pull-Back Horizon Finale",
        "camera_move": "Expansive high pull-back smoothly rising away from the subject toward a glowing scenic horizon for a serene dramatic closure",
        "lighting": "Radiant horizon backlight, atmospheric golden bloom, deep theatrical contrast, timeless filmic finish",
    },
]

# Global strict language & anti-hallucination guard applied to EVERY video & image generation call
STRICT_ENGLISH_NO_FOREIGN_TEXT_RULE: str = (
    "STRICT VISUAL LANGUAGE RULE: NEVER render any Chinese, Mandarin, Kanji, Japanese, Korean, "
    "Cyrillic, Arabic, or garbled gibberish characters anywhere on vehicles, windshields, license plates, "
    "screens, billboards, signs, HUDs, or objects. Prefer completely textless photorealistic cinema; "
    "if any real-world label or HUD text is shown, it MUST be ONLY clean, accurately spelled standard English."
)

STRICT_PHYSICAL_REALISM_AND_NO_CAMERA_RULE: str = (
    "ZERO CAMERAS & PHYSICAL REALISM RULE: NEVER show any video camera, film camera, DSLR, tripod, lens, "
    "gimbal, microphone, lighting rig, film crew, smartphone, or modern anachronistic object anywhere in the frame. "
    "Maintain 100% realistic human and animal anatomy and natural physical laws (no surreal or misplaced liquids/limbs)."
)

NEGATIVE_PROMPT_BLACKLIST: str = (
    "NEGATIVE PROMPT BLACKLIST: Video camera, film camera, modern filming gear, camera crew, tripod, film crew, "
    "boom mic, studio lights, modern tech, lens, wires, production rigs, contemporary materials, plastic, "
    "fantastical artificial glow, surreal distortions, mutant animals, unnatural liquid from mouth, deformed anatomy, "
    "morphing faces, floating text, Chinese or foreign letters, watermarks."
)

VEO_STRICT_NEGATIVE_PROMPT: str = (
    "video camera, film camera, modern filming gear, camera crew, tripod, film crew, boom microphone, studio lights, "
    "modern tech, camera lens, wires, production rigs, DSLR, gimbal, Steadicam, drone, film crane, behind the scenes, "
    "contemporary materials, plastic, artificial glow, surreal distortions, mutant animals, unnatural liquid from mouth, "
    "deformed anatomy, extra limbs, morphing faces, "
    "Chinese text, Mandarin characters, Hanzi, Kanji, Japanese text, Korean Hangul, Cyrillic text, "
    "gibberish letters, garbled text, distorted license plates, watermarks, floating subtitles, text overlays, "
    "PowerPoint slides, flat 2D clipart, infographic bar charts, wireframe grid floor, neon grid clipart, "
    "cheesy plastic CGI, UI dashboard panels, split screen collage, abrupt jump cuts, blurry low resolution"
)


def get_cinema_preset(preset_name: Optional[str] = None) -> Dict[str, str]:
    if preset_name and preset_name in CINEMA_STYLE_PRESETS:
        return CINEMA_STYLE_PRESETS[preset_name]
    return CINEMA_STYLE_PRESETS[DEFAULT_CINEMA_PRESET]


def _scrub_camera_gear_and_anachronisms(text: str) -> str:
    """
    Deterministically strips physical cinema hardware brands & rig terms (`ARRI Alexa`, `Panavision`,
    `RED V-Raptor`, `Steadicam`, `gimbal`, `dolly`, `crane`, `drone`, `tripod`, `Camera tracks`, etc.)
    so video models NEVER render a physical video camera or film crew inside the scene!
    Also removes stray non-ASCII foreign words accidentally mixed into English visual prompts.
    """
    s = (text or "").strip()
    gear_replacements = [
        (
            r"\b(?:shot\s+)?on\s+ARRI\s+Alexa\s*\d*"
            r"(?:(?:,\s*|\s+)(?:with\s+)?(?:Panavision\s+)?(?:\d+mm\s+)?(?:Panavision\s+)?"
            r"(?:anamorphic|telephoto|wide|macro)(?:\s+prime)?(?:\s+(?:glass|lens(?:es)?))?"
            r"(?:\s+at\s+f/[\d.]+)?)?",
            "in widescreen theatrical film aesthetic",
        ),
        (r"\bARRI\s+Alexa\s*\d*\b", "theatrical film"),
        (r"\bPanavision\s+(?:\d+mm\s+)?anamorphic(?:\s+prime)?(?:\s+glass|\s+lens(?:es)?)?\b", "widescreen theatrical perspective"),
        (r"\bPanavision\b", "theatrical"),
        (r"\bRED\s+V-Raptor\s*8K\b", "ultra-crisp cinema"),
        (r"\bKodak\s+Vision3\s*500T\b", "classic celluloid"),
        (r"\brobotic\s+Bolt\s+motion-control(?:\s+macro)?(?:\s+lens)?\b", "ultra-smooth macro close-up"),
        (r"\b(?:ultra-smooth\s+)?motorized\s+(?:macro\s+)?(?:slider\s+)?(?:dolly\s+)?push-in\b", "ultra-smooth slow close-up glide"),
        (r"\b(?:fluid\s+)?(?:orbital\s+)?(?:180[- ]degree\s+|180°\s+)?Steadicam(?:\s+arc|\s+orbits?|\s+shot|\s+push-ins?|\s+tracking)?\b", "smooth circular gliding perspective"),
        (r"\b(?:aerial\s+|stabilized\s+|low-angle\s+)?gimbal(?:\s+tracking|\s+choreography|\s+shot)?\b", "smooth gliding perspective"),
        (r"\b(?:top-down\s+|aerial\s+|stabilized\s+|nocturnal\s+)?drone(?:\s+pull-back|\s+descent|\s+shot|\s+reveals?|\s+pulls\s+back)?\b", "high aerial overhead view"),
        (r"\b(?:overhead\s+|reverse\s+|elevated\s+|sweeping\s+|stabilized\s+top-down\s+)?crane(?:\s+reveal|\s+descent|\s+shot|\s+rise|\s+arcs?|\s+pulls\s+away|\s+rises)?\b", "sweeping elevated aerial view"),
        (r"\b(?:foreground\s+parallax\s+|micro-|slider\s+)?dolly(?:\s+shot|\s+slide|\s+glides?|\s+push-ins?)?\b", "smooth gliding perspective"),
        (r"\bwith\s+\d+mm\s+(?:anamorphic\s+|telephoto\s+|wide\s+)?(?:prime\s+)?(?:glass|lens(?:es)?)\b", "with rich cinematic depth"),
        (r"\b\d+mm\s+(?:anamorphic\s+|telephoto\s+|wide\s+|macro\s+)?(?:prime\s+)?(?:glass|lens(?:es)?)\b", "cinematic depth"),
        (r"\bCamera\s+(tracks|glides|slides|pulls|rises|pans|orbits|moves|sweeps)\b", r"The viewpoint smoothly \1"),
        (r"\bthe\s+camera\s+(tracks|glides|slides|pulls|rises|pans|orbits|moves|sweeps)\b", r"the viewpoint smoothly \1"),
        (r"\b(?:video|film|cinema)\s+camera\b", "theatrical perspective"),
        (r"\bcamera\s+style\b", "visual style"),
        (r"\bfilm\s+look\b", "natural theatrical aesthetic"),
        (r"\ban\s+actor\b", "a realistic historical figure"),
        (r"\bactors\b", "historical figures"),
        (r"\b120fps\b", "graceful slow-motion"),
        (r"\bat\s+f/1\.4\b", "with shallow depth of field"),
        (r"\bshallow\s+f/1\.4\b", "shallow"),
        (r"\bf/1\.4\b", "shallow"),
        (r"\bratusan\b", "hundreds of"),
    ]
    for pat, repl in gear_replacements:
        s = re.sub(pat, repl, s, flags=re.IGNORECASE)

    # Fix anatomical cow-milk wording if a legacy prompt omits "udder beneath her belly"
    if re.search(r"\bcow\b", s, flags=re.IGNORECASE) and re.search(r"\bmilk\b", s, flags=re.IGNORECASE):
        if not re.search(r"\budder\b", s, flags=re.IGNORECASE):
            s = re.sub(
                r"(pure\s+white\s+milk\s+flows\s+naturally)",
                "pure white milk streams naturally downward from her udder beneath her belly (while her head and closed mouth remain peaceful and calm)",
                s,
                flags=re.IGNORECASE,
            )

    # Strip stray non-ASCII script words (e.g., Devanagari leaked inside English visual prompt)
    s = re.sub(r"[^\x00-\x7F]+", " ", s)
    s = re.sub(r"\s{2,}", " ", s).strip()
    return s


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
    Elevates ANY scene prompt (new, user-edited, or legacy) into spotless theatrical cinematography
    optimized for Gemini Omni 1.2 Flash, Vertex Veo 3.1, and Google Flow:
    - Scrubs physical camera brand/rig words (`ARRI`, `Panavision`, `Steadicam`, `dolly`, `crane`, `drone`, `gimbal`)
      so video models NEVER draw a camera or film crew on screen!
    - Strips anti-cinema chart/UI clichés (`wireframe grid`, `summary card`, `analytical chart`, etc.)
    - Enforces era-authenticity (zero modern anachronisms in mythological/historical scenes) & anatomical realism
    - Embeds frame-synced pure-Foley sound design (NO spoken dialogue, NO singing, NO background music)
    - Enforces Omni's single-unbroken-shot rule (zero jump cuts) + zero foreign glyphs.
    """
    prof = get_niche_profile(niche)
    preset = get_cinema_preset(cinema_preset)
    choreo = CINEMATIC_SHOT_CHOREOGRAPHY[(max(1, scene_index) - 1) % len(CINEMATIC_SHOT_CHOREOGRAPHY)]

    cleaned = (raw_prompt or "").strip()
    # Idempotently strip prior appended boilerplate so re-enhancing (Agent 2 -> Agent 3) never duplicates clauses
    for marker in ("Sound design:", "Execution:", "ZERO CAMERAS", "NEGATIVE PROMPT BLACKLIST:", "STRICT VISUAL LANGUAGE RULE:"):
        if marker in cleaned:
            cleaned = cleaned.split(marker)[0].strip()

    # Replace chart/slide/grid clichés with photorealistic physical cinema language
    anti_cinema_replacements = [
        (r"\banalytical data chart\b", "photorealistic physical visual metaphor in real-world light"),
        (r"\bmotion graphic[s]?\b", "photorealistic live-action theatrical cinematography"),
        (r"\bkinetic summary card\b", "sweeping twilight architectural vista"),
        (r"\benergetic outro motion backdrop\b", "expansive golden-hour horizon pull-back"),
        (r"\bwireframe grid\b", "gleaming atmospheric stone and architectural reflections"),
        (r"\btypography panels?\b", "clean atmospheric practical lighting"),
        (r"\bcomparison scorecard\b", "dramatic real-world side-by-side physical contrast"),
        (r"\bannotated diagram reveal\b", "intimate macro physical cutaway in dramatic studio lighting"),
        (r"\binfographic\b", "tangible physical 3D real-world scene"),
    ]
    for pat, repl in anti_cinema_replacements:
        cleaned = re.sub(pat, repl, cleaned, flags=re.IGNORECASE)

    # Scrub physical camera/rig brands & stray foreign words
    cleaned = _scrub_camera_gear_and_anachronisms(cleaned)

    low = cleaned.lower()
    parts: List[str] = [cleaned.rstrip(".") + "."]

    # Inject clean framing perspective if missing concrete viewpoint motion
    has_view_motion = any(
        tok in low for tok in ("wide ", "low-angle", "macro", "orbital", "overhead", "bird's-eye", "slow-motion", "parallax", "pull-back", "tracking", "gliding", "sweeping")
    )
    if not has_view_motion:
        safe_cam = _scrub_camera_gear_and_anachronisms(camera_cue)
        cam_desc = safe_cam if safe_cam and len(safe_cam) > 20 else choreo["camera_move"]
        parts.append(f"Framing & Motion: {cam_desc}.")

    # Inject theatrical lighting & color grade if not already specified
    has_lighting_grade = any(
        tok in low for tok in ("chiaroscuro", "volumetric", "color grade", "film aesthetic", "dynamic range", "rim light", "sunbeams")
    )
    if not has_lighting_grade:
        parts.append(
            f"Look & Lighting: {preset['camera_rig']}; {preset['lighting_signature']}; "
            f"{preset['color_grade']}. Visual tone anchored to {prof['visual_style']}."
        )

    # Reinforce period authenticity for historical/mythological topics
    if niche in ("Religious & Devotional", "History & Geopolitics"):
        parts.append(
            "Period Authenticity: 100% era-authentic ancient/traditional environment, clothing, and props - "
            "strictly ZERO modern items, ZERO cameras, ZERO modern lights, ZERO wires or screens."
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
        f"no UI overlays. {STRICT_PHYSICAL_REALISM_AND_NO_CAMERA_RULE} {STRICT_ENGLISH_NO_FOREIGN_TEXT_RULE} "
        f"{NEGATIVE_PROMPT_BLACKLIST}"
    )
    return " ".join(parts)


def format_flow_prompts_export_txt(
    topic: str,
    niche: str,
    character_bible: str,
    scenes: List[Any],
    cinema_preset: Optional[str] = None,
    character_anchor_prompt: str = "",
) -> str:
    """
    Exports all scenes into a clean, ready-to-paste text sheet for Google Flow (Google AI Ultra),
    pre-scrubbed of camera hardware terms, carrying the inline Character Identity Lock, Step 0 Master
    Portrait prompt for Flow's 'Ingredients to Video', anatomical realism fixes, and Negative Blacklist.
    """
    clean_bible = (character_bible or "").strip()
    clean_anchor = (character_anchor_prompt or clean_bible).strip()

    # Build simple character-name detection so even legacy saved projects get [MAIN CHARACTER] tags
    char_tokens: List[str] = []
    if clean_bible:
        lead = re.split(r"[:\-\(\n,.]", clean_bible[:140])[0]
        stop_w = {
            "the", "and", "for", "with", "young", "indian", "warrior", "man", "woman",
            "ancient", "hero", "main", "character", "lord", "king", "prince", "baba",
        }
        for w in re.findall(r"[A-Za-z]{4,}", lead):
            wl = w.lower()
            if wl not in stop_w and wl not in char_tokens:
                char_tokens.append(wl)
                if wl.endswith("ik") and len(wl) >= 7:
                    char_tokens.append(wl[:-2])

    lines: List[str] = [
        "OMNI STUDIO -> GOOGLE FLOW (AI ULTRA) PRODUCTION SHEET",
        f"Topic: {topic} | Category: {niche} | Total Scenes: {len(scenes)}",
        "=" * 78,
        "HOW TO USE WITH GOOGLE AI ULTRA (ZERO EXTRA GOOGLE CLOUD VIDEO COST):",
        "1. Open Google Flow (https://labs.google/fx/tools/flow) signed into your Ultra account.",
        "2. STEP 0 (Same-Face Lock): Generate 1 portrait image using the MASTER CHARACTER PORTRAIT",
        "   prompt below and save/pin it as an Ingredient in Google Flow.",
        "3. For every scene marked [MAIN CHARACTER - ATTACH FACE INGREDIENT], switch Flow to",
        "   'Ingredients to Video', attach that 1 portrait, and paste the scene's FLOW PROMPT.",
        "4. Save downloaded clips named scene_01.mp4, scene_02.mp4 ... and bulk-drop them into",
        "   OMNI STUDIO Step 2 (automatic voiceover, music, subtitles, thumbnail & YouTube publish!).",
        "=" * 78,
        "",
    ]
    if clean_bible or clean_anchor:
        portrait_prompt = (
            "Photorealistic 8K theatrical character reference portrait, head-and-shoulders three-quarter "
            "angle looking clearly forward, crisp unobstructed facial features, natural warm skin texture, "
            "soft even neutral lighting against a plain warm dark-gray backdrop (no scenery, no crowd, "
            f"single person only): {clean_anchor}. {STRICT_PHYSICAL_REALISM_AND_NO_CAMERA_RULE} "
            f"{STRICT_ENGLISH_NO_FOREIGN_TEXT_RULE} {NEGATIVE_PROMPT_BLACKLIST}"
        )
        lines.extend([
            "STEP 0 — MASTER CHARACTER REFERENCE PORTRAIT PROMPT (GENERATE ONCE & PIN IN FLOW):",
            portrait_prompt,
            "",
            "LOCKED CHARACTER BIBLE (ENFORCED INSIDE EVERY MAIN CHARACTER SCENE BELOW):",
            clean_bible or clean_anchor,
            "",
            "=" * 78,
            "",
        ])

    for sc in scenes:
        s_idx = sc.scene_index if hasattr(sc, "scene_index") else sc.get("scene_index", 1)
        ch_lbl = sc.chapter_label if hasattr(sc, "chapter_label") else sc.get("chapter_label", "")
        raw_vp = sc.visual_prompt_veo_omni if hasattr(sc, "visual_prompt_veo_omni") else sc.get("visual_prompt_veo_omni", "")
        cam_c = sc.camera_and_lighting_cue if hasattr(sc, "camera_and_lighting_cue") else sc.get("camera_and_lighting_cue", "")
        sfx_c = sc.sfx_cue if hasattr(sc, "sfx_cue") else sc.get("sfx_cue", "")
        dur_s = sc.duration_sec if hasattr(sc, "duration_sec") else sc.get("duration_sec", 8.0)
        vo_txt = sc.voiceover_text if hasattr(sc, "voiceover_text") else sc.get("voiceover_text", "")
        feat_c = bool(sc.features_main_character if hasattr(sc, "features_main_character") else sc.get("features_main_character", False))
        if not feat_c and char_tokens:
            vp_low = (raw_vp or "").lower()
            is_scenery = any(k in vp_low for k in ("temple exterior", "aerial establishing", "crowd of", "devotees", "empty landscape"))
            if not is_scenery and any(re.search(rf"\b{re.escape(tok)}", vp_low) for tok in char_tokens):
                feat_c = True

        clean_p = build_cinematic_video_prompt(
            raw_vp,
            niche=niche,
            cinema_preset=cinema_preset,
            camera_cue=cam_c,
            sfx_cue=sfx_c,
            duration_sec=min(8.0, float(dur_s)),
            scene_index=int(s_idx),
        )
        if feat_c and clean_bible:
            clean_p = (
                "CHARACTER IDENTITY LOCK: Use the attached character reference portrait strictly for the "
                "EXACT SAME person's face, age, eye shape, forehead markings/tilak, hairstyle, and attire "
                "(do NOT copy the plain studio backdrop from the portrait). "
                f"Locked look: {clean_bible}. "
                f"{clean_p}"
            )

        char_tag = " [MAIN CHARACTER - ATTACH FACE INGREDIENT]" if feat_c else ""
        lines.extend([
            f"SCENE {int(s_idx):02d} — {ch_lbl}{char_tag}",
            f"Filename to save: scene_{int(s_idx):02d}.mp4",
            f"Voiceover cue: {vo_txt}",
            "FLOW PROMPT:",
            clean_p,
            "",
            "-" * 78,
            "",
        ])
    return "\n".join(lines)


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
