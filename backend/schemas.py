"""
OMNI STUDIO — Strict Pydantic v2 Data Contracts (`backend/schemas.py`)
======================================================================
Typed state contracts flowing cleanly across all 4 sequential agents:
- Agent 1: `Agent1Output` (YouTube Competitor Mining + SEO Package + High-Retention Storyboard)
- Agent 2: `Agent2Output` (30-50 Granular Scenes with 8-12s Reset Rule + Multi-Model Prompts + Vocal Cues)
- Agent 3: `Agent3Output` (Rendered Media Bundle: 16:9 1080p, 9:16 Shorts, .ass Subtitles, High-CTR Thumbnail)
- Agent 4: `Agent4Output` (Direct YouTube Resumable Upload & Scheduling Result)
"""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator


# ==============================================================================
# AGENT 1: SEARCH, SEO & STORYBOARD MANIFEST
# ==============================================================================
class CompetitorVideoInsight(BaseModel):
    model_config = ConfigDict(extra="ignore")

    video_id: str = ""
    title: str
    channel_title: str = ""
    view_count: int = 0
    hook_pattern: str = ""
    pacing_vibe: str = ""
    url: str = ""


class StoryboardBeat(BaseModel):
    model_config = ConfigDict(extra="ignore")

    beat_id: int = Field(..., ge=1)
    phase: Literal["Visual_Hook_0_45s", "Core_Act", "Micro_Retention_Loop", "Climax_Aha", "Outro_CTA"]
    beat_title: str
    start_sec: float = Field(..., ge=0.0)
    duration_sec: float = Field(..., ge=8.0, le=120.0)
    narrative_summary: str
    retention_device: str = Field(
        default="Visual pattern shift + curiosity question",
        description="Specific micro-retention hook, pattern interrupt, or visual reset trigger.",
    )
    visual_direction: str


class Agent1Output(BaseModel):
    model_config = ConfigDict(extra="ignore")

    topic: str
    niche: str
    language_tone: str
    target_duration_minutes: float = Field(default=6.0, ge=1.0, le=12.0)
    competitor_insights: List[CompetitorVideoInsight] = Field(default_factory=list)
    common_audience_questions: List[str] = Field(default_factory=list)
    extracted_visual_hooks: List[str] = Field(default_factory=list)
    bgm_style_reference: str = Field(
        default="High-spirited modern documentary electronic pulse inspired by top-performing search videos"
    )
    title_options: List[str] = Field(..., min_length=3, max_length=3)
    selected_title: str
    seo_description: str
    tags: List[str] = Field(..., min_length=20)
    storyboard_beats: List[StoryboardBeat] = Field(..., min_length=5)
    hook_script_0_45s: str
    climax_misconception_aha: str
    outro_cta_script: str
    short_hook_script: str = Field(
        default="",
        description="Punchy 26-38 word (10-18s) curiosity/fear/shock cliffhanger hook for the 9:16 YouTube Short directing viewers to the full video link in the description.",
    )
    thumbnail_hook_headline: str = Field(
        default="THE HIDDEN TRUTH!",
        description="Bold 2-4 word high-CTR thumbnail headline matching the topic.",
    )
    thumbnail_badge_label: str = Field(
        default="DEEP DIVE",
        description="Compact topic/niche badge label for thumbnail corner.",
    )
    thumbnail_graphic_concept: str = Field(
        default="Glowing futuristic holographic infographic and 3D icons symbolizing the video topic",
        description="Concrete visual objects/diagrams drawn opposite @jwalashiva on the thumbnail.",
    )
    character_bible: str = Field(
        default="",
        description="Immutable physical appearance sheet (age, face, skin tone, hair, markings/tilak, attire, props) for the recurring main character(s) so their face stays identical across every scene.",
    )
    character_anchor_prompt: str = Field(
        default="",
        description="Photorealistic neutral-backdrop studio portrait prompt of the main recurring character used as visual face reference for all scenes.",
    )


# ==============================================================================
# AGENT 2: GRANULAR SCENE-BY-SCENE MULTI-MODEL SCRIPTING (30-50 SCENES, 8-12s)
# ==============================================================================
class SceneClipSpec(BaseModel):
    model_config = ConfigDict(extra="ignore")

    scene_index: int = Field(..., ge=1)
    beat_phase: str = "Core_Act"
    chapter_label: str = ""
    start_sec: float = 0.0
    duration_sec: float = Field(default=10.0, ge=6.0, le=14.0)
    asset_mode: Literal["ai_video", "motion_graphics", "custom_upload"] = "ai_video"
    motion_graphic_type: Optional[Literal["none", "manim_formula", "data_chart", "comparison_chart", "timeline_chart"]] = "none"
    motion_graphic_payload: Dict[str, Any] = Field(default_factory=dict)
    visual_prompt_veo_omni: str = Field(..., min_length=15)
    camera_and_lighting_cue: str = "Smooth macro dolly-in, high-contrast studio rim lighting"
    voiceover_text: str = Field(..., min_length=10)
    ssml_voice_cues: str = Field(
        default="",
        description="Voiceover enriched with expressive emotion notes & <break time='0.4s'/> pauses.",
    )
    on_screen_callout: str = ""
    sfx_cue: str = "subtle whoosh transition"
    features_main_character: bool = False
    custom_asset_path: Optional[str] = None

    @field_validator("duration_sec")
    @classmethod
    def clamp_scene_duration(cls, v: float) -> float:
        return round(max(6.0, min(14.0, float(v))), 1)


class Agent2Output(BaseModel):
    model_config = ConfigDict(extra="ignore")

    topic: str
    niche: str
    language_tone: str
    total_scenes: int
    total_estimated_duration_sec: float
    chapters_markdown: str = ""
    scenes: List[SceneClipSpec] = Field(..., min_length=6)


# ==============================================================================
# AGENT 3: MEDIA GENERATOR & COMPOSER OUTPUT
# ==============================================================================
class RenderedSceneArtifact(BaseModel):
    model_config = ConfigDict(extra="ignore")

    scene_index: int
    audio_path: str
    actual_audio_duration_sec: float
    visual_path: str
    asset_source: str


class Agent3Output(BaseModel):
    model_config = ConfigDict(extra="ignore")

    project_dir: str
    video_16x9_path: str
    video_9x16_shorts_path: str
    thumbnail_16x9_path: str
    thumbnail_9x16_path: str = ""
    ass_subtitles_16x9_path: str
    ass_subtitles_9x16_path: str
    bgm_stem_path: str
    final_duration_sec: float
    shorts_duration_sec: float
    short_hook_script: str = ""
    scene_count_rendered: int
    exact_chapters_text: str
    generation_mode: str = "hybrid_ai_and_procedural"
    scene_artifacts: List[RenderedSceneArtifact] = Field(default_factory=list)


# ==============================================================================
# AGENT 4: DIRECT YOUTUBE PUBLISHER OUTPUT
# ==============================================================================
class Agent4Output(BaseModel):
    model_config = ConfigDict(extra="ignore")

    record_id: str
    video_id: str = ""
    watch_url: str = ""
    studio_url: str = ""
    title: str
    privacy_status: str
    scheduled_publish_at: Optional[str] = None
    playlist_id: Optional[str] = None
    thumbnail_attached: bool = False
    is_short: bool = False
    linked_long_video_url: Optional[str] = None
    status: str = "Published"
    note: str = ""
