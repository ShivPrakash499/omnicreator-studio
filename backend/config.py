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


FLOW_SANITIZER_VERSION: str = "pg13-safe-v3"


def sanitize_policy_safe_visual_text(text: str) -> str:
    """
    Translates graphic gore, open-wound, blood, self-harm, or extreme-violence phrasing
    into 100% policy-safe PG-13 theatrical/mythological visual cinematography so Google Flow
    (Nano Banana Pro / Veo 3.1), Vertex Veo, and Gemini Omni never trigger 'harmful content'
    safety rejections while preserving full dramatic & mythological authenticity.
    """
    s = (text or "").strip()
    if not s:
        return s
    safe_replacements = [
        # Forehead wound / gem extraction (common in Ashwatthama / Mahabharata stories)
        (r"\b(?:deep\s+)?raw\s+crimson\s+(?:hollowed\s+|gem-socket\s+)?wound(?:\s+on\s+(?:his\s+|her\s+)?center-forehead)?\b",
         "faint crimson vermilion tilak mark and subtle weathered indentation on center-forehead"),
        (r"\b(?:his|her|their)\s+center-forehead\s+wound\b", "his weathered center-forehead tilak mark"),
        (r"\bcenter-forehead\s+wound\b", "weathered center-forehead tilak mark"),
        (r"\b(?:open|bleeding|festering|oozing|gory|gaping|hollowed|raw)\s+wounds?\b", "subtle weathered ancient mark"),
        (r"\bwounds?\b", "weathered mark"),
        (r"\btrembling\s+blood[-\s]?stained\s+fingers\b", "trembling dust-weathered hands"),
        (r"\bblood[-\s]?stained\b", "dust-weathered"),
        (r"\bblood[-\s]?soaked\b", "ash-dusted"),
        (r"\b(?:drenched|covered|dripping)\s+(?:in|with)\s+blood\b", "dusted with battlefield ash"),
        (r"\bbloody\b", "battle-worn"),
        (r"\bbleeding\b", "weathered"),
        (r"\bblood\b", "crimson vermilion dust"),
        (r"\bjust\s+carved\s+from\s+(?:the\s+)?", "gently lifted away from "),
        (r"\bcarved\s+from\s+(?:the\s+)?", "lifted away from "),
        (r"\bextracted\s+from\s+(?:his|her|their)\s+", "lifted away from "),
        (r"\bvisceral\s+crystalline\s+gem\s+extraction\s+resonance\b", "radiant crystalline gem chime"),
        (r"\bvisceral\b", "dramatic"),
        (r"\bwet\s+flesh\s+parting(?:\s+sound)?\b", "deep solemn temple chime resonance"),
        (r"\bflesh\b", "skin"),
        (r"\bheavy\s+ragged\s+breathing\s+of\s+pain\b", "deep solemn exhale"),
        (r"\bdrops\s+of\s+liquid\s+hitting\s+dusty\s+stone\b", "gentle wind stirring temple dust"),
        # General mythological/historical violence -> PG-13 theatrical framing
        (r"\b(?:severed|decapitated)\s+head\b", "fallen ancient warrior silhouette in twilight mist"),
        (r"\b(?:behead(?:ed|ing)?|decapitat(?:e|ed|ing|ion))\b", "solemn mythic defeat"),
        (r"\b(?:slaughter(?:ed|ing)?|massacre(?:d)?|butcher(?:ed|ing)?|murder(?:ed|er|ing)?|brutal\s+killing)\b", "dramatic mythic confrontation"),
        (r"\b(?:corpses?|dead\s+bodies|mutilated|dismembered|gore|gory)\b", "abandoned ancient shields and broken wooden chariot wheels in mist"),
        (r"\b(?:stab(?:bed|bing)?|slash(?:ed|ing)?)\b", "clashing ancient bronze blades"),
        (r"\b(?:suicide|self-harm|cutting\s+(?:himself|herself|his\s+own|her\s+own))\b", "solemn vow of renunciation"),
        (r"\b(?:unborn\s+child|womb|sleeping\s+children|killing\s+children)\b", "royal palace sanctuary"),
        (r"\bmutant\s+animals\b", "unrealistic animals"),
        (r"\bdeformed\s+anatomy\b", "distorted proportions"),
        (r"\bunnatural\s+liquid\s+from\s+mouth\b", "unnatural fluid physics"),
    ]
    for pat, repl in safe_replacements:
        s = re.sub(pat, repl, s, flags=re.IGNORECASE)
    s = re.sub(r"\s{2,}", " ", s).strip()
    return s


def _scrub_camera_gear_and_anachronisms(text: str) -> str:
    """
    Deterministically strips physical cinema hardware brands & rig terms (`ARRI Alexa`, `Panavision`,
    `RED V-Raptor`, `Steadicam`, `gimbal`, `dolly`, `crane`, `drone`, `tripod`, `Camera tracks`, etc.)
    so video models NEVER render a physical video camera or film crew inside the scene!
    Also applies PG-13 policy-safe visual phrasing and removes stray non-ASCII foreign words.
    """
    s = sanitize_policy_safe_visual_text((text or "").strip())
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
        (r"\btoward\s+the\s+camera\b", "toward the viewer"),
        (r"\binto\s+the\s+camera\b", "straight ahead"),
        (r"\bto\s+the\s+camera\b", "toward the viewer"),
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
    # Idempotently strip prior appended boilerplate so re-enhancing (Agent 2 -> Agent 3 -> Flow) never duplicates clauses
    for marker in (
        "Framing & Motion:",
        "Look & Lighting:",
        "Period Authenticity:",
        "Sound design:",
        "Execution:",
        "ZERO CAMERAS",
        "NEGATIVE PROMPT BLACKLIST:",
        "STRICT VISUAL LANGUAGE RULE:",
    ):
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
    clean_sfx = sanitize_policy_safe_visual_text((sfx_cue or "").strip())
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


def parse_characters_from_bible(
    character_bible: str,
    character_anchor_prompt: str = "",
) -> List[Dict[str, Any]]:
    """
    Parses one or more recurring characters from `character_bible` (e.g.,
    "Ashwatthama: 34-year-old... Shri Krishna: 32-year-old...") into structured
    character cards with `@Tag`, description, detection tokens, and a dedicated
    studio reference portrait prompt for Google Flow's `Characters` library.
    """
    clean_bible = (character_bible or "").strip()
    clean_anchor = (character_anchor_prompt or "").strip()
    if not clean_bible and not clean_anchor:
        return []

    stop_w = {
        "the", "and", "for", "with", "young", "indian", "warrior", "man", "woman",
        "ancient", "hero", "main", "character", "lord", "king", "prince", "baba",
        "shri", "sri", "bhagwan", "maharaj", "sage", "saint", "goddess", "devi",
        "locked", "look", "note", "portrait", "studio", "photorealistic",
    }
    raw_entries: List[Tuple[str, str]] = []

    if clean_bible:
        # Match "Name: description..." segments (handles single or multiple characters cleanly)
        hdr_re = re.compile(r"(?:^|(?<=\.\s)|(?<=\n))([A-Z][A-Za-z0-9'\-\(\) ]{1,36}?):\s+")
        matches = list(hdr_re.finditer(clean_bible))
        valid_matches = [
            m for m in matches
            if m.group(1).strip().lower() not in ("locked look", "main character", "note", "style", "setting")
        ]
        if valid_matches:
            for idx, m in enumerate(valid_matches):
                c_name = m.group(1).strip()
                desc_start = m.end()
                desc_end = valid_matches[idx + 1].start() if idx + 1 < len(valid_matches) else len(clean_bible)
                c_desc = clean_bible[desc_start:desc_end].strip().rstrip(".")
                if c_desc:
                    raw_entries.append((c_name, c_desc))
        else:
            lead = re.split(r"[:\-\(\n,.]", clean_bible[:80])[0].strip()
            fallback_name = lead if (2 <= len(lead) <= 32 and re.match(r"^[A-Za-z]", lead)) else "MainCharacter"
            raw_entries.append((fallback_name, clean_bible.rstrip(".")))
    elif clean_anchor:
        raw_entries.append(("MainCharacter", clean_anchor.rstrip(".")))

    parsed: List[Dict[str, Any]] = []
    for idx, (c_name, c_desc) in enumerate(raw_entries):
        tag_slug = re.sub(r"[^A-Za-z0-9]+", "", c_name) or f"Character{idx + 1}"
        tag = f"@{tag_slug}"
        # Build matching tokens (full name + distinctive proper-noun words)
        tokens: List[str] = []
        full_norm = re.sub(r"\s+", " ", re.sub(r"\([^)]*\)", "", c_name)).strip().lower()
        if full_norm and len(full_norm) >= 4:
            tokens.append(full_norm)
        for w in re.findall(r"[A-Za-z]{4,}", c_name):
            wl = w.lower()
            if wl not in stop_w and wl not in tokens:
                tokens.append(wl)
                if wl.endswith("ik") and len(wl) >= 7:
                    tokens.append(wl[:-2])

        # Use clean_anchor for single-character projects if provided; otherwise build a crisp per-character portrait prompt
        if len(raw_entries) == 1 and clean_anchor:
            portrait_body = _scrub_camera_gear_and_anachronisms(clean_anchor).rstrip(".")
        else:
            portrait_body = _scrub_camera_gear_and_anachronisms(f"{c_name}, {c_desc}").rstrip(".")

        portrait_prompt = (
            "Photorealistic 8K theatrical character reference portrait, waist-up three-quarter angle "
            "looking clearly forward, crisp unobstructed facial features, natural warm skin texture, "
            "soft even neutral lighting against a plain warm dark-gray backdrop (no scenery, no crowd, "
            f"single person only): {portrait_body}. "
            "ZERO cameras, ZERO modern gear, ZERO text, ZERO watermarks."
        )
        parsed.append({
            "name": c_name,
            "tag": tag,
            "description": _scrub_camera_gear_and_anachronisms(c_desc),
            "tokens": tokens,
            "portrait_prompt": portrait_prompt,
        })
    return parsed


def detect_scene_characters(
    scene_prompt: str,
    characters: List[Dict[str, Any]],
    features_main_character: bool = False,
) -> List[Dict[str, Any]]:
    """
    Determines which exact character(s) from `parse_characters_from_bible` appear in a given scene prompt.
    Prevents multi-character bleed (e.g., Krishna-only scenes attach ONLY @ShriKrishna, not @Ashwatthama!).
    """
    if not characters:
        return []
    vp_low = (scene_prompt or "").lower()
    matched: List[Dict[str, Any]] = []
    for ch in characters:
        if any(re.search(rf"\b{re.escape(tok)}\b", vp_low) for tok in ch.get("tokens", [])):
            matched.append(ch)
    if matched:
        return matched
    if features_main_character:
        is_pure_scenery = any(
            k in vp_low for k in ("temple exterior", "empty landscape", "unoccupied", "palm-leaf manuscript resting", "stone hourglass")
        )
        if not is_pure_scenery:
            return [characters[0]]
    return []


def format_flow_agent_memory_block(
    topic: str,
    niche: str,
    character_bible: str,
    cinema_preset: Optional[str] = None,
    character_anchor_prompt: str = "",
) -> str:
    """
    Returns a concise, paste-ready Project Memory block for Google Flow's
    `Agent settings -> Memory -> + Add new` panel so the Flow Agent enforces
    character lock, visual style, foley-only audio, and negative guardrails automatically.
    """
    prof = get_niche_profile(niche)
    preset = get_cinema_preset(cinema_preset)
    chars = parse_characters_from_bible(character_bible, character_anchor_prompt)

    lines: List[str] = [
        f"PROJECT: {topic} ({niche})",
        f"VISUAL STYLE: 16:9 widescreen theatrical cinema, {preset['camera_rig']}. {prof['visual_style']}.",
        "VIDEO DEFAULTS: Use Omni 1.2 Flash (8s, 16:9 landscape, 1 output/scene) for character-referenced scenes for best face consistency, and Veo 3.1 or Omni 1.2 Flash (8s, 16:9, 1 output/scene) for scenery scenes. Single unbroken continuous shot (strictly NO scene cuts, NO split screens, NO UI overlays).",
        "AUDIO RULE: Realistic frame-synced environmental foley ONLY. Strictly NO spoken dialogue, NO lip-syncing, NO human voices, NO singing, NO background music (OMNI STUDIO adds the locked narrator voiceover & continuous BGM after sewing).",
    ]
    if chars:
        lines.append("CHARACTER LOCK (ALWAYS USE SAVED 'Characters' PORTRAITS — NEVER COPY PLAIN STUDIO BACKDROP INTO SCENES):")
        for ch in chars:
            lines.append(f"- {ch['tag']} ({ch['name']}): {ch['description']}")
        lines.append("- On scenery/supporting scenes tagged 'ATTACH CHARACTERS: NONE', do NOT attach any saved character portrait.")
    if niche in ("Religious & Devotional", "History & Geopolitics"):
        lines.append("ERA AUTHENTICITY: 100% period-authentic ancient clothing, sandstone architecture, brass diyas, and props. Strictly ZERO modern items.")
    lines.append(
        "STRICT VISUAL GUARDRAILS: Keep all scenes PG-13 mythological cinema with natural lifelike human and animal "
        "proportions, calm realistic expressions, and authentic ancient textures. NEVER show video cameras, film cameras, "
        "DSLR rigs, tripods, lenses, gimbals, boom mics, studio lights, film crews, wires, smartphones, plastic, modern "
        "tech, morphing faces, floating text, Chinese or foreign letters, or watermarks."
    )
    return "\n".join(lines)


def format_flow_phase3_sew_prompt(
    topic: str,
    total_scenes: int,
) -> str:
    """
    Ready-to-paste Phase 3 prompt telling Google Flow Agent to sew all generated clips
    in exact order (`scene_01` -> `scene_XX`) inside Flow's `Scenes` builder into ONE
    single 16:9 master MP4 ready to download and enrich with audio/BGM/captions in OMNI STUDIO.
    """
    return (
        f"PHASE 3 — SEW ALL {total_scenes} SCENES INTO ONE MASTER VIDEO (IN FLOW 'Scenes' BUILDER) for \"{topic}\":\n"
        f"1. Open the project's Scenes timeline and place all {total_scenes} generated video clips in exact sequential order "
        f"from scene_01.mp4 through scene_{total_scenes:02d}.mp4 (verify no scene is skipped, duplicated, or out of order).\n"
        f"2. Join consecutive clips with clean, seamless theatrical cuts (either crisp straight cuts or subtle 0.25-second "
        f"soft cross-dissolves where scenes shift location). Keep every clip at its full original 8-second duration and 16:9 landscape framing.\n"
        f"3. AUDIO PRESERVATION: Keep each clip's subtle native environmental Foley sound effects ONLY. Do NOT add any spoken "
        f"voiceover, background music track, or on-screen text/subtitles (OMNI STUDIO will enrich this stitched master video with "
        f"studio narration, continuous BGM, sound polish, and active captions).\n"
        f"4. Render and prepare the single complete stitched 16:9 HD video (named final_flow_video_16x9.mp4) so I can download it."
    )


def format_flow_phase4_thumbnails_prompt(
    topic: str,
    niche: str,
    character_bible: str = "",
    character_anchor_prompt: str = "",
    *,
    thumbnail_hook_headline: str = "",
    thumbnail_badge_label: str = "",
    thumbnail_graphic_concept: str = "",
    language_tone: str = "",
) -> str:
    """
    Ready-to-paste Phase 4 prompt telling Google Flow Agent (using `Nano Banana Pro` + saved
    `@Characters`) to generate BOTH a 16:9 YouTube Long Video thumbnail and a 9:16 vertical
    YouTube Shorts thumbnail in PG-13 policy-safe, ultra-high-CTR theatrical quality.
    """
    prof = get_niche_profile(niche)
    chars = parse_characters_from_bible(character_bible, character_anchor_prompt)
    safe_concept = sanitize_policy_safe_visual_text(
        _scrub_camera_gear_and_anachronisms(thumbnail_graphic_concept or f"Dramatic epic cinematic key art representing {topic}")
    )
    headline = (thumbnail_hook_headline or "").strip()
    badge = (thumbnail_badge_label or prof.get("badge_prefix", "")).strip()
    char_clause = (
        f"Attach and lock our saved Characters ({' + '.join(c['tag'] for c in chars)}) so the exact same faces, "
        f"markings, crowns, hair, and costumes appear crisply with intense, dramatic theatrical expressions."
        if chars
        else "Create an iconic, high-impact focal subject in ultra-sharp photorealistic cinema lighting."
    )
    headline_16 = (
        f'Render bold, ultra-legible high-CTR headline text "{headline}" in clean bright saffron-gold and pure white '
        f"letters with thick dark outline and soft glow inside the opposite visual third (100% inside safe margins, zero cut-off letters)"
        + (f', with a compact top-corner badge reading "{badge}".' if badge else ".")
        if headline
        else "Keep the composition dramatic and clean with generous negative space on one side for bold YouTube title text."
    )
    headline_9 = (
        f'Render bold, centered high-CTR headline text "{headline}" in bright golden-white with thick dark outline '
        f"positioned cleanly in the upper-middle safe zone (keep the bottom 25% of the frame visually uncluttered so "
        f"YouTube Shorts captions and buttons never overlap text or faces)."
        if headline
        else "Keep the top and bottom 20% clean so YouTube Shorts UI never covers faces or key action."
    )

    return (
        f"PHASE 4 — GENERATE BOTH YOUTUBE THUMBNAILS (16:9 LONG + 9:16 SHORTS) for \"{topic}\":\n"
        f"Use Nano Banana Pro (1 output each). {char_clause}\n"
        f"Keep BOTH thumbnails strictly PG-13 epic mythological/theatrical cinema — natural lifelike proportions, "
        f"zero video cameras, zero modern items, zero watermarks, zero garbled extra text.\n\n"
        f"THUMBNAIL 1 — 16:9 LANDSCAPE (YouTube Full-Length Video | Download as: thumbnail_16x9.png):\n"
        f"Aspect Ratio: 16:9 Landscape. High-CTR theatrical movie-poster YouTube thumbnail. Visual scene: {safe_concept}. "
        f"Visual style: {prof['visual_style']}. Dramatic high-contrast volumetric backlighting, glowing golden embers, "
        f"razor-sharp subject separation against deep twilight shadows, intense emotional storytelling. {headline_16}\n\n"
        f"THUMBNAIL 2 — 9:16 VERTICAL PORTRAIT (YouTube Shorts Cover | Download as: thumbnail_9x16.png):\n"
        f"Aspect Ratio: 9:16 Vertical Portrait. Full-bleed high-CTR vertical YouTube Shorts cover matching the exact same "
        f"cinematic color palette, characters, and epic lighting as Thumbnail 1. Visual scene: {safe_concept}. "
        f"Place the main character(s) powerfully framed in the center with radiant volumetric rim light and glowing embers. {headline_9}"
    )


def format_flow_agent_kickoff_prompt(
    topic: str,
    total_scenes: int,
    character_bible: str = "",
    character_anchor_prompt: str = "",
    batch_size: int = 6,
) -> str:
    """
    Returns a short, crystal-clear kickoff prompt to paste into Google Flow's
    Agent bar (`Describe your goal`) right after uploading the Holistic Master File.
    """
    chars = parse_characters_from_bible(character_bible, character_anchor_prompt)
    first_end = min(total_scenes, batch_size)
    if chars:
        tag_list = ", ".join(ch["tag"] for ch in chars)
        return (
            f"I uploaded our complete 4-phase production blueprint ({total_scenes} scenes + sewing + 16:9 & 9:16 thumbnails) for \"{topic}\". "
            f"Follow our Project Memory rules and execute in 4 strict phases:\n"
            f"1) PHASE 1 ONLY RIGHT NOW: Generate 1 clean 16:9 studio reference portrait (Nano Banana Pro, 1 output each) "
            f"for each locked character listed in Phase 1 ({tag_list}), save them into the project's Characters library "
            f"under those exact names, and STOP so I can approve the faces before spending video credits.\n"
            f"2) PHASE 2 (AFTER MY APPROVAL): Generate the {total_scenes} clips sequentially in batches of {batch_size} "
            f"(Batch 1: scene_01 to scene_{first_end:02d}, then wait for my \"next\" for each batch) using Omni 1.2 Flash "
            f"(16:9, 8s, 1 output) for character scenes and Veo 3.1 / Omni 1.2 Flash for scenery. Strictly obey ATTACH CHARACTERS, "
            f"foley-only audio (zero speech/music), PG-13 visuals, zero cameras/text, labeled scene_01..scene_{total_scenes:02d}.\n"
            f"3) PHASE 3 (AFTER ALL SCENES COMPLETE): Sew scene_01..scene_{total_scenes:02d} sequentially in the Scenes builder "
            f"into one complete 16:9 video (`final_flow_video_16x9.mp4`) keeping native foley only (no voiceover/BGM).\n"
            f"4) PHASE 4: Generate BOTH thumbnails (16:9 `thumbnail_16x9.png` + 9:16 `thumbnail_9x16.png`) with Nano Banana Pro using our locked Characters."
        )
    return (
        f"I uploaded our complete production blueprint ({total_scenes} scenes + sewing + 16:9 & 9:16 thumbnails) for \"{topic}\". "
        f"Follow our Project Memory rules: generate the {total_scenes} clips sequentially in batches of {batch_size} "
        f"(Batch 1: scene_01 to scene_{first_end:02d}, then wait for my \"next\" for each batch) using Veo 3.1 / Omni 1.2 Flash "
        f"(16:9, 8s, 1 output), foley-only audio (zero speech/music), zero cameras/text, labeled scene_01..scene_{total_scenes:02d}. "
        f"Then execute Phase 3 (sew all {total_scenes} clips in Scenes into one 16:9 video) and Phase 4 (generate 16:9 & 9:16 thumbnails with Nano Banana Pro)."
    )


def _format_single_flow_scene_lines(
    sc: Any,
    *,
    fallback_idx: int,
    niche: str,
    cinema_preset: Optional[str],
    chars: List[Dict[str, Any]],
) -> List[str]:
    """Formats one deduplicated, character-routed scene block for Google Flow Agent Mode."""
    s_idx = sc.scene_index if hasattr(sc, "scene_index") else sc.get("scene_index", fallback_idx)
    ch_lbl = sc.chapter_label if hasattr(sc, "chapter_label") else sc.get("chapter_label", "")
    raw_vp = sc.visual_prompt_veo_omni if hasattr(sc, "visual_prompt_veo_omni") else sc.get("visual_prompt_veo_omni", "")
    cam_c = sc.camera_and_lighting_cue if hasattr(sc, "camera_and_lighting_cue") else sc.get("camera_and_lighting_cue", "")
    sfx_c = sc.sfx_cue if hasattr(sc, "sfx_cue") else sc.get("sfx_cue", "")
    dur_s = sc.duration_sec if hasattr(sc, "duration_sec") else sc.get("duration_sec", 8.0)
    vo_txt = sc.voiceover_text if hasattr(sc, "voiceover_text") else sc.get("voiceover_text", "")
    feat_c = bool(sc.features_main_character if hasattr(sc, "features_main_character") else sc.get("features_main_character", False))

    scene_chars = detect_scene_characters(raw_vp, chars, features_main_character=feat_c)

    # Build clean, deduplicated cinematic prompt (no duplicate Period Authenticity!)
    full_clean = build_cinematic_video_prompt(
        raw_vp,
        niche=niche,
        cinema_preset=cinema_preset,
        camera_cue=cam_c,
        sfx_cue=sfx_c,
        duration_sec=min(8.0, float(dur_s)),
        scene_index=int(s_idx),
    )
    # Replace verbose repeated footer with tight, policy-safe per-scene guard (avoid trigger words even in negatives!)
    short_clean = full_clean.split("ZERO CAMERAS")[0].strip()
    short_clean = (
        f"{short_clean} "
        "STYLE GUARD: PG-13 epic theatrical cinema, natural lifelike proportions, no video or film camera, "
        "no tripod, no film crew, no modern gear, no spoken dialogue or music, no on-screen text, no watermarks."
    )

    if scene_chars:
        attach_str = " + ".join(c["tag"] for c in scene_chars)
        mode_str = f"Ingredients to Video — ATTACH CHARACTERS: {attach_str}"
        lock_prefix = (
            f"CHARACTER LOCK ({attach_str}): Match the exact face, age, markings, hairstyle, and attire of "
            f"{attach_str} from Characters (do NOT copy the plain studio backdrop). "
        )
        final_prompt = lock_prefix + short_clean
    else:
        mode_str = "Text to Video — ATTACH CHARACTERS: NONE (Scenery / Supporting Only)"
        final_prompt = short_clean

    # NOTE: Intentionally omit Hindi/narrative voiceover cues & non-ASCII chapter titles from Flow prompts so dramatic
    # narration words never trip Google Flow's text safety classifier (Flow generates visual foley only; OMNI STUDIO adds VO).
    ascii_ch = sanitize_policy_safe_visual_text(_scrub_camera_gear_and_anachronisms(ch_lbl))
    clean_hdr = f"SCENE {int(s_idx):02d} — {ascii_ch}" if len(re.findall(r"[A-Za-z]", ascii_ch)) >= 4 else f"SCENE {int(s_idx):02d}"
    return [
        clean_hdr,
        f"CLIP FILENAME: scene_{int(s_idx):02d}.mp4",
        f"MODE & CHARACTERS: {mode_str}",
        "SCENE PROMPT:",
        final_prompt,
        "",
        "-" * 78,
        "",
    ]


def build_flow_agent_copy_blocks(
    topic: str,
    niche: str,
    character_bible: str,
    scenes: List[Any],
    cinema_preset: Optional[str] = None,
    character_anchor_prompt: str = "",
    batch_size: int = 6,
    *,
    thumbnail_hook_headline: str = "",
    thumbnail_badge_label: str = "",
    thumbnail_graphic_concept: str = "",
    language_tone: str = "",
) -> Dict[str, Any]:
    """
    Builds ready-to-copy 1-click prompt blocks for Google Flow Agent Mode side-by-side workflow:
    - `memory`: Paste once into Flow's `Agent settings -> Memory -> + Add new`
    - `phase1_prompt`: Self-contained Phase 1 prompt to generate & save locked `@Character` portraits first
    - `batches`: List of self-contained 6-scene batch prompts (`Batch 1 (01-06)` .. `Batch N`) ready to paste
      straight into Flow's `Describe your goal` / `Use side panel` even without uploading a `.txt` file!
    - `phase3_sew_prompt`: Prompt instructing Flow Agent to sew all clips sequentially in `Scenes` into 1 MP4
    - `phase4_thumbnails_prompt`: Prompt instructing Flow Agent to generate BOTH 16:9 & 9:16 thumbnails with Nano Banana Pro
    - `kickoff`: Short kickoff prompt when uploading the full Master `.txt` file via `+`
    """
    chars = parse_characters_from_bible(character_bible, character_anchor_prompt)
    memory_txt = format_flow_agent_memory_block(
        topic=topic,
        niche=niche,
        character_bible=character_bible,
        cinema_preset=cinema_preset,
        character_anchor_prompt=character_anchor_prompt,
    )
    total_scenes = len(scenes)
    num_batches = max(1, (total_scenes + batch_size - 1) // batch_size)

    phase1_prompt = ""
    if chars:
        tag_list = ", ".join(ch["tag"] for ch in chars)
        p1_lines: List[str] = [
            f"PHASE 1 ONLY (CHARACTER LOCK) for \"{topic}\":",
            f"Generate 1 clean 16:9 studio reference portrait (Nano Banana Pro, 1 output each) for the {len(chars)} locked character(s) below ({tag_list}).",
            "Save each generated portrait into this project's Characters library under its exact @Name below, then STOP and wait for my face approval before generating any videos.",
            "",
        ]
        for c_idx, ch in enumerate(chars, start=1):
            p1_lines.extend([
                f"CHARACTER {c_idx}: {ch['name']}  |  Save in Characters as: {ch['tag']}",
                "PORTRAIT PROMPT:",
                ch["portrait_prompt"],
                "",
            ])
        phase1_prompt = "\n".join(p1_lines).strip()

    batches: List[Dict[str, Any]] = []
    for b_idx in range(num_batches):
        start_0 = b_idx * batch_size
        end_0 = min(total_scenes, start_0 + batch_size)
        slice_scenes = scenes[start_0:end_0]
        if not slice_scenes:
            continue
        b_num = b_idx + 1
        first_s = slice_scenes[0].scene_index if hasattr(slice_scenes[0], "scene_index") else slice_scenes[0].get("scene_index", start_0 + 1)
        last_s = slice_scenes[-1].scene_index if hasattr(slice_scenes[-1], "scene_index") else slice_scenes[-1].get("scene_index", end_0)
        attached_in_batch = sum(
            1
            for s in slice_scenes
            if (s.asset_mode if hasattr(s, "asset_mode") else s.get("asset_mode")) == "custom_upload"
            and bool(((s.custom_asset_path if hasattr(s, "custom_asset_path") else s.get("custom_asset_path")) or "").strip())
        )

        char_rule = (
            "Use Omni 1.2 Flash (8s, 16:9, 1 output) for character-referenced scenes and Veo 3.1 or Omni 1.2 Flash for scenery scenes. "
            "Strictly obey each scene's ATTACH CHARACTERS tag using our saved Characters portraits "
            "(and attach NO character portrait on scenes marked NONE)."
            if chars
            else "Use Veo 3.1 or Omni 1.2 Flash (8s, 16:9, 1 output) for pure Text-to-Video scenes (no recurring character lock)."
        )
        b_lines: List[str] = [
            f"PHASE 2 — BATCH {b_num} OF {num_batches} (SCENES {int(first_s):02d}–{int(last_s):02d}) for \"{topic}\":",
            f"Generate ONLY these {len(slice_scenes)} clips sequentially (8s continuous single shot each). "
            f"{char_rule} Follow our Project Memory rules strictly: realistic physical foley ONLY (ZERO spoken dialogue, ZERO voices, ZERO music), "
            f"PG-13 visuals, ZERO cameras/tripods/film crew/modern gear, ZERO foreign or garbled text. Label every clip clearly as scene_{int(first_s):02d}.mp4 through scene_{int(last_s):02d}.mp4.",
            "",
        ]
        for offset, sc in enumerate(slice_scenes):
            b_lines.extend(
                _format_single_flow_scene_lines(
                    sc,
                    fallback_idx=start_0 + offset + 1,
                    niche=niche,
                    cinema_preset=cinema_preset,
                    chars=chars,
                )
            )
        batches.append({
            "batch_num": b_num,
            "total_batches": num_batches,
            "start_scene": int(first_s),
            "end_scene": int(last_s),
            "scene_count": len(slice_scenes),
            "attached_count": attached_in_batch,
            "label": f"Batch {b_num} ({int(first_s):02d}–{int(last_s):02d})",
            "prompt_text": "\n".join(b_lines).strip(),
        })

    phase3_sew_prompt = format_flow_phase3_sew_prompt(topic=topic, total_scenes=total_scenes)
    phase4_thumbnails_prompt = format_flow_phase4_thumbnails_prompt(
        topic=topic,
        niche=niche,
        character_bible=character_bible,
        character_anchor_prompt=character_anchor_prompt,
        thumbnail_hook_headline=thumbnail_hook_headline,
        thumbnail_badge_label=thumbnail_badge_label,
        thumbnail_graphic_concept=thumbnail_graphic_concept,
        language_tone=language_tone,
    )
    kickoff_txt = format_flow_agent_kickoff_prompt(
        topic=topic,
        total_scenes=total_scenes,
        character_bible=character_bible,
        character_anchor_prompt=character_anchor_prompt,
        batch_size=batch_size,
    )
    return {
        "characters": chars,
        "memory": memory_txt,
        "phase1_prompt": phase1_prompt,
        "batches": batches,
        "phase3_sew_prompt": phase3_sew_prompt,
        "phase4_thumbnails_prompt": phase4_thumbnails_prompt,
        "kickoff": kickoff_txt,
    }


def format_flow_prompts_export_txt(
    topic: str,
    niche: str,
    character_bible: str,
    scenes: List[Any],
    cinema_preset: Optional[str] = None,
    character_anchor_prompt: str = "",
    batch_size: int = 6,
    *,
    thumbnail_hook_headline: str = "",
    thumbnail_badge_label: str = "",
    thumbnail_graphic_concept: str = "",
    language_tone: str = "",
) -> str:
    """
    Exports a Holistic 4-Phase Google Flow Agent Master Production Blueprint (.txt):
    - Phase 1: Dedicated studio reference portrait prompt for EVERY parsed character (`Characters` lock)
    - Phase 2: All scenes cleanly grouped into batches of 6 (`Omni 1.2 Flash` / `Veo 3.1`, Foley-only, PG-13 safe)
    - Phase 3: Sewing prompt to assemble all clips in Flow's `Scenes` builder into ONE 16:9 master MP4
    - Phase 4: Thumbnail prompts for BOTH 16:9 Long Video & 9:16 Shorts covers (`Nano Banana Pro`)
    """
    chars = parse_characters_from_bible(character_bible, character_anchor_prompt)
    memory_block = format_flow_agent_memory_block(
        topic=topic,
        niche=niche,
        character_bible=character_bible,
        cinema_preset=cinema_preset,
        character_anchor_prompt=character_anchor_prompt,
    )
    total_scenes = len(scenes)
    num_batches = max(1, (total_scenes + batch_size - 1) // batch_size)

    lines: List[str] = [
        "==============================================================================",
        "OMNI STUDIO -> GOOGLE FLOW AGENT HOLISTIC 4-PHASE PRODUCTION FILE",
        f"Topic: {topic} | Category: {niche} | Total Scenes: {total_scenes} ({num_batches} Batches of {batch_size})",
        "==============================================================================",
        "AGENT EXECUTION PROTOCOL (READ BEFORE GENERATING):",
        "- VIDEO MODEL: Use Omni 1.2 Flash (8s, 16:9, 1 output) for character-referenced scenes,",
        "  and Veo 3.1 or Omni 1.2 Flash (8s, 16:9, 1 output) for pure scenery scenes.",
        "- IMAGES & THUMBNAILS: Nano Banana Pro (1 output each).",
        "- SAFETY: Keep 'Confirm before generating' = Always so credits are confirmed per batch.",
        "- AUDIO: Realistic physical foley ONLY. Strictly NO spoken dialogue, NO singing, NO music",
        "  (OMNI STUDIO enriches the final stitched video with locked Hindi/English narration, continuous BGM & captions).",
        "- VISUALS: PG-13 epic cinema, single unbroken 8s shot per scene, ZERO cameras/tripods/film crew, ZERO text.",
        "- DELIVERABLES TO DOWNLOAD & UPLOAD TO OMNI STUDIO STEP 3:",
        "  1) final_flow_video_16x9.mp4 (from Phase 3 Scenes sew)",
        "  2) thumbnail_16x9.png        (from Phase 4)",
        "  3) thumbnail_9x16.png        (from Phase 4)",
        "",
        "--- PROJECT MEMORY SUMMARY (ALSO PASTE INTO 'Agent settings -> Memory') ---",
        memory_block,
        "==============================================================================",
        "",
    ]

    if chars:
        lines.extend([
            "==============================================================================",
            f"PHASE 1 — GENERATE & SAVE {len(chars)} LOCKED CHARACTER(S) FIRST (THEN STOP FOR APPROVAL)",
            "Instructions for Flow Agent: Generate 1 reference portrait per character below using",
            "Nano Banana Pro (16:9, 1 output each), save each into the project's 'Characters' library",
            "with the exact @Name below, and PAUSE for user face approval before starting Phase 2.",
            "==============================================================================",
            "",
        ])
        for c_idx, ch in enumerate(chars, start=1):
            lines.extend([
                f"CHARACTER {c_idx}: {ch['name']}  |  Save in Characters as: {ch['tag']}",
                "PORTRAIT PROMPT:",
                ch["portrait_prompt"],
                "",
            ])

    lines.extend([
        "==============================================================================",
        f"PHASE 2 — SEQUENTIAL VIDEO QUEUE ({total_scenes} SCENES IN {num_batches} BATCHES OF {batch_size})",
        "Instructions for Flow Agent: Generate ONLY ONE BATCH AT A TIME unless the user explicitly",
        "says 'generate all remaining batches'. For each scene, obey ATTACH CHARACTERS strictly:",
        "- If @Character tag(s) are listed -> use Omni 1.2 Flash + attach ONLY those saved Character(s).",
        "- If 'NONE' is listed -> pure Text-to-Video (do NOT attach any Character reference).",
        "==============================================================================",
        "",
    ])

    for idx_0, sc in enumerate(scenes):
        if idx_0 % batch_size == 0:
            b_num = (idx_0 // batch_size) + 1
            b_start = idx_0 + 1
            b_end = min(total_scenes, idx_0 + batch_size)
            lines.extend([
                f"#################### BATCH {b_num} OF {num_batches} (SCENES {b_start:02d} - {b_end:02d}) ####################",
                "",
            ])
        lines.extend(
            _format_single_flow_scene_lines(
                sc,
                fallback_idx=idx_0 + 1,
                niche=niche,
                cinema_preset=cinema_preset,
                chars=chars,
            )
        )

    lines.extend([
        "==============================================================================",
        "PHASE 3 — SEW ALL CLIPS INTO ONE MASTER VIDEO (FLOW 'Scenes' BUILDER)",
        "==============================================================================",
        format_flow_phase3_sew_prompt(topic=topic, total_scenes=total_scenes),
        "",
        "==============================================================================",
        "PHASE 4 — GENERATE BOTH 16:9 & 9:16 THUMBNAILS (NANO BANANA PRO)",
        "==============================================================================",
        format_flow_phase4_thumbnails_prompt(
            topic=topic,
            niche=niche,
            character_bible=character_bible,
            character_anchor_prompt=character_anchor_prompt,
            thumbnail_hook_headline=thumbnail_hook_headline,
            thumbnail_badge_label=thumbnail_badge_label,
            thumbnail_graphic_concept=thumbnail_graphic_concept,
            language_tone=language_tone,
        ),
        "",
        "==============================================================================",
        "FINAL STEP: Download (1) final_flow_video_16x9.mp4, (2) thumbnail_16x9.png, and",
        "(3) thumbnail_9x16.png -> Upload all 3 in OMNI STUDIO Step 3 ('Upload Sewn Flow Video')",
        "to automatically add Hindi/English Voiceover, Continuous Devotional BGM, Active Captions,",
        "and the 10-20s Hook Short (~Rs 15), then publish straight to YouTube in Step 4!",
        "==============================================================================",
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
