"""
Module D: `omni_creator/thumbnail_hook_studio.py`
=================================================
A/B High-CTR 4K Thumbnail Suite for Classes 9-12 Science (`gemini-3-pro-image`).

Generates 3 distinct 16:9 4K thumbnail variants (`variant_1.png`, `variant_2.png`, `variant_3.png`):
- Variant 1 (The Visual Paradox): Extreme close-up 3D phenomenon looking impossible + <4 word hook.
- Variant 2 (The Exam Urgency): Split-screen 3D comparison ("Wrong vs Topper Method") + "99% FAIL HERE!".
- Variant 3 (The Curiosity Zoom): 10,000x microscopic 3D cutaway with glowing neon arrows + <4 words of text.
All thumbnails enforce high-contrast mobile readability and strictly non-kiddish Unreal Engine 5 / Octane 3D styling.
"""

from __future__ import annotations

import base64
import logging
import math
from pathlib import Path
from typing import Dict, List, Optional

from PIL import Image, ImageDraw, ImageFont

from config.models import (
    GLOBAL_3D_SCIENCE_STYLE_PROMPT,
    GLOBAL_NEGATIVE_CONSTRAINTS,
    IMAGE_4K_PRO_MODEL,
    IMAGE_CONTINUITY_MODEL,
    OmniModelConfig,
    call_interaction_with_backoff,
    compute_content_sha256,
    get_genai_client,
)
from schemas.blueprint import ChapterVideoBlueprint, ThumbnailVariantSpec

logger = logging.getLogger("omni_creator.thumbnail_hook_studio")


def _load_thumb_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for candidate in [
        "C:/Windows/Fonts/impact.ttf",
        "C:/Windows/Fonts/segoeuib.ttf",
        "C:/Windows/Fonts/arialbd.ttf",
    ]:
        if Path(candidate).exists():
            try:
                return ImageFont.truetype(candidate, size=size)
            except Exception:
                pass
    return ImageFont.load_default()


def _render_3d_thumbnail_canvas(
    spec: ThumbnailVariantSpec,
    blueprint: ChapterVideoBlueprint,
    output_path: Path,
    base_ai_image_bytes: Optional[bytes] = None,
) -> Path:
    """
    Renders or overlays a 3840x2160 (4K 16:9) High-CTR Science Thumbnail for Variant 1, 2, or 3
    with razor-sharp `< 4` word hook typography, mobile-first contrast, and non-kiddish 3D visuals.
    """
    w, h = 3840, 2160  # True 4K 16:9 resolution
    if base_ai_image_bytes:
        try:
            import io
            bg = Image.open(io.BytesIO(base_ai_image_bytes)).convert("RGBA").resize((w, h), Image.Resampling.LANCZOS)
        except Exception:
            bg = Image.new("RGBA", (w, h), (6, 9, 16, 255))
    else:
        bg = Image.new("RGBA", (w, h), (6, 9, 16, 255))

    draw = ImageDraw.Draw(bg, "RGBA")
    short_ch = blueprint.input_spec.chapter_name.split("—")[0].split("-")[0].strip()
    formula_expr = blueprint.beat_3_hud_formula_vault.exact_formula_expression.split("|")[0].strip()

    if not base_ai_image_bytes:
        # Procedural Unreal 5 / Octane Dark-Obsidian 4K 3D Artwork per Variant Archetype
        cx, cy = int(w * 0.74), int(h * 0.52)
        for r in range(int(w * 0.65), 80, -60):
            t = 1.0 - (r / float(w * 0.65))
            if spec.variant_id == "variant_1":
                col = (int(8 + 38 * t), int(16 + 75 * t), int(38 + 145 * t), 255)
            elif spec.variant_id == "variant_2":
                col = (int(18 + 65 * t), int(10 + 30 * t), int(24 + 70 * t), 255)
            else:
                col = (int(6 + 24 * t), int(24 + 95 * t), int(34 + 115 * t), 255)
            draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=col)

        # 3D Titanium Grid Perspective
        for gx in range(-10, 11):
            draw.line(
                [(cx + gx * 160, int(h * 0.62)), (cx + gx * 480, h)],
                fill=(0, 225, 255, 45),
                width=4,
            )

        if spec.variant_id == "variant_1":
            # Variant 1: The Visual Paradox — Impossible 3D Laser & Optical/Subatomic Deflection
            p1, p2, p3 = (cx, int(h * 0.16)), (cx - 500, int(h * 0.82)), (cx + 500, int(h * 0.82))
            draw.line([(int(w * 0.48), int(h * 0.60)), (cx - 190, int(h * 0.46))], fill=(0, 240, 255, 255), width=26)
            draw.line([(cx - 190, int(h * 0.46)), (cx + 210, int(h * 0.50))], fill=(255, 230, 60, 255), width=22)
            for idx, c_rgb in enumerate([(255, 50, 80), (255, 165, 30), (50, 255, 150), (0, 200, 255), (185, 90, 255)]):
                draw.line(
                    [(cx + 210, int(h * 0.50)), (w - 60, int(h * 0.36 + idx * 145))],
                    fill=(*c_rgb, 240),
                    width=18,
                )
            draw.polygon([p1, p2, p3], fill=(150, 230, 255, 42), outline=(190, 245, 255, 245))
            draw.line([p1, p2, p3, p1], fill=(255, 255, 255, 255), width=10)

        elif spec.variant_id == "variant_2":
            # Variant 2: The Exam Urgency — Split-Screen 3D "WRONG vs TOPPER METHOD"
            panel_x = int(w * 0.53)
            mid_x = int(w * 0.75)
            # Left Sub-panel: WRONG (Crimson HUD)
            draw.rounded_rectangle(
                [panel_x, 220, mid_x - 24, h - 220],
                radius=36,
                fill=(45, 12, 20, 220),
                outline=(255, 65, 85, 255),
                width=8,
            )
            # Right Sub-panel: TOPPER METHOD (Emerald/Cyan 3D HUD)
            draw.rounded_rectangle(
                [mid_x + 24, 220, w - 90, h - 220],
                radius=36,
                fill=(10, 38, 34, 225),
                outline=(0, 255, 170, 255),
                width=8,
            )
            f_sub = _load_thumb_font(68)
            f_eq = _load_thumb_font(56)
            draw.text((panel_x + 55, 280), "X  WRONG SIGN", fill=(255, 90, 105, 255), font=f_sub)
            draw.text((panel_x + 55, 430), "u = +20 cm (Trap!)", fill=(255, 210, 215, 255), font=f_eq)
            draw.line([(panel_x + 85, 720), (mid_x - 85, 1420)], fill=(255, 60, 80, 230), width=18)
            draw.line([(mid_x - 85, 720), (panel_x + 85, 1420)], fill=(255, 60, 80, 230), width=18)

            draw.text((mid_x + 70, 280), "TOPPER 3D RULE", fill=(50, 255, 175, 255), font=f_sub)
            draw.text((mid_x + 70, 430), formula_expr[:22], fill=(255, 240, 120, 255), font=f_eq)
            # 3D Vector diagram inside Topper panel
            tcx, tcy = int((mid_x + 24 + w - 90) / 2), 1120
            draw.ellipse([tcx - 240, tcy - 240, tcx + 240, tcy + 240], outline=(0, 245, 200, 230), width=10)
            draw.line([(tcx - 290, tcy), (tcx + 290, tcy)], fill=(0, 240, 255, 255), width=10)
            draw.line([(tcx, tcy - 290), (tcx, tcy + 290)], fill=(255, 215, 50, 255), width=10)

        else:
            # Variant 3: The Curiosity Zoom — 10,000x Microscopic 3D Cutaway with Neon Arrows
            for ring_r, col_rgba in [(580, (0, 235, 255, 220)), (410, (255, 195, 40, 235)), (240, (170, 110, 255, 245))]:
                draw.ellipse([cx - ring_r, cy - ring_r, cx + ring_r, cy + ring_r], outline=col_rgba, width=12)
            for k in range(12):
                ang = k * (math.pi / 6.0)
                x1 = int(cx + math.cos(ang) * 220)
                y1 = int(cy + math.sin(ang) * 220)
                x2 = int(cx + math.cos(ang) * 550)
                y2 = int(cy + math.sin(ang) * 550)
                draw.line([(x1, y1), (x2, y2)], fill=(0, 245, 255, 185), width=8)
                draw.ellipse([x2 - 24, y2 - 24, x2 + 24, y2 + 24], fill=(255, 210, 45, 255))
            draw.ellipse([cx - 105, cy - 105, cx + 105, cy + 105], fill=(255, 95, 40, 255), outline=(255, 255, 255, 255), width=10)

    # Left-side high-contrast dark gradient scrim for mobile readability (fades cleanly by 0.50w)
    scrim_end = int(w * 0.50)
    for x in range(scrim_end):
        alpha = 242 if x < int(w * 0.38) else int(242 * (1.0 - (x - int(w * 0.38)) / float(scrim_end - int(w * 0.38))))
        draw.line([(x, 0), (x, h)], fill=(5, 8, 15, alpha), width=1)

    # Top Class + Subject Pill (Consistent Yellow/Red/Cyan High-Contrast Brand Header)
    f_pill = _load_thumb_font(76)
    f_hook = _load_thumb_font(220)
    f_chap = _load_thumb_font(96)
    f_form = _load_thumb_font(72)

    pill_text = f"{blueprint.input_spec.class_level.upper()} • {blueprint.input_spec.subject.upper()} • {spec.sub_badge_text.upper()}"
    draw.rounded_rectangle(
        [120, 120, 1980, 265],
        radius=28,
        fill=(220, 28, 48, 250),
        outline=(255, 220, 60, 255),
        width=8,
    )
    draw.text((165, 145), pill_text[:38], fill=(255, 255, 255, 255), font=f_pill)

    # Primary < 4 Word Hook Text (Massive Yellow/White Impact Typography)
    hook_words = spec.hook_text_max_3_words.upper().split()
    line_1 = hook_words[0] if hook_words else "3D SECRET!"
    line_2 = " ".join(hook_words[1:3]) if len(hook_words) > 1 else short_ch.upper()[:12]

    # Drop shadow + crisp yellow/white fill
    draw.text((132, 352), line_1, fill=(0, 0, 0, 240), font=f_hook)
    draw.text((120, 340), line_1, fill=(255, 230, 35, 255), font=f_hook)

    draw.text((132, 612), line_2, fill=(0, 0, 0, 240), font=f_hook)
    draw.text((120, 600), line_2, fill=(255, 255, 255, 255), font=f_hook)

    # Chapter Focus Keyword Banner
    draw.rounded_rectangle(
        [120, 920, 1860, 1110],
        radius=24,
        fill=(12, 22, 42, 235),
        outline=(0, 230, 255, 240),
        width=6,
    )
    draw.text(
        (165, 955),
        blueprint.keyword_strategy.primary_focus_keyword.upper()[:32],
        fill=(0, 240, 255, 255),
        font=f_chap,
    )

    # Bottom HUD Formula Preview Strip
    draw.rounded_rectangle(
        [120, h - 320, 1920, h - 130],
        radius=24,
        fill=(18, 24, 38, 240),
        outline=(255, 195, 45, 245),
        width=6,
    )
    draw.text(
        (165, h - 272),
        f"FORMULA VAULT:  {formula_expr[:36]}",
        fill=(255, 220, 75, 255),
        font=f_form,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    bg.convert("RGB").save(output_path, format="PNG", optimize=True)
    return output_path


def generate_ab_thumbnail_suite(
    blueprint: ChapterVideoBlueprint,
    *,
    output_thumbnails_dir: Path,
    config: Optional[OmniModelConfig] = None,
    dry_run: bool = False,
) -> Dict[str, Path]:
    """
    Executes Module D (`thumbnail_hook_studio.py`):
    Generates `variant_1.png`, `variant_2.png`, and `variant_3.png` in 4K 16:9 using `gemini-3-pro-image`
    (with SHA-256 content-hash caching) and high-contrast mobile-first HUD typography.
    """
    cfg = config or OmniModelConfig()
    output_thumbnails_dir.mkdir(parents=True, exist_ok=True)
    thumb_cache_dir = cfg.cache_dir / "thumbnails"
    thumb_cache_dir.mkdir(parents=True, exist_ok=True)

    generated_paths: Dict[str, Path] = {}

    for spec in blueprint.thumbnail_variants:
        cache_hash = compute_content_sha256(
            "thumb_4k_v1",
            spec.variant_id,
            spec.hook_text_max_3_words,
            spec.visual_3d_prompt,
            blueprint.keyword_strategy.primary_focus_keyword,
        )
        cached_png = thumb_cache_dir / f"{spec.variant_id}_{cache_hash[:16]}.png"
        target_png = output_thumbnails_dir / f"{spec.variant_id}.png"

        if cached_png.exists() and cached_png.stat().st_size > 4096:
            target_png.write_bytes(cached_png.read_bytes())
            generated_paths[spec.variant_id] = target_png
            continue

        ai_bytes: Optional[bytes] = None
        if not dry_run and cfg.api_key and cfg.api_key != "your_gemini_paid_tier1_api_key_here":
            try:
                client = get_genai_client(cfg.api_key)
                interaction = call_interaction_with_backoff(
                    client,
                    model=IMAGE_4K_PRO_MODEL,
                    fallback_model=IMAGE_CONTINUITY_MODEL,
                    input=(
                        f"{spec.visual_3d_prompt}\n"
                        f"Render razor-sharp text '{spec.hook_text_max_3_words}' in high-contrast typography.\n"
                        f"{GLOBAL_3D_SCIENCE_STYLE_PROMPT}\n{GLOBAL_NEGATIVE_CONSTRAINTS}"
                    ),
                    response_format={
                        "type": "image",
                        "aspect_ratio": "16:9",
                        "image_size": "4k",
                    },
                )
                out_img = getattr(interaction, "output_image", None)
                if out_img and getattr(out_img, "data", None):
                    ai_bytes = (
                        base64.b64decode(out_img.data)
                        if isinstance(out_img.data, str)
                        else bytes(out_img.data)
                    )
            except Exception as exc:
                logger.info("Thumbnail %s API call fell back to 4K 3D HUD studio renderer: %s", spec.variant_id, exc)

        _render_3d_thumbnail_canvas(spec, blueprint, cached_png, base_ai_image_bytes=ai_bytes)
        target_png.write_bytes(cached_png.read_bytes())
        generated_paths[spec.variant_id] = target_png

    return generated_paths
