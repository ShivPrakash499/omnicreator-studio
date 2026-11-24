"""
OMNI STUDIO — High-CTR Thumbnail Studio (`render_engine/thumbnail_studio.py`)
=============================================================================
Supports 3 clean thumbnail modes controlled by explicit user opt-in:
1. **Faceless Cinema Mode (`include_creator_avatar=False`, default):**
   Full-bleed 16:9 dramatic cinematic artwork 100% focused on the video topic with razor-sharp
   high-CTR typography (zero awkward faces, zero AI text leakage).
2. **Real Studio Portrait Cutout (`include_creator_avatar=True, avatar_mode="real_photo"`):**
   Generates a pure cinematic topic backdrop and cleanly composites the user's 100% authentic,
   unaltered studio photo (`image_13.png`) with soft studio rim-light feathering — zero AI face distortion!
3. **AI Studio Portrait (`include_creator_avatar=True, avatar_mode="ai_pro"`):**
   Uses `gemini-3-pro-image` (primary) with ONLY clean studio likeness photos (`image_13.png`,
   `image_14.png`) and flattering warm studio lighting + natural confident expression.

Script & Font Guarantee:
- NEVER embeds trigger words like "space for typography" into image prompts (eliminates literal
  "CLEAN SPACE FOR TYPOGRAPHY" hallucinations!).
- When headline/badge contains **Hindi Devanagari**, `gemini-3-pro-image` renders razor-sharp native
  Hindi poster text directly (zero `□□□` boxes and zero broken Devanagari matras!).
- For English / Hinglish (Latin), uses crisp auto-fitted neon glow PIL typography + bundled
  `assets/fonts/NotoSansDevanagari-Bold.ttf` fallback so `□□□` boxes can NEVER occur.
"""

from __future__ import annotations

import base64
import io
import logging
import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont
from google.genai import types as genai_types

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

logger = logging.getLogger("omni_studio.thumbnail_studio")


def _contains_devanagari(text: str) -> bool:
    return any("\u0900" <= ch <= "\u097f" for ch in (text or ""))


def _hex_to_rgb(hex_color: str, fallback: Tuple[int, int, int] = (0, 229, 255)) -> Tuple[int, int, int]:
    h = hex_color.lstrip("#")
    if len(h) == 6:
        try:
            return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))
        except Exception:
            pass
    return fallback


def _load_bold_font(size: int, text: str = "") -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Selects a genuine Devanagari-capable bold font if text contains Hindi, else crisp Latin bold."""
    if _contains_devanagari(text):
        candidates = [
            "assets/fonts/NotoSansDevanagari-Bold.ttf",
            "C:/Windows/Fonts/NirmalaB.ttf",
            "C:/Windows/Fonts/Nirmala.ttf",
            "/usr/share/fonts/truetype/noto/NotoSansDevanagari-Bold.ttf",
            "/usr/share/fonts/truetype/lohit-devanagari/Lohit-Devanagari.ttf",
            "/usr/share/fonts/truetype/noto/NotoSansDevanagari-Regular.ttf",
        ]
    else:
        candidates = [
            "C:/Windows/Fonts/impact.ttf",
            "C:/Windows/Fonts/segoeuib.ttf",
            "C:/Windows/Fonts/arialbd.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "assets/fonts/NotoSansDevanagari-Bold.ttf",
        ]
    for p in candidates:
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
    for ox in (-5, 0, 5):
        for oy in (-5, 0, 5):
            g_draw.text((x + ox, y + oy), text, fill=(*glow_rgb, 200), font=font)
    glow_layer = glow_layer.filter(ImageFilter.GaussianBlur(radius=glow_radius))
    out = Image.alpha_composite(base_img, glow_layer)

    d = ImageDraw.Draw(out, "RGBA")
    for ox, oy in [(6, 6), (-3, -3), (3, -3), (-3, 3)]:
        d.text((x + ox, y + oy), text, fill=(5, 8, 14, 245), font=font)
    d.text((x, y), text, fill=fill_rgba, font=font)
    return out


def _paste_clean_real_portrait(
    bg_img: Image.Image,
    portrait_path: Path,
    *,
    creator_side: str = "left",
    accent_rgb: Tuple[int, int, int] = (0, 229, 255),
) -> Image.Image:
    """
    Composites the user's 100% authentic studio portrait (`image_13.png`) cleanly onto the
    cinematic backdrop with soft elliptical edge feathering and subtle backlight glow — zero AI face distortion!
    """
    w, h = 1920, 1080
    canvas = bg_img.convert("RGBA").resize((w, h), Image.Resampling.LANCZOS)
    if not portrait_path.exists():
        return canvas

    p_img = Image.open(portrait_path).convert("RGBA")
    target_h = int(h * 0.96)
    target_w = int(p_img.width * (target_h / float(p_img.height)))
    p_img = p_img.resize((target_w, target_h), Image.Resampling.LANCZOS)
    p_img = ImageEnhance.Contrast(p_img).enhance(1.06)
    p_img = ImageEnhance.Sharpness(p_img).enhance(1.10)

    # Smooth feather mask on the inner edge & top so portrait merges seamlessly into studio atmosphere
    mask = Image.new("L", p_img.size, 255)
    m_draw = ImageDraw.Draw(mask)
    fade_w = int(target_w * 0.34)
    for dx in range(fade_w):
        alpha_val = int(255 * (1.0 - (dx / float(fade_w)) ** 1.35))
        if creator_side == "left":
            m_draw.line([(target_w - fade_w + dx, 0), (target_w - fade_w + dx, target_h)], fill=alpha_val)
        else:
            m_draw.line([(dx, 0), (dx, target_h)], fill=int(255 * (dx / float(fade_w)) ** 1.35))
    # Gentle top fade
    fade_h = int(target_h * 0.08)
    for dy in range(fade_h):
        a = int(255 * (dy / float(fade_h)))
        for x in range(target_w):
            cur = mask.getpixel((x, dy))
            mask.putpixel((x, dy), min(cur, a))

    # Subtle rim glow behind portrait
    glow_bg = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow_bg, "RGBA")
    gx = int(target_w * 0.45) if creator_side == "left" else int(w - target_w * 0.45)
    gd.ellipse([gx - 420, 120, gx + 420, h], fill=(*accent_rgb, 65))
    glow_bg = glow_bg.filter(ImageFilter.GaussianBlur(radius=60))
    canvas = Image.alpha_composite(canvas, glow_bg)

    px = 0 if creator_side == "left" else (w - target_w)
    canvas.paste(p_img, (px, h - target_h), mask)
    return canvas


def _apply_high_ctr_typography_overlay(
    bg_img: Image.Image,
    *,
    headline: str,
    badge_label: str,
    topic: str,
    niche: str,
    include_creator_avatar: bool = False,
    creator_side: str = "left",
) -> Image.Image:
    """
    Overlays crisp, auto-fitted neon-highlighted typography, badge pill, and topic strap.
    - When `include_creator_avatar=False` (Faceless Cinema): positions headline cleanly in the
      upper-left cinematic focal band with generous breathing room.
    - When `include_creator_avatar=True`: positions headline strictly opposite the creator half.
    """
    w, h = 1920, 1080
    canvas = bg_img.convert("RGBA").resize((w, h), Image.Resampling.LANCZOS)
    prof = get_niche_profile(niche)
    acc_rgb = _hex_to_rgb(prof["accent_hex"])
    sec_rgb = _hex_to_rgb(prof["secondary_hex"])

    # Soft directional gradient scrim behind typography side for effortless mobile readability
    scrim = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    s_draw = ImageDraw.Draw(scrim, "RGBA")
    if not include_creator_avatar or creator_side == "right":
        # Scrim on left side
        for x in range(int(w * 0.56)):
            a = int(175 * (1.0 - (x / float(w * 0.56)) ** 1.5))
            s_draw.line([(x, 0), (x, h)], fill=(5, 8, 16, a))
        text_x = 68
        max_text_w = int(w * 0.50) - 68
    else:
        # Scrim on upper-right side opposite left-hand creator
        for x in range(int(w * 0.44), w):
            ratio = (x - int(w * 0.44)) / float(w - int(w * 0.44))
            a = int(160 * (ratio ** 0.7))
            s_draw.line([(x, 0), (x, int(h * 0.56))], fill=(5, 8, 16, a))
        text_x = int(w * 0.48)
        max_text_w = w - text_x - 56
    canvas = Image.alpha_composite(canvas, scrim)
    draw = ImageDraw.Draw(canvas, "RGBA")

    # Top topic/niche badge pill
    niche_short = niche.split("&")[0].strip().upper()
    badge_text = f"{niche_short}  •  {badge_label.upper()}" if not _contains_devanagari(badge_label) else badge_label.strip()
    f_badge = _load_bold_font(36, text=badge_text)
    while draw.textbbox((0, 0), badge_text, font=f_badge)[2] > max_text_w - 60 and len(badge_text) > 8:
        badge_text = badge_text[:-1].rstrip()
    b_box = draw.textbbox((0, 0), badge_text, font=f_badge)
    bw = (b_box[2] - b_box[0]) + 54
    bh = (b_box[3] - b_box[1]) + 28
    draw.rounded_rectangle(
        [text_x, 56, min(w - 44, text_x + bw), 56 + max(64, bh)],
        radius=16,
        fill=(220, 28, 52, 242),
        outline=(*sec_rgb, 255),
        width=4,
    )
    draw.text((text_x + 26, 68), badge_text, fill=(255, 255, 255, 255), font=f_badge)

    # Split headline into 2 balanced punchy lines & auto-fit font strictly inside max_text_w
    words = [w_tok for w_tok in headline.strip().split() if w_tok][:5]
    if not _contains_devanagari(headline):
        words = [w_tok.upper() for w_tok in words]
    if len(words) <= 1:
        line1 = words[0] if words else "HIDDEN TRUTH!"
        line2 = ""
    elif len(words) == 2:
        line1, line2 = words[0], words[1]
    else:
        mid = (len(words) + 1) // 2
        line1 = " ".join(words[:mid])
        line2 = " ".join(words[mid:])

    def _fit_font(text_line: str, start_sz: int = 128, min_sz: int = 58) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
        sz = start_sz
        while sz > min_sz:
            fnt = _load_bold_font(sz, text=text_line)
            tw = draw.textbbox((0, 0), text_line, font=fnt)[2]
            if tw <= max_text_w:
                return fnt
            sz -= 6
        return _load_bold_font(min_sz, text=text_line)

    f_line1 = _fit_font(line1, 132)
    y_l1 = 152
    canvas = _draw_glowing_text(
        canvas,
        (text_x, y_l1),
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
            (text_x, y_l1 + l1_h + 24),
            line2,
            f_line2,
            fill_rgba=(255, 255, 255, 255),
            glow_rgb=acc_rgb,
            glow_radius=14,
        )

    # Bottom glowing topic strap
    draw2 = ImageDraw.Draw(canvas, "RGBA")
    strap_y = h - 124
    strap_right = (text_x + max_text_w + 16)
    draw2.rounded_rectangle(
        [text_x, strap_y, min(w - 44, strap_right), h - 42],
        radius=16,
        fill=(8, 14, 28, 225),
        outline=(*acc_rgb, 240),
        width=3,
    )
    strap_txt = topic.strip() if _contains_devanagari(topic) else topic.upper().strip()
    f_strap = _fit_font(strap_txt, 40, 22)
    draw2.text((text_x + 22, strap_y + 18), strap_txt, fill=(*acc_rgb, 255), font=f_strap)
    return canvas


def _get_clean_studio_portraits(cfg: OmniStudioConfig) -> List[Path]:
    """
    Returns ONLY clean studio likeness photos (`image_13.png`, `image_14.png`), intentionally
    excluding the low-res webcam `image_12.png` (which contains baked-in 'Shiv Prakash' text).
    """
    clean: List[Path] = []
    for fname in ("image_13.png", "image_14.png"):
        p = cfg.likeness_dir / fname
        if p.exists():
            clean.append(p)
    if not clean:
        return cfg.likeness_reference_paths
    return clean


def _build_local_fallback_backdrop(
    *,
    niche: str,
    include_creator_avatar: bool,
    creator_side: str,
    portrait_path: Optional[Path],
) -> Image.Image:
    w, h = 1920, 1080
    prof = get_niche_profile(niche)
    acc_rgb = _hex_to_rgb(prof["accent_hex"])
    sec_rgb = _hex_to_rgb(prof["secondary_hex"])

    canvas = Image.new("RGBA", (w, h), (7, 12, 22, 255))
    draw = ImageDraw.Draw(canvas, "RGBA")

    gx = int(w * (0.72 if (not include_creator_avatar or creator_side == "left") else 0.28))
    gy = int(h * 0.54)
    for r in range(720, 50, -40):
        t = 1.0 - (r / 720.0)
        draw.ellipse(
            [gx - r, gy - r, gx + r, gy + r],
            fill=(int(8 + acc_rgb[0] * 0.34 * t), int(14 + acc_rgb[1] * 0.34 * t), int(26 + acc_rgb[2] * 0.42 * t), 255),
        )

    for ring_r, col in [(240, acc_rgb), (165, sec_rgb), (92, (255, 255, 255))]:
        draw.ellipse([gx - ring_r, gy - ring_r, gx + ring_r, gy + ring_r], outline=(*col, 210), width=6)
    for k in range(8):
        ang = k * (math.pi / 4.0)
        x1, y1 = int(gx + math.cos(ang) * 92), int(gy + math.sin(ang) * 92)
        x2, y2 = int(gx + math.cos(ang) * 265), int(gy + math.sin(ang) * 265)
        draw.line([(x1, y1), (x2, y2)], fill=(*acc_rgb, 175), width=4)
        draw.ellipse([x2 - 12, y2 - 12, x2 + 12, y2 + 12], fill=(*sec_rgb, 255))

    if include_creator_avatar and portrait_path and portrait_path.exists():
        canvas = _paste_clean_real_portrait(canvas, portrait_path, creator_side=creator_side, accent_rgb=acc_rgb)
    return canvas


def _call_ai_image_generation(
    *,
    prompt: str,
    reference_paths: List[Path],
    config: OmniStudioConfig,
) -> Tuple[Optional[bytes], str]:
    """Calls `gemini-3-pro-image` (primary) -> `gemini-nano-banana-2.1` on Vertex AI ADC or Developer API."""
    if not config.has_valid_gemini_key:
        return None, ""

    # Always prioritize `gemini-3-pro-image` first for top photographic fidelity & native text accuracy
    img_models = [
        "gemini-3-pro-image",
        resolve_current_model(IMAGE_CONTINUITY_MODEL, "gemini-nano-banana-2.1"),
    ]
    client = get_genai_client(config.gemini_api_key)
    v_creds, v_proj = get_vertex_adc_credentials()

    if v_creds is not None and v_proj:
        contents_parts: List[Any] = [
            genai_types.Part.from_bytes(data=p.read_bytes(), mime_type="image/png")
            for p in reference_paths
            if p.exists()
        ]
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
                for cand in getattr(resp, "candidates", []) or []:
                    for part in getattr(getattr(cand, "content", None), "parts", []) or []:
                        if getattr(part, "inline_data", None) and part.inline_data.data:
                            return bytes(part.inline_data.data), f"vertex({m_img})"
            except Exception as v_err:
                logger.info("Vertex image model %s skipped: %s", m_img, v_err)
        return None, ""

    # Developer API Interactions fallback
    try:
        input_parts: List[Dict[str, Any]] = []
        for p in reference_paths:
            if p.exists():
                b64 = base64.b64encode(p.read_bytes()).decode("utf-8")
                input_parts.append({"type": "image", "data": b64, "mime_type": "image/png"})
        input_parts.append({"type": "text", "text": prompt})
        interaction = call_interaction_with_fallback(
            client,
            models=img_models,
            max_retries=2,
            input=input_parts,
            response_format={"type": "image", "aspect_ratio": "16:9", "image_size": "2K"},
        )
        out_img = getattr(interaction, "output_image", None)
        if out_img and getattr(out_img, "data", None):
            raw = base64.b64decode(out_img.data) if isinstance(out_img.data, str) else bytes(out_img.data)
            return raw, f"gemini_api({img_models[0]})"
    except Exception as exc:
        logger.info("Developer API image generation skipped: %s", exc)
    return None, ""


def generate_high_ctr_thumbnail(
    output_png_path: Path,
    *,
    topic: str,
    niche: str,
    headline: str,
    badge_label: str,
    graphic_concept: str,
    include_creator_avatar: bool = False,
    avatar_mode: str = "real_photo",
    creator_side: str = "left",
    config: Optional[OmniStudioConfig] = None,
    use_ai_image_api: bool = True,
) -> Tuple[Path, str]:
    """
    Generates a crisp High-CTR 16:9 YouTube thumbnail.
    - `include_creator_avatar=False`: Pure faceless cinematic artwork + bold neon typography.
    - `include_creator_avatar=True, avatar_mode="real_photo"`: AI cinematic backdrop + authentic real photo cutout.
    - `include_creator_avatar=True, avatar_mode="ai_pro"`: `gemini-3-pro-image` portrait using clean studio refs.
    - Native Devanagari rendering via `gemini-3-pro-image` whenever Hindi script is detected (zero tofu boxes!).
    """
    cfg = config or OmniStudioConfig()
    prof = get_niche_profile(niche)
    acc_rgb = _hex_to_rgb(prof["accent_hex"])
    clean_portraits = _get_clean_studio_portraits(cfg)
    has_hindi_script = _contains_devanagari(headline) or _contains_devanagari(badge_label)
    output_png_path.parent.mkdir(parents=True, exist_ok=True)

    if use_ai_image_api and cfg.has_valid_gemini_key:
        side_word = "left side" if creator_side == "left" else "right side"
        other_side = "right side" if creator_side == "left" else "left side"

        if not include_creator_avatar:
            # FACELESS CINEMA MODE: 100% pure epic topic visuals
            if has_hindi_script:
                prompt = (
                    f"Create a dramatic, ultra-high-CTR 16:9 YouTube thumbnail poster for '{topic}' ({niche}). "
                    f"Feature breathtaking epic 3D cinematic visuals on the right half: {graphic_concept}. "
                    f"Visual style: {prof['visual_style']}. Deep dark obsidian atmospheric glow on the left half. "
                    f"On the upper-left dark area, render razor-sharp, bold, accurately spelled Hindi Devanagari "
                    f"poster title '{headline}' in bright glowing metallic gold and white with dark drop-shadow, "
                    f"plus a sleek small red badge above it reading '{badge_label}'. "
                    f"Do NOT include any other random words, watermarks, or labels."
                )
            else:
                prompt = (
                    f"Create a breathtaking, dramatic 16:9 widescreen cinematic photograph representing '{topic}' ({niche}). "
                    f"Place the main glowing visual focal subject prominently on the right half: {graphic_concept}. "
                    f"Visual style: {prof['visual_style']}. Keep the left half as deep dark atmospheric bokeh "
                    f"with subtle rim glow and minimal visual clutter. "
                    f"STRICTLY PURE PHOTOGRAPHIC ARTWORK ONLY — zero letters, zero words, zero labels, zero captions anywhere in the frame."
                )
            raw_bytes, eng = _call_ai_image_generation(prompt=prompt, reference_paths=[], config=cfg)
            if raw_bytes:
                ai_pil = Image.open(io.BytesIO(raw_bytes)).convert("RGBA")
                if has_hindi_script:
                    # Gemini 3 Pro Image rendered properly-shaped Devanagari natively!
                    ai_pil.resize((1920, 1080), Image.Resampling.LANCZOS).convert("RGB").save(
                        output_png_path, format="PNG", optimize=True
                    )
                    return output_png_path, f"faceless_native_hindi_{eng}"
                final_pil = _apply_high_ctr_typography_overlay(
                    ai_pil,
                    headline=headline,
                    badge_label=badge_label,
                    topic=topic,
                    niche=niche,
                    include_creator_avatar=False,
                    creator_side="right",
                )
                final_pil.convert("RGB").save(output_png_path, format="PNG", optimize=True)
                return output_png_path, f"faceless_cinema_{eng}"

        elif avatar_mode == "real_photo":
            # REAL STUDIO PHOTO CUTOUT MODE: AI generates epic topic scene; authentic real portrait composited!
            if has_hindi_script:
                prompt = (
                    f"Create a dramatic 16:9 YouTube thumbnail background for '{topic}' ({niche}). "
                    f"Keep the {side_word} as deep dark blurred bokeh atmosphere. "
                    f"On the lower {other_side}, render dramatic glowing 3D visuals: {graphic_concept}. "
                    f"Style: {prof['visual_style']}. "
                    f"On the upper {other_side}, render razor-sharp bold glowing metallic gold and white Hindi "
                    f"Devanagari headline '{headline}' with a small crimson badge reading '{badge_label}' above it. "
                    f"No human faces in the image, no extra random words."
                )
            else:
                prompt = (
                    f"Create a dramatic 16:9 cinematic background artwork representing '{topic}' ({niche}). "
                    f"Keep the {side_word} dark atmospheric studio bokeh. On the lower {other_side}, render rich "
                    f"glowing 3D conceptual visuals: {graphic_concept}. Style: {prof['visual_style']}. "
                    f"STRICTLY PURE TEXTLESS BACKGROUND ARTWORK — zero humans, zero words, zero letters, zero labels anywhere."
                )
            raw_bytes, eng = _call_ai_image_generation(prompt=prompt, reference_paths=[], config=cfg)
            if raw_bytes:
                ai_pil = Image.open(io.BytesIO(raw_bytes)).convert("RGBA")
                primary_portrait = clean_portraits[0] if clean_portraits else None
                if primary_portrait:
                    ai_pil = _paste_clean_real_portrait(
                        ai_pil, primary_portrait, creator_side=creator_side, accent_rgb=acc_rgb
                    )
                if has_hindi_script:
                    ai_pil.convert("RGB").save(output_png_path, format="PNG", optimize=True)
                    return output_png_path, f"real_photo_hindi_{eng}"
                final_pil = _apply_high_ctr_typography_overlay(
                    ai_pil,
                    headline=headline,
                    badge_label=badge_label,
                    topic=topic,
                    niche=niche,
                    include_creator_avatar=True,
                    creator_side=creator_side,
                )
                final_pil.convert("RGB").save(output_png_path, format="PNG", optimize=True)
                return output_png_path, f"real_photo_cutout_{eng}"

        else:
            # AI STUDIO PORTRAIT MODE (`gemini-3-pro-image` using ONLY clean studio photos image_13 & image_14)
            if has_hindi_script:
                prompt = (
                    f"Create an ultra-polished 16:9 YouTube thumbnail featuring the exact Indian male creator "
                    f"from these two reference studio portraits — preserving his exact natural face, glasses, "
                    f"neatly trimmed beard, youthful warm skin tone, and hairstyle with flattering soft key lighting. "
                    f"Position him on the {side_word} wearing a crisp tailored dark charcoal Nehru jacket over a "
                    f"black collared shirt, with a warm, confident, engaging smile, gesturing smoothly toward the {other_side}. "
                    f"On the lower {other_side}, render dramatic glowing 3D visuals representing '{topic}': {graphic_concept}. "
                    f"On the upper {other_side}, render bold, accurately spelled glowing gold & white Hindi Devanagari "
                    f"title '{headline}' with a small crimson pill badge '{badge_label}' above it. "
                    f"Style: {prof['visual_style']}. Zero other random text or watermarks."
                )
            else:
                prompt = (
                    f"Create an ultra-polished 16:9 widescreen studio photograph featuring the exact Indian male creator "
                    f"from these two reference portraits — preserving his exact natural face, glasses, neatly trimmed beard, "
                    f"youthful flattering skin tone, and hairstyle with soft commercial key lighting and rim glow. "
                    f"Position him on the {side_word} wearing a sharp tailored dark charcoal Nehru jacket over a black shirt, "
                    f"with a warm confident charismatic expression, gesturing smoothly toward the lower {other_side}. "
                    f"On the lower {other_side}, render vivid glowing 3D conceptual visuals representing '{topic}': {graphic_concept}. "
                    f"Keep the upper {other_side} as deep dark empty starry/bokeh negative atmosphere. "
                    f"Style: {prof['visual_style']}. STRICTLY COMPLETELY TEXTLESS PHOTOGRAPH — zero words, zero letters, zero labels anywhere."
                )
            raw_bytes, eng = _call_ai_image_generation(prompt=prompt, reference_paths=clean_portraits, config=cfg)
            if raw_bytes:
                ai_pil = Image.open(io.BytesIO(raw_bytes)).convert("RGBA")
                if has_hindi_script:
                    ai_pil.resize((1920, 1080), Image.Resampling.LANCZOS).convert("RGB").save(
                        output_png_path, format="PNG", optimize=True
                    )
                    return output_png_path, f"ai_pro_avatar_hindi_{eng}"
                final_pil = _apply_high_ctr_typography_overlay(
                    ai_pil,
                    headline=headline,
                    badge_label=badge_label,
                    topic=topic,
                    niche=niche,
                    include_creator_avatar=True,
                    creator_side=creator_side,
                )
                final_pil.convert("RGB").save(output_png_path, format="PNG", optimize=True)
                return output_png_path, f"ai_pro_avatar_{eng}"

    # Offline / local studio compositor fallback
    primary_portrait = clean_portraits[0] if (include_creator_avatar and clean_portraits) else None
    fallback_bg = _build_local_fallback_backdrop(
        niche=niche,
        include_creator_avatar=include_creator_avatar,
        creator_side=creator_side,
        portrait_path=primary_portrait,
    )
    final_fb = _apply_high_ctr_typography_overlay(
        fallback_bg,
        headline=headline,
        badge_label=badge_label,
        topic=topic,
        niche=niche,
        include_creator_avatar=include_creator_avatar,
        creator_side=creator_side,
    )
    final_fb.convert("RGB").save(output_png_path, format="PNG", optimize=True)
    return output_png_path, "local_studio_compositor"
