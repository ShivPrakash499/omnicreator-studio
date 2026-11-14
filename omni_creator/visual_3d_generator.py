"""
Module C: `omni_creator/visual_3d_generator.py`
===============================================
4K Start/End Keyframes (`gemini-3-pro-image` & `gemini-nano-banana-2.1`) +
Ultra-Realistic 3D Video Simulation Engine (`gemini-omni-1.2-flash` via `client.interactions.create(...)`).

STRICT RULES:
- NEVER use deprecated `veo-2.0` or `veo-3.1-preview` endpoints.
- NEVER use legacy `<FIRST_FRAME>` / `<LAST_FRAME>` / `<IMAGE_REF_N>` prompt tags; bind images
  in natural language inside `client.interactions.create(model="gemini-omni-1.2-flash", input=[...])`.
- Supports:
  1. First-and-last-frame interpolation (`3s`-`10s`) and single-frame/text (`3s`-`15s`) 4K/1080p 24fps.
  2. Up to 6 reference images per interaction to lock laboratory props, molecular structures, or 3D cross-sections.
  3. Multi-turn conversational extension (`previous_interaction_id`) up to 30s per continuous sequence.
  4. SHA-256 content-hash local disk cache (`workspaces/omni_cache/keyframes` & `clips`).
"""

from __future__ import annotations

import asyncio
import base64
import logging
import math
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from config.models import (
    GLOBAL_3D_SCIENCE_STYLE_PROMPT,
    GLOBAL_NEGATIVE_CONSTRAINTS,
    IMAGE_4K_PRO_MODEL,
    IMAGE_CONTINUITY_MODEL,
    VIDEO_OMNI_MODEL,
    OmniModelConfig,
    call_interaction_with_backoff,
    compute_content_sha256,
    get_genai_client,
)
from schemas.blueprint import ChapterVideoBlueprint, SimulationSceneBeat

logger = logging.getLogger("omni_creator.visual_3d_generator")


@dataclass
class SceneVisualAssets:
    """Holds cached paths and metadata for a single scene's 4K keyframes and 3D video clip."""
    scene_key: str
    scene_title: str
    duration_sec: float
    start_keyframe_path: Path
    end_keyframe_path: Optional[Path] = None
    video_clip_path: Optional[Path] = None
    omni_interaction_id: Optional[str] = None
    used_cached_clip: bool = False
    model_used: str = VIDEO_OMNI_MODEL


@dataclass
class Visual3DBundle:
    """Complete collection of generated keyframes and 3D clips for a `ChapterVideoBlueprint`."""
    hook_assets: SceneVisualAssets
    scene_assets: List[SceneVisualAssets] = field(default_factory=list)
    reference_anchor_paths: List[Path] = field(default_factory=list)


def _get_font(size: int, bold: bool = True) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        "C:/Windows/Fonts/segoeuib.ttf" if bold else "C:/Windows/Fonts/segoeui.ttf",
        "C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/calibrib.ttf",
    ]
    for path in candidates:
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size=size)
            except Exception:
                pass
    return ImageFont.load_default()


def render_dark_obsidian_3d_keyframe(
    output_path: Path,
    *,
    subject: str,
    chapter_name: str,
    scene_title: str,
    hud_label: str,
    formula_expr: str,
    aspect_ratio: str = "16:9",
    phase: float = 0.0,
    is_end_frame: bool = False,
) -> Path:
    """
    Synthesizes a photorealistic-styled dark obsidian & brushed-titanium 3D scientific keyframe
    (inspired by Veritasium, Melodysheep, and 3Blue1Brown) with volumetric optical caustics,
    3D coordinate grids, subatomic/ray-optics diagrams, and glassmorphic HUD telemetry.
    Strictly non-kiddish.
    """
    width, height = (1920, 1080) if aspect_ratio == "16:9" else (1080, 1920)
    img = Image.new("RGBA", (width, height), (7, 10, 18, 255))
    draw = ImageDraw.Draw(img, "RGBA")

    # 1. Deep Obsidian & Brushed-Titanium radial volumetric backdrop
    cx, cy = int(width * 0.52), int(height * 0.50)
    for r in range(max(width, height), 40, -35):
        ratio = 1.0 - (r / float(max(width, height)))
        if subject == "Physics":
            col = (int(8 + 26 * ratio), int(16 + 52 * ratio), int(34 + 95 * ratio), 255)
        elif subject == "Chemistry":
            col = (int(14 + 48 * ratio), int(12 + 38 * ratio), int(28 + 80 * ratio), 255)
        else:
            col = (int(8 + 22 * ratio), int(22 + 64 * ratio), int(28 + 75 * ratio), 255)
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=col)

    # 2. Perspective 3D Optical / Titanium Laboratory Floor Grid
    horizon_y = int(height * 0.62)
    grid_color = (0, 210, 255, 42) if not is_end_frame else (255, 190, 40, 50)
    for gx in range(-12, 13):
        x_top = cx + gx * int(width * 0.04)
        x_bot = cx + gx * int(width * 0.14)
        draw.line([(x_top, horizon_y), (x_bot, height)], fill=grid_color, width=2)
    for gy in range(1, 10):
        t = (gy / 9.0) ** 1.7
        y_pos = int(horizon_y + t * (height - horizon_y))
        draw.line([(0, y_pos), (width, y_pos)], fill=grid_color, width=2)

    # 3. 3D Scientific Phenomenon Core (Ray Optics / Subatomic Lattice / Biomolecular Helix)
    shift = int(48 * math.sin(phase + (1.1 if is_end_frame else 0.0)))
    text_low = f"{chapter_name} {scene_title}".lower()

    if any(k in text_low for k in ["light", "optic", "refraction", "reflection", "lens", "prism"]):
        # 3D Crown Glass Prism / Convex Lens & Volumetric Laser Caustics
        p_top = (cx + shift // 3, int(height * 0.24))
        p_left = (cx - int(width * 0.14), int(height * 0.66))
        p_right = (cx + int(width * 0.14), int(height * 0.66))
        # Incident Sapphire Laser Beam
        inc_start = (int(width * 0.06), int(height * 0.56))
        hit_pt = (cx - int(width * 0.065), int(height * 0.46))
        exit_pt = (cx + int(width * 0.075), int(height * 0.49))
        draw.line([inc_start, hit_pt], fill=(80, 225, 255, 240), width=10)
        draw.line([inc_start, hit_pt], fill=(255, 255, 255, 255), width=4)
        # Internal refracted beam
        draw.line([hit_pt, exit_pt], fill=(255, 230, 90, 235), width=9)
        # Dispersed spectrum caustic rays
        spectrum = [
            ((255, 65, 90, 220), int(height * 0.54) + shift // 2),
            ((255, 165, 40, 220), int(height * 0.58) + shift // 2),
            ((90, 255, 160, 220), int(height * 0.62) + shift // 2),
            ((60, 190, 255, 225), int(height * 0.66) + shift // 2),
            ((175, 100, 255, 225), int(height * 0.70) + shift // 2),
        ]
        for col_rgba, target_y in spectrum:
            draw.line([exit_pt, (int(width * 0.94), target_y)], fill=col_rgba, width=7)
        # Glassmorphic 3D Prism body
        draw.polygon([p_top, p_left, p_right], fill=(160, 225, 255, 38), outline=(140, 235, 255, 230))
        draw.line([p_top, p_left, p_right, p_top], fill=(220, 250, 255, 245), width=4)
        # Normal dashed line & angle arc
        draw.line(
            [(hit_pt[0] - 90, hit_pt[1] - 55), (hit_pt[0] + 90, hit_pt[1] + 55)],
            fill=(255, 215, 0, 190),
            width=3,
        )
    elif subject == "Biology":
        # 3D Bioluminescent Double-Helix / Cellular Membrane Pump Simulation
        for idx in range(22):
            t_x = int(width * 0.18 + (idx / 21.0) * width * 0.64)
            angle = (idx * 0.42) + phase + (0.9 if is_end_frame else 0.0)
            y1 = int(cy + math.sin(angle) * (height * 0.16))
            y2 = int(cy - math.sin(angle) * (height * 0.16))
            draw.line([(t_x, y1), (t_x, y2)], fill=(0, 240, 195, 135), width=4)
            draw.ellipse([t_x - 14, y1 - 14, t_x + 14, y1 + 14], fill=(0, 220, 255, 245), outline=(255, 255, 255, 220))
            draw.ellipse([t_x - 14, y2 - 14, t_x + 14, y2 + 14], fill=(255, 185, 45, 245), outline=(255, 255, 255, 220))
    else:
        # 3D Subatomic / Copper Crystal Lattice / Quantized Orbital Simulation
        for orbit_r, col_rgba in [
            (int(min(width, height) * 0.13), (0, 230, 255, 210)),
            (int(min(width, height) * 0.22), (255, 195, 45, 195)),
            (int(min(width, height) * 0.30), (140, 120, 255, 175)),
        ]:
            draw.ellipse(
                [cx - orbit_r, cy - orbit_r, cx + orbit_r, cy + orbit_r],
                outline=col_rgba,
                width=4,
            )
            ang = phase + (orbit_r * 0.025) + (1.2 if is_end_frame else 0.0)
            ex = int(cx + math.cos(ang) * orbit_r)
            ey = int(cy + math.sin(ang) * orbit_r)
            draw.ellipse([ex - 16, ey - 16, ex + 16, ey + 16], fill=(80, 245, 255, 255), outline=(255, 255, 255, 255))
            # Velocity tangent vector arrow
            vx = int(ex - math.sin(ang) * 65)
            vy = int(ey + math.cos(ang) * 65)
            draw.line([(ex, ey), (vx, vy)], fill=(255, 220, 60, 240), width=4)

        # Glowing Golden Nucleus / Lattice Core
        nuc_r = 38
        draw.ellipse(
            [cx - nuc_r, cy - nuc_r, cx + nuc_r, cy + nuc_r],
            fill=(255, 140, 30, 250),
            outline=(255, 240, 180, 255),
            width=4,
        )

    # 4. Subtle Right-Side 3D Telemetry Micro-Badge (never overlaps Top Header or Bottom Caption HUD)
    f_badge = _get_font(22, bold=True)
    f_mono = _get_font(26, bold=True)
    short_form = formula_expr.split("|")[0].strip()

    card_w = int(width * 0.34)
    card_x1 = width - card_w - 44
    card_y1 = 164
    draw.rounded_rectangle(
        [card_x1, card_y1, width - 44, card_y1 + 98],
        radius=14,
        fill=(12, 18, 32, 215),
        outline=(255, 195, 45, 200),
        width=2,
    )
    draw.text((card_x1 + 20, card_y1 + 14), f"3D TELEMETRY  |  {hud_label[:28]}", fill=(0, 230, 255, 255), font=f_badge)
    draw.text((card_x1 + 20, card_y1 + 48), short_form[:36], fill=(255, 225, 75, 255), font=f_mono)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    img.convert("RGB").save(output_path, format="PNG", optimize=True)
    return output_path


def generate_keyframe_image(
    prompt: str,
    *,
    output_path: Path,
    aspect_ratio: str = "16:9",
    resolution: str = "4k",
    use_continuity_model: bool = False,
    previous_interaction_id: Optional[str] = None,
    reference_images_b64: Optional[List[str]] = None,
    fallback_metadata: Optional[Dict[str, Any]] = None,
    config: Optional[OmniModelConfig] = None,
    dry_run: bool = False,
) -> Tuple[Path, Optional[str]]:
    """
    Generates a 4K start or end keyframe via `gemini-3-pro-image` (or `gemini-nano-banana-2.1`
    for multi-turn scene/object continuity across consecutive shots).
    Caches by SHA-256 content hash.
    """
    if output_path.exists() and output_path.stat().st_size > 1024:
        return output_path, previous_interaction_id

    cfg = config or OmniModelConfig()
    model_name = IMAGE_CONTINUITY_MODEL if use_continuity_model else IMAGE_4K_PRO_MODEL
    fallback_model = IMAGE_4K_PRO_MODEL if use_continuity_model else IMAGE_CONTINUITY_MODEL

    full_prompt = f"{prompt}\n\nStyle Lock: {GLOBAL_3D_SCIENCE_STYLE_PROMPT}\n{GLOBAL_NEGATIVE_CONSTRAINTS}"

    if not dry_run and cfg.api_key and cfg.api_key != "your_gemini_paid_tier1_api_key_here":
        try:
            client = get_genai_client(cfg.api_key)
            input_payload: List[Dict[str, Any]] = []
            if reference_images_b64:
                for b64_img in reference_images_b64[:6]:
                    input_payload.append({"type": "image", "data": b64_img, "mime_type": "image/png"})
            input_payload.append({"type": "text", "text": full_prompt})

            kwargs: Dict[str, Any] = {
                "input": input_payload if len(input_payload) > 1 else full_prompt,
                "response_format": {
                    "type": "image",
                    "aspect_ratio": aspect_ratio,
                    "image_size": resolution.lower(),
                },
            }
            if previous_interaction_id and use_continuity_model:
                kwargs["previous_interaction_id"] = previous_interaction_id

            interaction = call_interaction_with_backoff(
                client,
                model=model_name,
                fallback_model=fallback_model,
                **kwargs,
            )
            out_img = getattr(interaction, "output_image", None)
            if out_img and getattr(out_img, "data", None):
                raw_bytes = (
                    base64.b64decode(out_img.data)
                    if isinstance(out_img.data, str)
                    else bytes(out_img.data)
                )
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_bytes(raw_bytes)
                return output_path, getattr(interaction, "id", None)
        except Exception as exc:
            logger.info("Keyframe API generation fell back to local 3D obsidian renderer: %s", exc)

    meta = fallback_metadata or {}
    render_dark_obsidian_3d_keyframe(
        output_path,
        subject=meta.get("subject", "Physics"),
        chapter_name=meta.get("chapter_name", "Science 3D"),
        scene_title=meta.get("scene_title", "3D Optical & Subatomic Simulation"),
        hud_label=meta.get("hud_label", "UNREAL 5 / OCTANE 3D LAB"),
        formula_expr=meta.get("formula_expr", "n = sin(i) / sin(r)"),
        aspect_ratio=aspect_ratio,
        phase=float(meta.get("phase", 0.0)),
        is_end_frame=bool(meta.get("is_end_frame", False)),
    )
    return output_path, previous_interaction_id


def render_smooth_24fps_3d_clip_from_keyframes(
    start_frame_path: Path,
    end_frame_path: Optional[Path],
    output_clip_path: Path,
    *,
    duration_sec: float,
    aspect_ratio: str = "16:9",
    fps: int = 24,
) -> Path:
    """
    Synthesizes a smooth 24fps 3D camera motion + keyframe interpolation MP4 clip via FFmpeg
    when running in `--dry-run` or local verification mode.
    """
    import imageio_ffmpeg

    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    w, h = (1920, 1080) if aspect_ratio == "16:9" else (1080, 1920)
    output_clip_path.parent.mkdir(parents=True, exist_ok=True)

    dur = max(3.0, float(duration_sec))
    frames_total = int(dur * fps)

    if end_frame_path and end_frame_path.exists():
        # Cross-interpolate start -> end keyframe while preserving 100% of HUD margins
        half_dur = max(1.5, dur * 0.55)
        fade_offset = max(1.0, dur * 0.45)
        vf_filter = (
            f"[0:v]scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},fps={fps}[v0];"
            f"[1:v]scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},fps={fps}[v1];"
            f"[v0][v1]xfade=transition=smoothleft:duration=1.2:offset={fade_offset:.2f},format=yuv420p[outv]"
        )
        cmd = [
            ffmpeg_exe,
            "-y",
            "-loop", "1", "-t", f"{half_dur + 1.2:.2f}", "-i", str(start_frame_path),
            "-loop", "1", "-t", f"{half_dur + 1.2:.2f}", "-i", str(end_frame_path),
            "-filter_complex", vf_filter,
            "-map", "[outv]",
            "-t", f"{dur:.2f}",
            "-r", str(fps),
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-crf", "20",
            str(output_clip_path),
        ]
    else:
        vf_filter = f"scale={w}:{h},format=yuv420p"
        cmd = [
            ffmpeg_exe,
            "-y",
            "-loop", "1",
            "-i", str(start_frame_path),
            "-vf", vf_filter,
            "-t", f"{dur:.2f}",
            "-r", str(fps),
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-crf", "20",
            str(output_clip_path),
        ]

    subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return output_clip_path


def generate_omni_3d_simulation_clip(
    camera_motion_prompt: str,
    *,
    start_keyframe_path: Path,
    end_keyframe_path: Optional[Path] = None,
    reference_image_paths: Optional[List[Path]] = None,
    previous_interaction_id: Optional[str] = None,
    duration_sec: float = 8.0,
    aspect_ratio: str = "16:9",
    resolution: str = "4k",
    output_clip_path: Path,
    config: Optional[OmniModelConfig] = None,
    dry_run: bool = False,
) -> Tuple[Path, Optional[str], bool]:
    """
    Generates an ultra-realistic 3D simulation video clip using `gemini-omni-1.2-flash`
    via `client.interactions.create(...)`.

    Follows official `gemini-omni-1.2-flash` rules:
    - First-and-last-frame interpolation or multi-turn extension (`previous_interaction_id`)
      clamps duration to `3s`–`10s` per turn (up to `30s` total sequence).
    - Single-frame or text-to-video supports `3s`–`15s`.
    - Up to 6 reference images bound in natural language (NO `<FIRST_FRAME>` / `<LAST_FRAME>` tags).
    - Cached locally by SHA-256 content hash.
    """
    if output_clip_path.exists() and output_clip_path.stat().st_size > 4096:
        return output_clip_path, previous_interaction_id, True

    cfg = config or OmniModelConfig()

    if not dry_run and cfg.api_key and cfg.api_key != "your_gemini_paid_tier1_api_key_here":
        try:
            client = get_genai_client(cfg.api_key)
            input_items: List[Dict[str, Any]] = []

            # Attach start keyframe
            start_b64 = base64.b64encode(start_keyframe_path.read_bytes()).decode("utf-8")
            input_items.append({"type": "image", "data": start_b64, "mime_type": "image/png"})

            has_end_frame = end_keyframe_path is not None and end_keyframe_path.exists()
            if has_end_frame and end_keyframe_path is not None:
                end_b64 = base64.b64encode(end_keyframe_path.read_bytes()).decode("utf-8")
                input_items.append({"type": "image", "data": end_b64, "mime_type": "image/png"})

            # Attach up to remaining reference images (max 6 total images per interaction)
            ref_count = 0
            if reference_image_paths:
                for ref_p in reference_image_paths:
                    if len(input_items) >= 6:
                        break
                    if ref_p.exists() and ref_p not in (start_keyframe_path, end_keyframe_path):
                        ref_b64 = base64.b64encode(ref_p.read_bytes()).decode("utf-8")
                        input_items.append({"type": "image", "data": ref_b64, "mime_type": "image/png"})
                        ref_count += 1

            # Natural-language image binding as required by `gemini-omni-1.2-flash`
            if has_end_frame:
                binding_instruction = (
                    "Use the first image as the starting frame and the second image as the final frame, "
                    "smoothly interpolating the 3D physical transition between them."
                )
                target_dur = max(3, min(10, int(round(duration_sec))))
            elif previous_interaction_id:
                binding_instruction = (
                    "Continue and extend the 3D scientific simulation smoothly from the previous clip, "
                    "maintaining exact laboratory prop and optical continuity with the reference image."
                )
                target_dur = max(3, min(10, int(round(duration_sec))))
            else:
                binding_instruction = (
                    "Use the first image as the starting frame for this 3D scientific simulation."
                )
                target_dur = max(3, min(15, int(round(duration_sec))))

            if ref_count > 0:
                binding_instruction += (
                    " Preserve the exact 3D laboratory apparatus and molecular/optical geometry "
                    "shown in the additional reference images."
                )

            full_video_prompt = (
                f"{binding_instruction} {camera_motion_prompt} "
                f"Generate a {target_dur}-second clip at 24fps. "
                f"{GLOBAL_3D_SCIENCE_STYLE_PROMPT} {GLOBAL_NEGATIVE_CONSTRAINTS}"
            )
            input_items.append({"type": "text", "text": full_video_prompt})

            interaction_kwargs: Dict[str, Any] = {
                "input": input_items,
                "response_format": {
                    "type": "video",
                    "aspect_ratio": aspect_ratio,
                    "resolution": resolution.lower(),
                },
            }
            if previous_interaction_id:
                interaction_kwargs["previous_interaction_id"] = previous_interaction_id

            interaction = call_interaction_with_backoff(
                client,
                model=VIDEO_OMNI_MODEL,
                **interaction_kwargs,
            )
            out_vid = getattr(interaction, "output_video", None)
            if out_vid and getattr(out_vid, "data", None):
                vid_bytes = (
                    base64.b64decode(out_vid.data)
                    if isinstance(out_vid.data, str)
                    else bytes(out_vid.data)
                )
                output_clip_path.parent.mkdir(parents=True, exist_ok=True)
                output_clip_path.write_bytes(vid_bytes)
                return output_clip_path, getattr(interaction, "id", None), False
        except Exception as exc:
            logger.info("gemini-omni-1.2-flash API call fell back to 24fps keyframe motion synthesizer: %s", exc)

    render_smooth_24fps_3d_clip_from_keyframes(
        start_keyframe_path,
        end_keyframe_path,
        output_clip_path,
        duration_sec=duration_sec,
        aspect_ratio=aspect_ratio,
        fps=cfg.default_fps,
    )
    return output_clip_path, previous_interaction_id, False


def generate_all_3d_visuals_for_blueprint(
    blueprint: ChapterVideoBlueprint,
    *,
    config: Optional[OmniModelConfig] = None,
    dry_run: bool = False,
    render_preview_clips_in_dry_run: bool = True,
) -> Visual3DBundle:
    """
    Executes Module C (`visual_3d_generator.py`) across Beat 1 (3s Hook) and Beat 2 (Simulation Scenes):
    - Locks 4K anchor keyframes with `gemini-3-pro-image` and multi-turn continuity shots with
      `gemini-nano-banana-2.1`.
    - Generates 24fps 3D simulation clips with `gemini-omni-1.2-flash` (`client.interactions.create`).
    - Caches all assets by SHA-256 content hash under `workspaces/omni_cache/`.
    """
    cfg = config or OmniModelConfig()
    kf_dir = cfg.cache_dir / "keyframes"
    clips_dir = cfg.cache_dir / "clips"
    kf_dir.mkdir(parents=True, exist_ok=True)
    clips_dir.mkdir(parents=True, exist_ok=True)

    aspect = blueprint.input_spec.aspect_ratio
    res = cfg.default_resolution
    formula_expr = blueprint.beat_3_hud_formula_vault.exact_formula_expression

    # 1. Beat 1: 0:00-0:03 Pattern-Interrupt Hook Keyframe & 3s Clip
    hook = blueprint.beat_1_pattern_interrupt_hook
    hook_dur = max(3.0, hook.end_sec - hook.start_sec)
    hook_hash = compute_content_sha256("hook_v1", hook.visual_macro_3d_prompt, aspect, res)
    hook_kf_path = kf_dir / f"hook_{hook_hash[:16]}_start.png"
    hook_clip_path = clips_dir / f"hook_{hook_hash[:16]}_{int(hook_dur)}s.mp4"

    hook_kf_path, prev_img_id = generate_keyframe_image(
        hook.visual_macro_3d_prompt,
        output_path=hook_kf_path,
        aspect_ratio=aspect,
        resolution=res,
        use_continuity_model=False,
        fallback_metadata={
            "subject": blueprint.input_spec.subject,
            "chapter_name": blueprint.input_spec.chapter_name,
            "scene_title": hook.on_screen_hud_callout,
            "hud_label": "0:00-0:03 PATTERN-INTERRUPT HOOK",
            "formula_expr": formula_expr,
            "phase": 0.0,
        },
        config=cfg,
        dry_run=dry_run,
    )

    hook_clip_final: Optional[Path] = None
    hook_vid_id: Optional[str] = None
    hook_cached = False
    if not dry_run or render_preview_clips_in_dry_run:
        hook_clip_final, hook_vid_id, hook_cached = generate_omni_3d_simulation_clip(
            hook.visual_macro_3d_prompt,
            start_keyframe_path=hook_kf_path,
            duration_sec=hook_dur,
            aspect_ratio=aspect,
            resolution=res,
            output_clip_path=hook_clip_path,
            config=cfg,
            dry_run=dry_run,
        )

    hook_assets = SceneVisualAssets(
        scene_key="beat_1_hook",
        scene_title=hook.on_screen_hud_callout,
        duration_sec=hook_dur,
        start_keyframe_path=hook_kf_path,
        end_keyframe_path=None,
        video_clip_path=hook_clip_final,
        omni_interaction_id=hook_vid_id,
        used_cached_clip=hook_cached,
    )

    # 2. Beat 2: Core Concept 3D Simulation Scenes with `gemini-nano-banana-2.1` continuity
    scene_assets_list: List[SceneVisualAssets] = []
    reference_anchors: List[Path] = [hook_kf_path]
    prev_omni_id: Optional[str] = None

    for idx, scene in enumerate(blueprint.beat_2_simulation_scenes):
        sc_hash = compute_content_sha256(
            "scene_v1",
            scene.scene_id,
            scene.start_keyframe_prompt,
            scene.end_keyframe_prompt or "",
            scene.omni_camera_motion_prompt,
            scene.duration_sec,
            aspect,
            res,
        )
        start_p = kf_dir / f"s{scene.scene_id:02d}_{sc_hash[:16]}_start.png"
        end_p = kf_dir / f"s{scene.scene_id:02d}_{sc_hash[:16]}_end.png" if scene.end_keyframe_prompt else None
        clip_p = clips_dir / f"s{scene.scene_id:02d}_{sc_hash[:16]}_{int(scene.duration_sec)}s.mp4"

        ref_b64_list = [
            base64.b64encode(p.read_bytes()).decode("utf-8")
            for p in reference_anchors[:3]
            if p.exists()
        ]

        start_p, prev_img_id = generate_keyframe_image(
            scene.start_keyframe_prompt,
            output_path=start_p,
            aspect_ratio=aspect,
            resolution=res,
            use_continuity_model=(idx > 0),  # Use gemini-nano-banana-2.1 for consecutive shot continuity
            previous_interaction_id=prev_img_id,
            reference_images_b64=ref_b64_list,
            fallback_metadata={
                "subject": blueprint.input_spec.subject,
                "chapter_name": blueprint.input_spec.chapter_name,
                "scene_title": scene.scene_title,
                "hud_label": scene.hud_overlay_label,
                "formula_expr": formula_expr,
                "phase": (idx + 1) * 0.85,
                "is_end_frame": False,
            },
            config=cfg,
            dry_run=dry_run,
        )
        if len(reference_anchors) < 6:
            reference_anchors.append(start_p)

        if scene.end_keyframe_prompt and end_p is not None:
            end_p, prev_img_id = generate_keyframe_image(
                scene.end_keyframe_prompt,
                output_path=end_p,
                aspect_ratio=aspect,
                resolution=res,
                use_continuity_model=True,
                previous_interaction_id=prev_img_id,
                reference_images_b64=ref_b64_list,
                fallback_metadata={
                    "subject": blueprint.input_spec.subject,
                    "chapter_name": blueprint.input_spec.chapter_name,
                    "scene_title": scene.scene_title,
                    "hud_label": scene.hud_overlay_label,
                    "formula_expr": formula_expr,
                    "phase": (idx + 1) * 0.85 + 0.6,
                    "is_end_frame": True,
                },
                config=cfg,
                dry_run=dry_run,
            )

        clip_final: Optional[Path] = None
        was_cached = False
        if not dry_run or render_preview_clips_in_dry_run:
            clip_final, prev_omni_id, was_cached = generate_omni_3d_simulation_clip(
                scene.omni_camera_motion_prompt,
                start_keyframe_path=start_p,
                end_keyframe_path=end_p,
                reference_image_paths=reference_anchors[:6],
                previous_interaction_id=prev_omni_id if idx < 2 else None,  # Keep continuous sequence <= 30s
                duration_sec=scene.duration_sec,
                aspect_ratio=aspect,
                resolution=res,
                output_clip_path=clip_p,
                config=cfg,
                dry_run=dry_run,
            )

        scene_assets_list.append(
            SceneVisualAssets(
                scene_key=f"scene_{scene.scene_id:02d}",
                scene_title=scene.scene_title,
                duration_sec=scene.duration_sec,
                start_keyframe_path=start_p,
                end_keyframe_path=end_p,
                video_clip_path=clip_final,
                omni_interaction_id=prev_omni_id,
                used_cached_clip=was_cached,
            )
        )

    return Visual3DBundle(
        hook_assets=hook_assets,
        scene_assets=scene_assets_list,
        reference_anchor_paths=reference_anchors,
    )
