"""
OMNI STUDIO — High-CTR Likeness-Locked Thumbnail Studio (`render_engine/thumbnail_studio.py`)
=============================================================================================
Generates high-CTR 16:9 YouTube thumbnails strictly preserving the creator likeness of
`@jwalashiva` from on-disk reference photos (`assets/likeness/image_12.png`, `image_13.png`,
`image_14.png`) and visual composition matching `assets/likeness/image_11.png`:

- Features `@jwalashiva` on the left (or right) side wearing proper smart attire (dark Nehru
  jacket / tailored vest over a crisp button-up shirt), dynamically gesture-pointing toward
  bright glowing thematic graphics/diagrams representing the chosen topic & niche.
- Includes oversized bold typography with high-frequency neon highlighting, outer glow,
  backlighting/rim effects, and crisp topic/niche badge labels.
- Uses `gemini-3-pro-image` (fallback: `gemini-nano-banana-2.1`) via `client.interactions.create(...)`
  passing all on-disk likeness images directly as multimodal inputs, with a guaranteed high-CTR
  composited studio fallback using the user's real portrait if offline/rate-limited.
"""

from __future__ import annotations

import base64
import io
import logging
import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

from backend.config import (
    IMAGE_CONTINUITY_MODEL,
    IMAGE_PRO_MODEL,
    OmniStudioConfig,
    call_interaction_with_fallback,
    get_genai_client,
    get_niche_profile,
    get_vertex_adc_credentials,
    resolve_current_model,
)
from google.genai import types as genai_types

logger = logging.getLogger("omni_studio.thumbnail_studio")


def _hex_to_rgb(hex_color: str, fallback: Tuple[int, int, int] = (0, 229, 255)) -> Tuple[int, int, int]:
    h = hex_color.lstrip("#")
    if len(h) == 6:
        try:
            return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))
        except Exception:
            pass
    return fallback


def _load_bold_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for p in [
        "C:/Windows/Fonts/impact.ttf",
        "C:/Windows/Fonts/segoeuib.ttf",
        "C:/Windows/Fonts/arialbd.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ]:
        if Path(p).exists():
            try:
                return ImageFont.truetype(p, size=size)
            except Exception:
                pass
    return ImageFont.load_default()


def _draw_glowing_text(
    base_img: Image.Image,
    pos: Tuple[int, int],
    text: str,
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    fill_rgba: Tuple[int, int, int, int],
    glow_rgb: Tuple[int, int, int],
    glow_radius: int = 12,
) -> Image.Image:
    glow_layer = Image.new("RGBA", base_img.size, (0, 0, 0, 0))
    g_draw = ImageDraw.Draw(glow_layer, "RGBA")
    x, y = pos
    # Thick outer stroke + neon glow
    for ox in (-5, 0, 5):
        for oy in (-5, 0, 5):
            g_draw.text((x + ox, y + oy), text, fill=(*glow_rgb, 210), font=font)
    glow_layer = glow_layer.filter(ImageFilter.GaussianBlur(radius=glow_radius))
    out = Image.alpha_composite(base_img, glow_layer)

    d = ImageDraw.Draw(out, "RGBA")
    # Crisp dark shadow for mobile readability
    for ox, oy in [(6, 6), (-3, -3), (3, -3), (-3, 3)]:
        d.text((x + ox, y + oy), text, fill=(5, 8, 14, 245), font=font)
    d.text((x, y), text, fill=fill_rgba, font=font)
    return out


def _apply_high_ctr_typography_overlay(
    bg_img: Image.Image,
    *,
    headline: str,
    badge_label: str,
    topic: str,
    niche: str,
    creator_side: str = "left",
) -> Image.Image:
    """
    Adds razor-sharp neon-highlighted oversized typography, topic badge label, and subtle
    rim contrast onto the 1920x1080 (or 16:9) thumbnail canvas so text is 100% legible on mobile.
    """
    w, h = 1920, 1080
    canvas = bg_img.convert("RGBA").resize((w, h), Image.Resampling.LANCZOS)
    prof = get_niche_profile(niche)
    acc_rgb = _hex_to_rgb(prof["accent_hex"])
    sec_rgb = _hex_to_rgb(prof["secondary_hex"])

    draw = ImageDraw.Draw(canvas, "RGBA")

    # Place headline and badge on the graphic half opposite the creator with strict right-margin fit
    text_x = int(w * 0.48) if creator_side == "left" else 64
    max_text_w = (w - text_x - 56) if creator_side == "left" else (int(w * 0.50) - 64)
    f_badge = _load_bold_font(38)
    f_sub = _load_bold_font(42)

    # Top topic/niche badge pill (never clipped mid-word)
    niche_short = niche.split("&")[0].strip().upper()
    badge_text = f"{niche_short}  •  {badge_label.upper()}"
    while draw.textbbox((0, 0), badge_text, font=f_badge)[2] > max_text_w - 60 and len(badge_text) > 10:
        badge_text = badge_text[:-1].rstrip()
    b_box = draw.textbbox((0, 0), badge_text, font=f_badge)
    bw = (b_box[2] - b_box[0]) + 54
    draw.rounded_rectangle(
        [text_x, 54, min(w - 44, text_x + bw), 124],
        radius=18,
        fill=(220, 28, 52, 242),
        outline=(*sec_rgb, 255),
        width=4,
    )
    draw.text((text_x + 26, 66), badge_text, fill=(255, 255, 255, 255), font=f_badge)

    # Split headline into 2 balanced punchy lines and auto-fit font size strictly inside max_text_w
    words = [w_tok for w_tok in headline.upper().split() if w_tok][:4]
    if len(words) <= 1:
        line1 = words[0] if words else "HIDDEN TRUTH!"
        line2 = ""
    elif len(words) == 2:
        line1, line2 = words[0], words[1]
    else:
        mid = len(words) // 2
        line1 = " ".join(words[:mid])
        line2 = " ".join(words[mid:])

    def _fit_font(text_line: str, start_sz: int = 126, min_sz: int = 62) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
        sz = start_sz
        while sz > min_sz:
            fnt = _load_bold_font(sz)
            tw = draw.textbbox((0, 0), text_line, font=fnt)[2]
            if tw <= max_text_w:
                return fnt
            sz -= 6
        return _load_bold_font(min_sz)

    f_line1 = _fit_font(line1, 130)
    canvas = _draw_glowing_text(
        canvas,
        (text_x, 148),
        line1,
        f_line1,
        fill_rgba=(255, 236, 40, 255),
        glow_rgb=sec_rgb,
        glow_radius=14,
    )
    if line2:
        f_line2 = _fit_font(line2, 122)
        l1_h = draw.textbbox((0, 0), line1, font=f_line1)[3]
        canvas = _draw_glowing_text(
            canvas,
            (text_x, 166 + l1_h),
            line2,
            f_line2,
            fill_rgba=(255, 255, 255, 255),
            glow_rgb=acc_rgb,
            glow_radius=14,
        )

    # Bottom glowing topic strap (auto-fitted cleanly)
    draw2 = ImageDraw.Draw(canvas, "RGBA")
    strap_y = h - 124
    strap_right = w - 48 if creator_side == "left" else int(w * 0.52)
    draw2.rounded_rectangle(
        [text_x, strap_y, strap_right, h - 42],
        radius=16,
        fill=(8, 14, 28, 225),
        outline=(*acc_rgb, 240),
        width=3,
    )
    strap_txt = topic.upper()
    f_strap = _fit_font(strap_txt, 42, 24)
    draw2.text((text_x + 22, strap_y + 18), strap_txt, fill=(*acc_rgb, 255), font=f_strap)
    return canvas


def _build_local_likeness_fallback_thumbnail(
    *,
    topic: str,
    niche: str,
    headline: str,
    badge_label: str,
    likeness_paths: List[Path],
    style_sample_path: Optional[Path],
    creator_side: str = "left",
) -> Image.Image:
    """
    High-CTR composited fallback preserving @jwalashiva's actual portrait from `image_13.png`/`image_11.png`
    with dramatic rim backlighting, glowing thematic graphic nodes, and neon-highlighted typography.
    """
    w, h = 1920, 1080
    prof = get_niche_profile(niche)
    acc_rgb = _hex_to_rgb(prof["accent_hex"])
    sec_rgb = _hex_to_rgb(prof["secondary_hex"])

    canvas = Image.new("RGBA", (w, h), (7, 12, 22, 255))
    draw = ImageDraw.Draw(canvas, "RGBA")

    # Cinematic studio backlight glow
    gx = int(w * (0.28 if creator_side == "left" else 0.72))
    gy = int(h * 0.45)
    for r in range(880, 60, -40):
        t = 1.0 - (r / 880.0)
        draw.ellipse(
            [gx - r, gy - r, gx + r, gy + r],
            fill=(int(8 + acc_rgb[0] * 0.35 * t), int(14 + acc_rgb[1] * 0.35 * t), int(26 + acc_rgb[2] * 0.42 * t), 255),
        )

    # Secondary graphic glow on opposite half
    ox = int(w * (0.74 if creator_side == "left" else 0.26))
    oy = int(h * 0.65)
    for r in range(460, 40, -30):
        t = 1.0 - (r / 460.0)
        draw.ellipse(
            [ox - r, oy - r, ox + r, oy + r],
            fill=(int(sec_rgb[0] * 0.45 * t), int(sec_rgb[1] * 0.35 * t), int(sec_rgb[2] * 0.25 * t), 90),
        )

    # Composite creator likeness (`image_13.png` studio portrait preferred, then `image_12.png`/`image_14.png`)
    portrait_path: Optional[Path] = None
    for cand in likeness_paths:
        if cand.name == "image_13.png" and cand.exists():
            portrait_path = cand
            break
    if portrait_path is None and likeness_paths:
        portrait_path = likeness_paths[0]

    if portrait_path and portrait_path.exists():
        p_img = Image.open(portrait_path).convert("RGBA")
        target_h = int(h * 0.96)
        target_w = int(p_img.width * (target_h / float(p_img.height)))
        p_img = p_img.resize((target_w, target_h), Image.Resampling.LANCZOS)
        p_img = ImageEnhance.Contrast(p_img).enhance(1.12)
        p_img = ImageEnhance.Sharpness(p_img).enhance(1.18)

        # Soft feather mask on the right edge so creator blends cleanly into studio lighting
        mask = Image.new("L", p_img.size, 255)
        m_draw = ImageDraw.Draw(mask)
        fade_w = int(target_w * 0.28)
        for dx in range(fade_w):
            alpha_val = int(255 * (1.0 - (dx / float(fade_w)) ** 1.3))
            if creator_side == "left":
                m_draw.line([(target_w - fade_w + dx, 0), (target_w - fade_w + dx, target_h)], fill=alpha_val)
            else:
                m_draw.line([(dx, 0), (dx, target_h)], fill=int(255 * (dx / float(fade_w))))

        px = 0 if creator_side == "left" else (w - target_w)
        canvas.paste(p_img, (px, h - target_h), mask)

    # Glowing thematic infographic HUD on opposite half
    draw = ImageDraw.Draw(canvas, "RGBA")
    cx_g, cy_g = ox, int(h * 0.68)
    for ring_r, col in [(220, acc_rgb), (150, sec_rgb), (85, (255, 255, 255))]:
        draw.ellipse([cx_g - ring_r, cy_g - ring_r, cx_g + ring_r, cy_g + ring_r], outline=(*col, 220), width=6)
    for k in range(8):
        ang = k * (math.pi / 4.0)
        x1, y1 = int(cx_g + math.cos(ang) * 85), int(cy_g + math.sin(ang) * 85)
        x2, y2 = int(cx_g + math.cos(ang) * 240), int(cy_g + math.sin(ang) * 240)
        draw.line([(x1, y1), (x2, y2)], fill=(*acc_rgb, 180), width=4)
        draw.ellipse([x2 - 12, y2 - 12, x2 + 12, y2 + 12], fill=(*sec_rgb, 255))

    return _apply_high_ctr_typography_overlay(
        canvas,
        headline=headline,
        badge_label=badge_label,
        topic=topic,
        niche=niche,
        creator_side=creator_side,
    )


def generate_high_ctr_thumbnail(
    output_png_path: Path,
    *,
    topic: str,
    niche: str,
    headline: str,
    badge_label: str,
    graphic_concept: str,
    creator_side: str = "left",
    config: Optional[OmniStudioConfig] = None,
    use_ai_image_api: bool = True,
) -> Tuple[Path, str]:
    """
    Generates a High-CTR 16:9 thumbnail preserving @jwalashiva's likeness (`image_12..14.png`),
    styled after validation sample `image_11.png`.
    Returns `(output_png_path, engine_used)`.
    """
    cfg = config or OmniStudioConfig()
    prof = get_niche_profile(niche)
    likeness_paths = cfg.likeness_reference_paths
    style_sample = cfg.thumbnail_style_sample_path
    output_png_path.parent.mkdir(parents=True, exist_ok=True)

    if use_ai_image_api and cfg.has_valid_gemini_key:
        try:
            client = get_genai_client(cfg.gemini_api_key)
            input_parts: List[Dict[str, Any]] = []

            for p in likeness_paths:
                b64 = base64.b64encode(p.read_bytes()).decode("utf-8")
                input_parts.append({"type": "image", "data": b64, "mime_type": "image/png"})
            if style_sample and style_sample.exists():
                b64_s = base64.b64encode(style_sample.read_bytes()).decode("utf-8")
                input_parts.append({"type": "image", "data": b64_s, "mime_type": "image/png"})

            side_word = "left half" if creator_side == "left" else "right half"
            other_side = "right half" if creator_side == "left" else "left half"
            prompt = (
                f"Create an ultra-high-CTR 16:9 YouTube thumbnail featuring the exact Indian male creator "
                f"({cfg.creator_handle}) shown in the first {len(likeness_paths)} reference photos — strictly "
                f"preserving his exact face, rectangular glasses, beard, moustache, skin tone, and hairstyle. "
                f"Position him dynamically on the {side_word} wearing sharp smart formal attire (a tailored "
                f"dark charcoal Nehru jacket/vest over a crisp button-up shirt), looking intensely at the camera "
                f"with an energetic expression while gesture-pointing dynamically toward the {other_side}. "
                f"On the {other_side}, render bright, glowing thematic 3D conceptual graphics and diagrams "
                f"representing '{topic}' ({niche}): {graphic_concept}. "
                f"Visual style: {prof['visual_style']}. Dramatic rim lighting, backlighting glow behind the creator "
                f"matching the studio composition of the final reference thumbnail sample. "
                f"Leave clean high-contrast space on the upper {other_side} for bold typography (no garbled text). "
                f"Photorealistic 4K commercial YouTube thumbnail."
            )
            input_parts.append({"type": "text", "text": prompt})

            img_models = [
                resolve_current_model(IMAGE_PRO_MODEL, "gemini-3-pro-image"),
                resolve_current_model(IMAGE_CONTINUITY_MODEL, "gemini-nano-banana-2.1"),
            ]

            v_creds, v_proj = get_vertex_adc_credentials()
            if v_creds is not None and v_proj:
                # Vertex AI ADC native multimodal image generation (`gemini-3-pro-image` / `gemini-nano-banana-2.1`)
                contents_parts: List[Any] = []
                for p in likeness_paths:
                    contents_parts.append(genai_types.Part.from_bytes(data=p.read_bytes(), mime_type="image/png"))
                if style_sample and style_sample.exists():
                    contents_parts.append(genai_types.Part.from_bytes(data=style_sample.read_bytes(), mime_type="image/png"))
                contents_parts.append(prompt)

                for m_img in img_models:
                    try:
                        resp = client.models.generate_content(
                            model=m_img,
                            contents=contents_parts,
                            config=genai_types.GenerateContentConfig(
                                response_modalities=["IMAGE"],
                                image_config=genai_types.ImageConfig(aspect_ratio="16:9"),
                            ),
                        )
                        raw_bytes: Optional[bytes] = None
                        for cand in getattr(resp, "candidates", []) or []:
                            for part in getattr(getattr(cand, "content", None), "parts", []) or []:
                                if getattr(part, "inline_data", None) and part.inline_data.data:
                                    raw_bytes = bytes(part.inline_data.data)
                                    break
                            if raw_bytes:
                                break
                        if raw_bytes:
                            ai_pil = Image.open(io.BytesIO(raw_bytes)).convert("RGBA")
                            final_pil = _apply_high_ctr_typography_overlay(
                                ai_pil,
                                headline=headline,
                                badge_label=badge_label,
                                topic=topic,
                                niche=niche,
                                creator_side=creator_side,
                            )
                            final_pil.convert("RGB").save(output_png_path, format="PNG", optimize=True)
                            return output_png_path, f"vertex_likeness_pro({m_img})"
                    except Exception as v_err:
                        logger.info("Vertex image model %s skipped: %s", m_img, v_err)
            else:
                interaction = call_interaction_with_fallback(
                    client,
                    models=img_models,
                    max_retries=2,
                    input=input_parts,
                    response_format={
                        "type": "image",
                        "aspect_ratio": "16:9",
                        "image_size": "2K",
                    },
                )
                out_img = getattr(interaction, "output_image", None)
                if out_img and getattr(out_img, "data", None):
                    raw = base64.b64decode(out_img.data) if isinstance(out_img.data, str) else bytes(out_img.data)
                    ai_pil = Image.open(io.BytesIO(raw)).convert("RGBA")
                    final_pil = _apply_high_ctr_typography_overlay(
                        ai_pil,
                        headline=headline,
                        badge_label=badge_label,
                        topic=topic,
                        niche=niche,
                        creator_side=creator_side,
                    )
                    final_pil.convert("RGB").save(output_png_path, format="PNG", optimize=True)
                    return output_png_path, f"gemini_likeness_pro({img_models[0]})"
        except Exception as exc:
            logger.info("Gemini likeness thumbnail fell back to composited @jwalashiva studio renderer: %s", exc)

    fallback_pil = _build_local_likeness_fallback_thumbnail(
        topic=topic,
        niche=niche,
        headline=headline,
        badge_label=badge_label,
        likeness_paths=likeness_paths,
        style_sample_path=style_sample,
        creator_side=creator_side,
    )
    fallback_pil.convert("RGB").save(output_png_path, format="PNG", optimize=True)
    return output_png_path, "likeness_studio_compositor"
