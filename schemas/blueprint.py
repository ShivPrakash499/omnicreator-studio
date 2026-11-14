"""
OMNI CREATOR — Strict Pydantic v2 Schemas (`schemas/blueprint.py`)
==================================================================
Defines the validated data contracts for:
1. `OmniCreatorInput`: User/CLI/UI input specification (Classes 9-12, Physics/Chemistry/Biology).
2. `KeywordStrategy`: Google Keyword Planner + YouTube India Autocomplete SEO intelligence.
3. `ChapterVideoBlueprint`: 5-Beat High-Retention Hinglish Pedagogical & 3D Production Blueprint.
4. `ThumbnailVariantSpec` & `ThumbnailSuite`: 3 A/B High-CTR 4K Thumbnail specifications.
5. `YouTubeSEOPackage`: Ready-to-publish Title, Description, Timestamps, Tags & Pinned Quiz.
"""

from __future__ import annotations

from typing import Dict, List, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


ClassLevelLiteral = Literal["Class 9", "Class 10", "Class 11", "Class 12"]
SubjectLiteral = Literal["Physics", "Chemistry", "Biology"]
VideoFormatLiteral = Literal["16:9_LongForm", "9:16_Shorts"]
ThumbnailArchetypeLiteral = Literal[
    "Variant_1_Visual_Paradox",
    "Variant_2_Exam_Urgency",
    "Variant_3_Curiosity_Zoom",
]


class OmniCreatorInput(BaseModel):
    """Validated input contract for Omni Creator runs."""
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    class_level: ClassLevelLiteral = Field(
        ...,
        description="Target CBSE/NCERT class level (Class 9, Class 10, Class 11, or Class 12).",
    )
    subject: SubjectLiteral = Field(
        ...,
        description="Core science subject (Physics, Chemistry, or Biology).",
    )
    chapter_name: str = Field(
        ...,
        min_length=2,
        description="NCERT / CBSE 2026-27 rationalized syllabus chapter name.",
    )
    chapter_section: str = Field(
        default="Full Chapter Modular",
        min_length=2,
        description="Specific sub-topic or 'Full Chapter Modular'.",
    )
    video_format: VideoFormatLiteral = Field(
        default="16:9_LongForm",
        description="Output aspect ratio and pacing format: '16:9_LongForm' or '9:16_Shorts'.",
    )

    @property
    def aspect_ratio(self) -> str:
        return "16:9" if self.video_format == "16:9_LongForm" else "9:16"

    @property
    def includes_jee_neet_depth(self) -> bool:
        return self.class_level in ("Class 11", "Class 12")


# ==============================================================================
# MODULE A SCHEMAS: SEO & KEYWORD INTELLIGENCE (`seo_keyword_engine.py`)
# ==============================================================================
class KeywordCandidate(BaseModel):
    """Single scored keyword candidate from Google Keyword Planner / YouTube India."""
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    keyword: str = Field(..., min_length=2)
    monthly_search_volume_india: int = Field(..., ge=0, description="Estimated monthly searches in India (geo 2356).")
    exam_intent_score: float = Field(..., ge=0.0, le=10.0, description="0-10 score for CBSE/JEE/NEET student intent.")
    visual_competition_index: float = Field(
        ...,
        ge=0.0,
        le=100.0,
        description="0-100 competition index (lower means higher 3D visual gap opportunity).",
    )
    composite_opportunity_score: float = Field(
        ...,
        ge=0.0,
        le=100.0,
        description="Weighted score combining High Search Volume + High Exam Intent + Low/Med Visual Competition.",
    )
    source: str = Field(
        default="GoogleAds+YTAutocomplete",
        description="Data source used to derive this keyword metric.",
    )


class KeywordStrategy(BaseModel):
    """
    Output of Module A (`seo_keyword_engine.py`).
    Enforces strict front-loading and <= 500-char tag block constraints.
    """
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    primary_focus_keyword: str = Field(
        ...,
        min_length=3,
        max_length=45,
        description=(
            "Top-scoring keyword. MUST appear in first 45 chars of Title, "
            "first sentence of spoken Hook, Thumbnail text concept, and first 120 chars of Description."
        ),
    )
    secondary_lsi_keywords: List[str] = Field(
        ...,
        min_length=5,
        max_length=8,
        description="5 to 8 high-intent LSI phrases for chapter timestamps and spoken Hinglish script.",
    )
    tags_500_chars: str = Field(
        ...,
        min_length=20,
        max_length=500,
        description="Exact comma-separated YouTube tag block strictly <= 500 characters.",
    )
    geo_target: str = Field(default="India (2356) • English + Hindi")
    data_source_mode: str = Field(
        default="Hybrid_YTAutocomplete_Trends_GeminiSearch",
        description="Indicates whether Google Ads API Developer Token or Clean Hybrid Fallback was used.",
    )
    top_candidates: List[KeywordCandidate] = Field(
        default_factory=list,
        description="Scored seed candidates analyzed to select the primary and LSI keywords.",
    )

    @field_validator("tags_500_chars")
    @classmethod
    def validate_tags_length(cls, value: str) -> str:
        cleaned = value.strip().rstrip(",")
        if len(cleaned) <= 500:
            return cleaned
        parts = [p.strip() for p in cleaned.split(",") if p.strip()]
        acc: List[str] = []
        current_len = 0
        for part in parts:
            add_len = len(part) + (2 if acc else 0)
            if current_len + add_len <= 500:
                acc.append(part)
                current_len += add_len
            else:
                break
        return ", ".join(acc)


# ==============================================================================
# MODULE B SCHEMAS: 5-BEAT HINGLISH PEDAGOGICAL BLUEPRINT (`script_and_pedagogy_agent.py`)
# ==============================================================================
class HookBeat(BaseModel):
    """Beat 1 (0:00-0:03): The 3-Second Pattern-Interrupt Hook."""
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    start_sec: float = Field(default=0.0, ge=0.0)
    end_sec: float = Field(default=3.0, ge=2.5, le=4.0)
    visual_macro_3d_prompt: str = Field(
        ...,
        min_length=20,
        description="Extreme macro 3D action mid-chaos (Unreal Engine 5 / Octane Render, non-kiddish).",
    )
    spoken_hinglish_hook: str = Field(
        ...,
        min_length=15,
        description=(
            "Immediate curiosity shock or exam fear-of-loss in Hinglish containing primary_focus_keyword. "
            "ZERO 'Hello friends, welcome back to my channel'."
        ),
    )
    on_screen_hud_callout: str = Field(
        ...,
        min_length=3,
        max_length=42,
        description="Punchy 3-second glassmorphic HUD headline banner.",
    )
    sfx_cue: str = Field(
        default="Sub-bass impact + metallic laser riser whoosh",
        description="Crisp audio transition cue at 0:00 and 0:03.",
    )

    @field_validator("spoken_hinglish_hook")
    @classmethod
    def ban_generic_intro(cls, value: str) -> str:
        lowered = value.lower()
        banned_openers = ["hello friends", "welcome back to my channel", "namaskar dosto", "hi guys welcome"]
        for phrase in banned_openers:
            if phrase in lowered:
                raise ValueError(f"HookBeat violates pattern-interrupt rule: contains banned phrase '{phrase}'.")
        return value


class SimulationSceneBeat(BaseModel):
    """Beat 2: Core Concept in 3D Visual Mode (5s-12s timed 3D simulation scene)."""
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    scene_id: int = Field(..., ge=1)
    scene_title: str = Field(..., min_length=3)
    duration_sec: float = Field(
        ...,
        ge=5.0,
        le=12.0,
        description="Scene duration between 5.0 and 12.0 seconds for gemini-omni-1.2-flash.",
    )
    indian_everyday_analogy: str = Field(
        ...,
        min_length=10,
        description="Relatable everyday Indian analogy (e.g. Mumbai local rush, cricket Yorker swing, pressure cooker).",
    )
    spoken_hinglish_narration: str = Field(
        ...,
        min_length=25,
        description="Witty, conversational Hinglish narration using 100% standard English NCERT scientific terms.",
    )
    start_keyframe_prompt: str = Field(
        ...,
        min_length=25,
        description="4K photorealistic 3D start keyframe prompt for gemini-3-pro-image / gemini-nano-banana-2.1.",
    )
    end_keyframe_prompt: Optional[str] = Field(
        default=None,
        description="Optional 4K 3D end-state keyframe prompt for first-and-last-frame interpolation.",
    )
    omni_camera_motion_prompt: str = Field(
        ...,
        min_length=25,
        description="Cinematic camera movement & optical physics prompt for gemini-omni-1.2-flash.",
    )
    hud_overlay_label: str = Field(
        ...,
        min_length=3,
        max_length=60,
        description="Dark-glass HUD micro-callout displayed during this 3D simulation scene.",
    )
    continuity_anchor_object: str = Field(
        ...,
        min_length=3,
        description="3D laboratory prop or molecular/optical structure locked across consecutive shots.",
    )


class HUDFormulaVaultBeat(BaseModel):
    """Beat 3: HUD Formula Vault & Memory Hack."""
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    formula_title: str = Field(..., min_length=3)
    exact_formula_expression: str = Field(
        ...,
        min_length=3,
        description="Exact mathematical/chemical/biological formula (e.g., '1/f = 1/v - 1/u' or 'R = rho * (L / A)').",
    )
    si_units_and_variables: str = Field(
        ...,
        min_length=5,
        description="SI units and variable definitions.",
    )
    vector_scalar_sign_conventions: str = Field(
        ...,
        min_length=5,
        description="Vector/scalar nature and CBSE/JEE/NEET sign conventions.",
    )
    sticky_hinglish_mnemonic: str = Field(
        ...,
        min_length=10,
        description="Sticky Hinglish mnemonic or acronym rendered on the sleek dark-glass HUD overlay.",
    )
    spoken_hinglish_explanation: str = Field(
        ...,
        min_length=20,
        description="Charismatic Hinglish delivery with dramatic pause before announcing the formula.",
    )
    duration_sec: float = Field(default=8.0, ge=5.0, le=12.0)


class ExamSniperTipBeat(BaseModel):
    """Beat 4: Exam Sniper Tip (CBSE Boards / JEE / NEET)."""
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    exam_target_badge: str = Field(
        ...,
        min_length=4,
        description="E.g. 'CBSE BOARD 3-MARK TRAP' or 'JEE MAIN / NEET PYQ SNIPER'.",
    )
    number_one_silly_mistake: str = Field(
        ...,
        min_length=15,
        description="The #1 silly mistake 90% of students make in exams on this topic.",
    )
    exact_ncert_step_marking_keywords: List[str] = Field(
        ...,
        min_length=3,
        max_length=6,
        description="Exact English NCERT keywords examiners check for full step-marking.",
    )
    pyq_competency_assertion_reason_angle: str = Field(
        ...,
        min_length=15,
        description="How this concept twists in CBSE Competency-Based or JEE/NEET Assertion-Reason PYQs.",
    )
    spoken_hinglish_sniper_warning: str = Field(
        ...,
        min_length=20,
        description="Urgent mentor callout in Hinglish warning students about the exam trap.",
    )
    duration_sec: float = Field(default=8.0, ge=5.0, le=12.0)


class GamifiedEngagementBeat(BaseModel):
    """Beat 5: Gamified Engagement Trigger (Mid-Roll + Outro)."""
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    mid_roll_micro_check_hinglish: str = Field(
        ...,
        min_length=15,
        description="Quick mid-roll retention check question to keep watch-time graph flat.",
    )
    outro_10s_tricky_pyq_puzzle: str = Field(
        ...,
        min_length=20,
        description=(
            "10-second tricky Board/PYQ conceptual puzzle on screen (e.g., 'Video pause karo! Agar wire ki "
            "length double kheench kar kar di, toh Resistance 2x hoga ya 4x?...')."
        ),
    )
    options_hud: List[str] = Field(
        ...,
        min_length=2,
        max_length=4,
        description="Multiple-choice options displayed on the 3D HUD screen.",
    )
    correct_answer_hint_for_pin: str = Field(
        ...,
        min_length=5,
        description="Hidden solution note for creator to heart & pin top student comments.",
    )
    duration_sec: float = Field(default=10.0, ge=8.0, le=12.0)


# ==============================================================================
# MODULE D & E SCHEMAS: THUMBNAIL VARIANTS & YOUTUBE SEO PACKAGE
# ==============================================================================
class ThumbnailVariantSpec(BaseModel):
    """Specification for a single 16:9 4K A/B Thumbnail Variant (< 4 words of text)."""
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    variant_id: Literal["variant_1", "variant_2", "variant_3"]
    archetype: ThumbnailArchetypeLiteral
    hook_text_max_3_words: str = Field(
        ...,
        min_length=2,
        max_length=28,
        description="Strictly < 4 words (1 to 3 words max) high-contrast Hinglish/English hook text.",
    )
    sub_badge_text: str = Field(
        ...,
        min_length=3,
        max_length=24,
        description="Compact class/exam pill (e.g., 'CLASS 10 • 3 MARKS').",
    )
    visual_3d_prompt: str = Field(
        ...,
        min_length=30,
        description="Photorealistic 4K Unreal Engine 5 / Octane Render prompt for gemini-3-pro-image.",
    )

    @field_validator("hook_text_max_3_words")
    @classmethod
    def enforce_under_four_words(cls, value: str) -> str:
        words = [w for w in value.strip().split() if w]
        if len(words) >= 4:
            return " ".join(words[:3])
        return " ".join(words)


class YouTubeSEOPackage(BaseModel):
    """Complete ready-to-publish YouTube SEO metadata bundle."""
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    title_variations: List[str] = Field(
        ...,
        min_length=3,
        max_length=3,
        description="3 high-CTR title variations (< 60 chars) with primary_focus_keyword front-loaded.",
    )
    seo_description: str = Field(
        ...,
        min_length=80,
        description="2-line hook with primary keyword in first 120 chars + Auto-Timestamps + Formula Summary + Hashtags.",
    )
    auto_timestamps: List[str] = Field(
        ...,
        min_length=5,
        description="Formatted YouTube chapter timestamps (starting with 00:00).",
    )
    pinned_comment_quiz: str = Field(
        ...,
        min_length=20,
        description="Ready-to-paste interactive Pinned Comment Quiz to drive comment velocity.",
    )
    tags_500_chars: str = Field(..., max_length=500)
    hashtags: List[str] = Field(..., min_length=4, max_length=10)

    @field_validator("title_variations")
    @classmethod
    def enforce_title_length(cls, titles: List[str]) -> List[str]:
        normalized: List[str] = []
        for title in titles:
            t = title.strip()
            if len(t) > 60:
                t = t[:57].rstrip() + "..."
            normalized.append(t)
        return normalized


class ChapterVideoBlueprint(BaseModel):
    """
    Master Pydantic v2 Blueprint connecting Module A (SEO), Module B (5-Beat Script),
    Module C (3D Keyframes & Omni Clips), Module D (3 A/B Thumbnails), and Module E (Compositor).
    """
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    input_spec: OmniCreatorInput
    keyword_strategy: KeywordStrategy
    beat_1_pattern_interrupt_hook: HookBeat
    beat_2_simulation_scenes: List[SimulationSceneBeat] = Field(
        ...,
        min_length=3,
        max_length=8,
        description="Timed 5s-12s 3D simulation scenes breaking down the core concept with Indian analogies.",
    )
    beat_3_hud_formula_vault: HUDFormulaVaultBeat
    beat_4_exam_sniper_tip: ExamSniperTipBeat
    beat_5_gamified_engagement: GamifiedEngagementBeat
    thumbnail_variants: List[ThumbnailVariantSpec] = Field(
        ...,
        min_length=3,
        max_length=3,
        description="3 A/B 16:9 4K Thumbnail specifications (Visual Paradox, Exam Urgency, Curiosity Zoom).",
    )
    youtube_seo_package: YouTubeSEOPackage

    @property
    def total_planned_duration_sec(self) -> float:
        hook_dur = self.beat_1_pattern_interrupt_hook.end_sec - self.beat_1_pattern_interrupt_hook.start_sec
        scenes_dur = sum(s.duration_sec for s in self.beat_2_simulation_scenes)
        return round(
            hook_dur
            + scenes_dur
            + self.beat_3_hud_formula_vault.duration_sec
            + self.beat_4_exam_sniper_tip.duration_sec
            + self.beat_5_gamified_engagement.duration_sec,
            1,
        )

    @model_validator(mode="after")
    def verify_primary_keyword_alignment(self) -> "ChapterVideoBlueprint":
        primary_kw = self.keyword_strategy.primary_focus_keyword.lower()
        # Ensure primary keyword is front-loaded in first 120 chars of description
        if primary_kw not in self.youtube_seo_package.seo_description[:140].lower():
            self.youtube_seo_package.seo_description = (
                f"{self.keyword_strategy.primary_focus_keyword} — "
                f"{self.youtube_seo_package.seo_description}"
            )
        return self
