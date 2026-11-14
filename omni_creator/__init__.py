"""
OMNI CREATOR — Ultra-Realistic 3D Hinglish Science Video & SEO Engine (Classes 9-12)
====================================================================================
Modular pipeline package containing:
- Module A: `seo_keyword_engine.py`
- Module B: `script_and_pedagogy_agent.py`
- Module C: `visual_3d_generator.py`
- Module D: `thumbnail_hook_studio.py`
- Module E: `compositor_and_packager.py`
"""

from config.models import (
    FRONTIER_BRAIN_MODEL,
    FRONTIER_BRAIN_FALLBACK_MODEL,
    ORCHESTRATOR_MODEL,
    IMAGE_4K_PRO_MODEL,
    IMAGE_CONTINUITY_MODEL,
    VIDEO_OMNI_MODEL,
    TTS_EXPRESSIVE_MODEL,
    TRANSCRIBE_MODEL,
    MUSIC_LYRIA_MODEL,
    OmniModelConfig,
    estimate_pipeline_credits,
)
from schemas.blueprint import (
    OmniCreatorInput,
    KeywordCandidate,
    KeywordStrategy,
    ChapterVideoBlueprint,
    ThumbnailVariantSpec,
    YouTubeSEOPackage,
)

__all__ = [
    "FRONTIER_BRAIN_MODEL",
    "FRONTIER_BRAIN_FALLBACK_MODEL",
    "ORCHESTRATOR_MODEL",
    "IMAGE_4K_PRO_MODEL",
    "IMAGE_CONTINUITY_MODEL",
    "VIDEO_OMNI_MODEL",
    "TTS_EXPRESSIVE_MODEL",
    "TRANSCRIBE_MODEL",
    "MUSIC_LYRIA_MODEL",
    "OmniModelConfig",
    "estimate_pipeline_credits",
    "OmniCreatorInput",
    "KeywordCandidate",
    "KeywordStrategy",
    "ChapterVideoBlueprint",
    "ThumbnailVariantSpec",
    "YouTubeSEOPackage",
]
