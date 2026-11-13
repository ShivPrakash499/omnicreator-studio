#!/usr/bin/env python3
r"""
C:\OmniCreator_Studio\services\studio_engine.py
Clean-Slate Production Engine for TopperLab 3D (@TopperLab3D):
  - Dedicated 100% Faceless High-School STEM & Exam Strategy Studio
    (Class 9–12 • CBSE/ICSE • JEE Mains/Adv • NEET UG).
  - Pure 3D Visuals via Nano Banana / Imagen 3 (zero PIL text boxes) + Google Flow (Veo 3.1) clip integration.
  - Clean Indian-English (en-IN) default narration (toggleable to Hinglish hi-IN) normalized to -14 LUFS.
  - Official YouTube Data API v3 OAuth 2.0 + Resumable Upload + Custom Thumbnails + Native Cloud Scheduling (`publishAt`)
    and Official Meta Graph API v21.0 Reels Connector.
"""
from __future__ import annotations

import asyncio
import datetime
import json
import math
import os
import re
import shutil
import sqlite3
import struct
import subprocess
import urllib.parse
import wave
from pathlib import Path
from typing import Any, Dict, List

import requests
from PIL import Image, ImageOps

ROOT_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT_DIR / "config"
CREDS_DIR = CONFIG_DIR / "credentials"
ASSETS_DIR = ROOT_DIR / "assets" / "topperlab_3d"
WORKSPACES_DIR = ROOT_DIR / "workspaces" / "topperlab_3d"


def load_studio_env() -> None:
    for env_path in [ROOT_DIR / ".env", Path(r"C:\YouTube_Studio_Engine\.env")]:
        if env_path.exists():
            for raw in env_path.read_text(encoding="utf-8", errors="ignore").splitlines():
                line = raw.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    val = v.strip().strip('"').strip("'")
                    if val:
                        os.environ.setdefault(k.strip(), val)


load_studio_env()


def to_portable_path(p: str | Path) -> str:
    """Convert any workspace/asset path to a forward-slash relative path portable across Linux & Windows."""
    raw = str(p or "").replace("\\", "/").strip()
    if not raw:
        return ""
    try:
        rel = Path(p).resolve().relative_to(ROOT_DIR.resolve())
        return rel.as_posix()
    except Exception:
        pass
    for marker in ("workspaces/", "assets/", "config/"):
        idx = raw.find(marker)
        if idx != -1:
            return raw[idx:]
    return raw


def resolve_workspace_path(p: str | Path | None) -> Path:
    """Resolve any Windows backslash, POSIX relative, or absolute path safely on both Linux Cloud & Windows."""
    raw = str(p or "").replace("\\", "/").strip()
    if not raw:
        return ROOT_DIR / "__missing__"
    for marker in ("workspaces/", "assets/", "config/"):
        idx = raw.find(marker)
        if idx != -1:
            return ROOT_DIR / raw[idx:]
    cand = Path(raw)
    if cand.is_absolute():
        return cand
    return ROOT_DIR / raw


def sanitize_api_error(err: Any) -> str:
    """Redact API keys, OAuth tokens, and query secrets from error strings."""
    msg = str(err or "")
    msg = re.sub(r"([?&](?:key|api_key|access_token)=)[^&\s'\"]+", r"\1[REDACTED]", msg, flags=re.IGNORECASE)
    msg = re.sub(r"\b(AIza[0-9A-Za-z\-_]{20,}|AQ\.[0-9A-Za-z\-_.]{20,}|ya29\.[0-9A-Za-z\-_.]+|GOCSPX-[0-9A-Za-z\-_]+)\b", "[REDACTED_KEY]", msg)
    return msg


def slugify(text: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "-", (text or "").lower()).strip("-")
    return s[:56] or "topperlab-episode"


def get_ffmpeg_exe() -> str:
    found = shutil.which(os.environ.get("FFMPEG_BINARY_PATH", "ffmpeg"))
    if found:
        return found
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return "ffmpeg"


# ============================================================================
# 1. SINGLE-CHANNEL PROFILE & PILLARS CONFIG
# ============================================================================
def load_active_channel() -> Dict[str, Any]:
    path = CONFIG_DIR / "active_channel.json"
    return json.loads(path.read_text(encoding="utf-8"))


def save_active_channel(profile: Dict[str, Any]) -> Dict[str, Any]:
    path = CONFIG_DIR / "active_channel.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(profile, indent=2, ensure_ascii=False), encoding="utf-8")
    return profile


def load_pillars_config() -> Dict[str, Any]:
    path = CONFIG_DIR / "highschool_pillars.json"
    return json.loads(path.read_text(encoding="utf-8"))


# ============================================================================
# 2. GEMINI 2.5 + NANO BANANA / IMAGEN 3 + VEO 3.1 HELPERS
# ============================================================================
def _saved_gemini_key_file() -> Path:
    CREDS_DIR.mkdir(parents=True, exist_ok=True)
    return CREDS_DIR / "gemini_api_key.txt"


def set_runtime_gemini_api_key(api_key: str) -> None:
    clean = (api_key or "").strip()
    if clean:
        os.environ["RUNTIME_GEMINI_API_KEY"] = clean
        os.environ["GEMINI_API_KEY"] = clean
        try:
            _saved_gemini_key_file().write_text(clean, encoding="utf-8")
        except Exception:
            pass


def get_gemini_api_key() -> str:
    rt = os.environ.get("RUNTIME_GEMINI_API_KEY", "").strip()
    if rt:
        return rt
    saved_file = _saved_gemini_key_file()
    if saved_file.exists():
        try:
            file_val = saved_file.read_text(encoding="utf-8").strip()
            if file_val:
                return file_val
        except Exception:
            pass
    try:
        import streamlit as st

        for key_name in ("GEMINI_API_KEY", "GOOGLE_API_KEY"):
            if key_name in st.secrets:
                sval = str(st.secrets[key_name]).strip()
                if sval:
                    return sval
    except Exception:
        pass
    for key_name in ("GEMINI_API_KEY", "GOOGLE_API_KEY"):
        val = os.environ.get(key_name, "").strip()
        if val:
            return val
    return ""


def _vertex_adc_file() -> Path:
    CREDS_DIR.mkdir(parents=True, exist_ok=True)
    return CREDS_DIR / "vertex_adc.json"


def _load_vertex_adc_dict() -> Dict[str, Any] | None:
    env_raw = os.environ.get("VERTEX_ADC_JSON", "").strip()
    if not env_raw:
        try:
            import streamlit as st

            if "VERTEX_ADC_JSON" in st.secrets:
                env_raw = str(st.secrets["VERTEX_ADC_JSON"]).strip()
        except Exception:
            pass
    if env_raw:
        try:
            return json.loads(env_raw)
        except Exception:
            pass
    for cand in [
        _vertex_adc_file(),
        Path(os.environ.get("APPDATA", "")) / "gcloud" / "application_default_credentials.json",
        Path.home() / ".config" / "gcloud" / "application_default_credentials.json",
    ]:
        try:
            if cand.is_file():
                return json.loads(cand.read_text(encoding="utf-8"))
        except Exception:
            continue
    return None


def has_vertex_adc() -> bool:
    return _load_vertex_adc_dict() is not None


def _is_vertex_client(client: Any) -> bool:
    return bool(getattr(client, "vertexai", False) or getattr(getattr(client, "_api_client", None), "vertexai", False))


def build_genai_client(location: str = "global", timeout_ms: int = 60000, api_key_override: str | None = None):
    """
    Builds an authenticated google-genai Client:
      1. If an explicit runtime api_key_override is passed, uses AI Studio API key mode.
      2. If Vertex AI Cloud Credits credentials (VERTEX_ADC_JSON / gcloud ADC) are available,
         uses Vertex AI on gen-lang-client-0777980903 (draws directly from ₹28.5K + ₹3.8K GCP credits at ₹0 cash cost).
      3. Otherwise falls back to GEMINI_API_KEY.
    """
    from google import genai
    from google.genai import types

    project_id = os.environ.get("VERTEX_PROJECT_ID", "gen-lang-client-0777980903").strip()
    if not api_key_override:
        adc_info = _load_vertex_adc_dict()
        if adc_info:
            try:
                scopes = ["https://www.googleapis.com/auth/cloud-platform"]
                if adc_info.get("type") == "service_account":
                    from google.oauth2 import service_account

                    creds = service_account.Credentials.from_service_account_info(adc_info, scopes=scopes).with_quota_project(project_id)
                else:
                    from google.oauth2.credentials import Credentials

                    creds = Credentials.from_authorized_user_info(adc_info, scopes=scopes).with_quota_project(project_id)
                return genai.Client(
                    vertexai=True,
                    project=project_id,
                    location=location,
                    credentials=creds,
                    http_options=types.HttpOptions(timeout=timeout_ms),
                )
            except Exception:
                pass

    key = (api_key_override or get_gemini_api_key()).strip()
    if key:
        return genai.Client(api_key=key, http_options=types.HttpOptions(timeout=timeout_ms))
    return None


SCRIPT_MODEL_PRESETS: Dict[str, str] = {
    "gemini-4-argon": "Gemini 4 Argon ⭐ (Best STEM & JEE/NEET Reasoning)",
    "gemini-4-hydrogen": "Gemini 4 Hydrogen ⚡ (Fastest Gemini 4 Workhorse)",
    "gemini-4-carbon": "Gemini 4 Carbon 🧠 (Deepest Frontier — Auto-Fallback to Argon)",
    "gemini-3.8-flash": "Gemini 3.8 Flash (Ultra-Light Fallback)",
}

SCRIPT_MODEL_SHORT_NAMES: Dict[str, str] = {
    "gemini-4-argon": "Gemini 4 Argon",
    "gemini-4-hydrogen": "Gemini 4 Hydrogen",
    "gemini-4-carbon": "Gemini 4 Carbon",
    "gemini-3.8-flash": "Gemini 3.8 Flash",
}


def get_active_script_model() -> str:
    rt = os.environ.get("RUNTIME_SCRIPT_MODEL", "").strip()
    if rt in SCRIPT_MODEL_PRESETS:
        return rt
    try:
        import streamlit as st

        if "SCRIPT_MODEL" in st.secrets:
            sval = str(st.secrets["SCRIPT_MODEL"]).strip()
            if sval in SCRIPT_MODEL_PRESETS:
                return sval
    except Exception:
        pass
    return "gemini-4-argon"


def set_active_script_model(model_id: str) -> None:
    clean = (model_id or "").strip()
    if clean:
        os.environ["RUNTIME_SCRIPT_MODEL"] = clean
        os.environ["SCRIPT_MODEL"] = clean


def _ordered_script_models(preferred: str | None = None) -> List[str]:
    first = (preferred or get_active_script_model()).strip()
    ordered: List[str] = []
    for m in (first, "gemini-4-argon", "gemini-4-hydrogen", "gemini-3.8-flash"):
        if m and m not in ordered:
            ordered.append(m)
    return ordered


def check_gemini_api_key_health(api_key: str | None = None, preferred_model: str | None = None) -> Dict[str, Any]:
    runtime_override = os.environ.get("RUNTIME_GEMINI_API_KEY", "").strip()
    effective_override = runtime_override if runtime_override else (None if has_vertex_adc() else (api_key if api_key else None))
    client = build_genai_client(location="global", timeout_ms=60000, api_key_override=effective_override)
    if client is None:
        return {
            "ok": False,
            "code": "MISSING",
            "summary": "No Gemini / Vertex AI Credentials Set (Free Built-In 3D Renderer Works!)",
            "detail": (
                "Add VERTEX_ADC_JSON in Streamlit Secrets to use your ₹28.5K+ Google Cloud credits, "
                "or paste a Free-Tier AIza... key below."
            ),
        }
    try:
        is_vertex = _is_vertex_client(client)
        candidates = _ordered_script_models(preferred_model)
        requested = candidates[0]
        last_err = ""
        for probe_model in candidates:
            try:
                if not is_vertex and hasattr(client, "interactions"):
                    inter = client.interactions.create(model=probe_model, input="Reply OK")
                    if getattr(inter, "output_text", None):
                        short_lbl = SCRIPT_MODEL_SHORT_NAMES.get(probe_model, probe_model)
                        return {
                            "ok": True,
                            "code": "ACTIVE",
                            "active_model": probe_model,
                            "summary": f"{short_lbl} Active (Gemini AI Key)",
                            "detail": f"Verified live on {probe_model}.",
                        }
                resp = client.models.generate_content(model=probe_model, contents="Reply OK")
                if getattr(resp, "text", None):
                    short_lbl = SCRIPT_MODEL_SHORT_NAMES.get(probe_model, probe_model)
                    mode_lbl = "Vertex AI Cloud Credits" if is_vertex else "Gemini AI Studio Key"
                    fallback_note = (
                        f" ({SCRIPT_MODEL_SHORT_NAMES.get(requested, requested)} auto-routed to {short_lbl} on Vertex AI)"
                        if probe_model != requested
                        else ""
                    )
                    return {
                        "ok": True,
                        "code": "ACTIVE",
                        "active_model": probe_model,
                        "summary": f"{short_lbl} + Nano Banana 3D Active ({mode_lbl})",
                        "detail": (
                            f"Verified live on {probe_model}{fallback_note} "
                            f"({project_label() if is_vertex else 'AI Studio'}) — scripts, 3D renders & Veo 3.1 ready!"
                        ),
                    }
            except Exception as exc:
                last_err = sanitize_api_error(exc)
                low = last_err.lower()
                if "prepayment credits are depleted" in low or "402" in low:
                    return {
                        "ok": False,
                        "code": "PREPAY_EMPTY",
                        "summary": "Paste VERTEX_ADC_JSON in Streamlit Secrets to Unlock ₹28.5K Credits",
                        "detail": (
                            "Add VERTEX_ADC_JSON to Streamlit Cloud → Settings → Secrets so the cloud app routes through "
                            "Vertex AI (₹28,568 + ₹3,810 Cloud credits at ₹0 deposit)!"
                        ),
                    }
                if "outstanding balance" in low:
                    return {
                        "ok": False,
                        "code": "BILLING_HOLD",
                        "summary": "Billing Hold on Key",
                        "detail": last_err[:220],
                    }
                if "api_key_invalid" in low or "api key not valid" in low:
                    return {
                        "ok": False,
                        "code": "INVALID_KEY",
                        "summary": "Invalid Gemini API Key",
                        "detail": "Please paste a valid key or VERTEX_ADC_JSON in Streamlit Secrets.",
                    }
                continue
        return {
            "ok": False,
            "code": "ERROR",
            "summary": "Gemini Connection Notice",
            "detail": last_err[:260],
        }
    except Exception as exc:
        return {
            "ok": False,
            "code": "ERROR",
            "summary": "Gemini Check Notice",
            "detail": sanitize_api_error(exc)[:240],
        }


def project_label() -> str:
    return os.environ.get("VERTEX_PROJECT_ID", "gen-lang-client-0777980903").strip()


def call_gemini_json(prompt: str, fallback: Any) -> Any:
    client = build_genai_client(location="global", timeout_ms=120000)
    if client is None:
        return fallback
    try:
        from google.genai import types

        is_vertex = _is_vertex_client(client)
        for model_id in _ordered_script_models():
            try:
                if not is_vertex and hasattr(client, "interactions"):
                    inter = client.interactions.create(
                        model=model_id,
                        input=f"{prompt}\n\nRespond ONLY with valid raw JSON (no markdown fences).",
                    )
                    txt = (inter.output_text or "").strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
                    if txt:
                        return json.loads(txt)
                resp = client.models.generate_content(
                    model=model_id,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                    ),
                )
                if resp and resp.text:
                    return json.loads(resp.text)
            except Exception:
                continue
    except Exception:
        pass
    return fallback


def _fit_and_save_image(src_img: Image.Image, output_path: Path, target_size: tuple[int, int]) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fitted = ImageOps.fit(src_img.convert("RGB"), target_size, method=Image.Resampling.LANCZOS)
    if output_path.suffix.lower() in (".jpg", ".jpeg"):
        fitted.save(output_path, format="JPEG", quality=93, optimize=True)
    else:
        fitted.save(output_path, format="PNG", optimize=True)
    return output_path


def generate_pure_3d_image(
    prompt: str,
    output_path: Path,
    target_size: tuple[int, int] = (1920, 1080),
    fallback_plate: str = "sample_thumb_16x9.jpg",
    force_live: bool = False,
) -> Path:
    """
    Generates a 100% pure 3D faceless render (zero PIL ImageDraw boxes).
    Uses Vertex AI / Gemini Nano Banana 2.1 when active, otherwise uses
    clean pre-rendered TopperLab 3D plates in assets/topperlab_3d/.
    """
    if output_path.exists() and not force_live:
        return output_path

    clean_prompt = (
        f"{prompt.strip()} "
        "100% faceless 3D scientific studio visualization, zero human faces, zero people, "
        "high-contrast Octane 3D render, crisp volumetric lighting."
    )

    client = build_genai_client(location="global", timeout_ms=90000)
    if client is not None:
        try:
            from io import BytesIO
            from google.genai import types

            is_vertex = _is_vertex_client(client)
            for img_model in (os.environ.get("IMAGE_MODEL", "gemini-nano-banana-2.1"), "gemini-3-pro-image"):
                try:
                    if not is_vertex and hasattr(client, "interactions"):
                        inter = client.interactions.create(model=img_model, input=clean_prompt)
                        out_img = getattr(inter, "output_image", None)
                        if out_img and getattr(out_img, "data", None):
                            import base64
                            raw = base64.b64decode(out_img.data) if isinstance(out_img.data, str) else out_img.data
                            return _fit_and_save_image(Image.open(BytesIO(raw)), output_path, target_size)
                    resp = client.models.generate_content(
                        model=img_model,
                        contents=clean_prompt,
                        config=types.GenerateContentConfig(response_modalities=["IMAGE", "TEXT"]),
                    )
                    for part in getattr(resp.candidates[0].content, "parts", []):
                        inline = getattr(part, "inline_data", None)
                        if inline and getattr(inline, "data", None):
                            img = Image.open(BytesIO(inline.data))
                            return _fit_and_save_image(img, output_path, target_size)
                except Exception:
                    continue
        except Exception:
            pass

    fallback_file = ASSETS_DIR / fallback_plate
    if not fallback_file.exists():
        candidates = list(ASSETS_DIR.glob("*.jpg")) + list(ASSETS_DIR.glob("*.png"))
        if candidates:
            fallback_file = candidates[0]
    if fallback_file.exists():
        img = Image.open(fallback_file)
        return _fit_and_save_image(img, output_path, target_size)

    blank = Image.new("RGB", target_size, (11, 15, 25))
    return _fit_and_save_image(blank, output_path, target_size)


def generate_veo_clip_via_api(
    veo_prompt: str,
    output_mp4: Path,
    aspect_ratio: str = "16:9",
) -> Dict[str, Any]:
    """
    Generates direct 3D physics motion clip via Vertex AI Veo 3.1 (using GCP credits) or Gemini Omni 1.2 Flash.
    """
    clean_prompt = f"{veo_prompt.strip()} Faceless 3D scientific animation, zero human faces."
    try:
        import time
        from google.genai import types

        v_client = build_genai_client(location="us-central1", timeout_ms=300000)
        if v_client is None:
            return {
                "ok": False,
                "message": "Add VERTEX_ADC_JSON in Streamlit Secrets (or use the Free Built-In 3D Renderer at the top of Step 3!).",
            }

        is_vertex = _is_vertex_client(v_client)
        last_err = ""
        if is_vertex:
            for veo_model in ("veo-3.1-fast-generate-001", "veo-3.1-generate-001"):
                try:
                    op = v_client.models.generate_videos(
                        model=veo_model,
                        prompt=clean_prompt,
                        config=types.GenerateVideosConfig(aspect_ratio=aspect_ratio),
                    )
                    for _ in range(42):
                        if getattr(op, "done", False):
                            break
                        time.sleep(5)
                        op = v_client.operations.get(op)
                    if getattr(op, "done", False) and getattr(op, "response", None):
                        vids = getattr(op.response, "generated_videos", [])
                        if vids:
                            vid_obj = vids[0].video
                            raw_bytes = getattr(vid_obj, "video_bytes", None)
                            output_mp4.parent.mkdir(parents=True, exist_ok=True)
                            if raw_bytes:
                                output_mp4.write_bytes(raw_bytes)
                            else:
                                vid_obj.save(str(output_mp4))
                            return {"ok": True, "path": to_portable_path(output_mp4), "model": veo_model}
                except Exception as exc:
                    last_err = sanitize_api_error(exc)
        elif hasattr(v_client, "interactions"):
            try:
                interaction = v_client.interactions.create(
                    model="gemini-omni-1.2-flash",
                    input=[{"type": "text", "text": clean_prompt}],
                    response_format={"type": "video", "delivery": "uri", "aspect_ratio": aspect_ratio},
                )
                out_vid = getattr(interaction, "output_video", None)
                if out_vid and getattr(out_vid, "uri", None):
                    video_bytes = v_client.files.download(file=out_vid.uri)
                    output_mp4.parent.mkdir(parents=True, exist_ok=True)
                    output_mp4.write_bytes(video_bytes)
                    return {"ok": True, "path": to_portable_path(output_mp4), "model": "gemini-omni-1.2-flash"}
            except Exception as exc:
                last_err = sanitize_api_error(exc)

        return {
            "ok": False,
            "message": f"Motion API notice: {last_err[:200] or 'Use the Free Built-In 3D Master Renderer above or drop a Google Flow MP4 clip!'}",
        }
    except Exception as exc:
        return {"ok": False, "message": f"Video API notice: {sanitize_api_error(exc)[:220]}"}


# ============================================================================
# 3. STEP 1: TOPPERLAB 3D BRANDING & PLATFORM OAUTH / GRAPH API CONNECTORS
# ============================================================================
def generate_topperlab_branding(
    custom_banner_prompt: str = "",
    custom_logo_prompt: str = "",
    force_regenerate: bool = False,
) -> Dict[str, Any]:
    ch = load_active_channel()
    brand_dir = WORKSPACES_DIR / "_branding"
    brand_dir.mkdir(parents=True, exist_ok=True)

    banner_path = brand_dir / "topperlab_3d_banner_2560x1440.jpg"
    logo_path = brand_dir / "topperlab_3d_logo_800x800.png"

    b_prompt = custom_banner_prompt.strip() or (
        f"Wide 16:9 futuristic dark obsidian 3D STEM laboratory YouTube banner with wide clean margins; "
        f"strictly centered in the middle safe band, bold 3D brushed-titanium and cyan typography reading "
        f"'{ch['channel_name'].upper()}' above crisp smaller text '3D CONCEPTS • BOARDS • JEE • NEET', "
        f"flanked subtly by glowing 3D DNA helix, magnetic field rings, and geometric vectors, zero @ handle."
    )
    l_prompt = custom_logo_prompt.strip() or (
        f"Iconic 1:1 circular dark obsidian 3D studio badge for {ch['channel_name']}, glowing cyan and gold "
        f"refractive 3D glass prism with orbital atomic rings and vector arrows, high contrast, readable at tiny avatar size."
    )

    generate_pure_3d_image(
        prompt=b_prompt,
        output_path=banner_path,
        target_size=(2560, 1440),
        fallback_plate="channel_banner_2560x1440.jpg",
        force_live=force_regenerate and bool(custom_banner_prompt.strip() or force_regenerate),
    )
    generate_pure_3d_image(
        prompt=l_prompt,
        output_path=logo_path,
        target_size=(800, 800),
        fallback_plate="channel_logo_800x800.png",
        force_live=force_regenerate and bool(custom_logo_prompt.strip() or force_regenerate),
    )

    return {
        "banner_path": to_portable_path(banner_path),
        "logo_path": to_portable_path(logo_path),
        "seo_description": ch.get("channel_seo_description", ""),
        "channel_keywords": ch.get("channel_keywords", ""),
    }


def _yt_secret_path() -> Path:
    CREDS_DIR.mkdir(parents=True, exist_ok=True)
    return CREDS_DIR / "youtube_client_secret.json"


def _yt_token_path() -> Path:
    CREDS_DIR.mkdir(parents=True, exist_ok=True)
    p = CREDS_DIR / "youtube_oauth_token.json"
    if not p.exists():
        env_tok = os.environ.get("YOUTUBE_OAUTH_TOKEN_JSON", "").strip()
        if not env_tok:
            try:
                import streamlit as st

                if "YOUTUBE_OAUTH_TOKEN_JSON" in st.secrets:
                    env_tok = str(st.secrets["YOUTUBE_OAUTH_TOKEN_JSON"]).strip()
            except Exception:
                pass
        if env_tok:
            p.write_text(env_tok, encoding="utf-8")
    return p


def _yt_redirect_memo_path() -> Path:
    CREDS_DIR.mkdir(parents=True, exist_ok=True)
    return CREDS_DIR / "youtube_last_redirect.txt"


def _parse_google_client_secret() -> Dict[str, Any]:
    p = _yt_secret_path()
    if not p.exists():
        try:
            import streamlit as st

            if "YOUTUBE_CLIENT_SECRET_JSON" in st.secrets:
                p.write_text(str(st.secrets["YOUTUBE_CLIENT_SECRET_JSON"]).strip(), encoding="utf-8")
        except Exception:
            pass
    if p.exists():
        raw = json.loads(p.read_text(encoding="utf-8"))
        block = raw.get("web") or raw.get("installed") or raw
        return {
            "client_id": block.get("client_id", ""),
            "client_secret": block.get("client_secret", ""),
            "redirect_uris": block.get("redirect_uris", ["https://onebillionviews.streamlit.app", "http://localhost:8501"]),
        }
    cid = os.environ.get("YOUTUBE_OAUTH_CLIENT_ID") or os.environ.get("GOOGLE_OAUTH_CLIENT_ID", "")
    csec = os.environ.get("YOUTUBE_OAUTH_CLIENT_SECRET") or os.environ.get("GOOGLE_OAUTH_CLIENT_SECRET", "")
    if cid and csec:
        return {
            "client_id": cid.strip(),
            "client_secret": csec.strip(),
            "redirect_uris": ["https://onebillionviews.streamlit.app", "http://localhost:8501"],
        }
    return {}


def save_youtube_client_secret(raw_bytes: bytes) -> Dict[str, Any]:
    parsed = json.loads(raw_bytes.decode("utf-8"))
    if "web" not in parsed and "installed" not in parsed:
        raise ValueError("Uploaded JSON does not look like a Google OAuth client_secret.json file.")
    _yt_secret_path().write_bytes(raw_bytes)
    return _parse_google_client_secret()


def build_youtube_auth_url(redirect_uri: str = "https://onebillionviews.streamlit.app") -> str:
    cfg = _parse_google_client_secret()
    if not cfg.get("client_id"):
        return ""
    clean_redir = redirect_uri.strip().rstrip("/")
    _yt_redirect_memo_path().write_text(clean_redir, encoding="utf-8")
    params = {
        "client_id": cfg["client_id"],
        "redirect_uri": clean_redir,
        "response_type": "code",
        "scope": "https://www.googleapis.com/auth/youtube.upload https://www.googleapis.com/auth/youtube.readonly",
        "access_type": "offline",
        "prompt": "consent select_account",
        "state": "youtube_channel_connect",
    }
    return "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode(params)


def exchange_youtube_auth_code(code_or_url: str, redirect_uri: str = "") -> Dict[str, Any]:
    cfg = _parse_google_client_secret()
    if not cfg.get("client_id") or not cfg.get("client_secret"):
        raise ValueError("Upload client_secret.json first before exchanging an authorization code.")

    memo_redir = (
        _yt_redirect_memo_path().read_text(encoding="utf-8").strip()
        if _yt_redirect_memo_path().exists()
        else ""
    )
    final_redir = (redirect_uri.strip() or memo_redir or "https://onebillionviews.streamlit.app").rstrip("/")

    clean_code = code_or_url.strip()
    if "code=" in clean_code:
        parsed_q = urllib.parse.parse_qs(urllib.parse.urlparse(clean_code).query)
        if "code" in parsed_q:
            clean_code = parsed_q["code"][0]

    resp = requests.post(
        "https://oauth2.googleapis.com/token",
        data={
            "code": clean_code,
            "client_id": cfg["client_id"],
            "client_secret": cfg["client_secret"],
            "redirect_uri": final_redir,
            "grant_type": "authorization_code",
        },
        timeout=20,
    )
    data = resp.json()
    if resp.status_code != 200 or "access_token" not in data:
        raise RuntimeError(f"Google OAuth token exchange failed: {data}")

    existing = {}
    if _yt_token_path().exists():
        try:
            existing = json.loads(_yt_token_path().read_text(encoding="utf-8"))
        except Exception:
            existing = {}

    token_bundle = {
        "access_token": data["access_token"],
        "refresh_token": data.get("refresh_token") or existing.get("refresh_token", ""),
        "expires_at": (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=int(data.get("expires_in", 3500)))).isoformat(),
        "client_id": cfg["client_id"],
        "client_secret": cfg["client_secret"],
    }

    # Verify which YouTube channel was authorized
    ch_resp = requests.get(
        "https://www.googleapis.com/youtube/v3/channels",
        params={"part": "snippet", "mine": "true"},
        headers={"Authorization": f"Bearer {token_bundle['access_token']}"},
        timeout=15,
    )
    if ch_resp.status_code == 200:
        items = ch_resp.json().get("items", [])
        if items:
            token_bundle["connected_channel_id"] = items[0]["id"]
            token_bundle["connected_channel_title"] = items[0]["snippet"]["title"]
            token_bundle["connected_custom_url"] = items[0]["snippet"].get("customUrl", "")

    _yt_token_path().write_text(json.dumps(token_bundle, indent=2), encoding="utf-8")
    return token_bundle


def get_valid_youtube_access_token() -> str:
    if not _yt_token_path().exists():
        return ""
    tok = json.loads(_yt_token_path().read_text(encoding="utf-8"))
    exp_str = tok.get("expires_at", "")
    needs_refresh = True
    if exp_str:
        try:
            exp_dt = datetime.datetime.fromisoformat(exp_str)
            if exp_dt > datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=2):
                needs_refresh = False
        except Exception:
            needs_refresh = True

    if not needs_refresh and tok.get("access_token"):
        return tok["access_token"]

    if not tok.get("refresh_token"):
        return tok.get("access_token", "")

    cfg = _parse_google_client_secret()
    cid = tok.get("client_id") or cfg.get("client_id", "")
    csec = tok.get("client_secret") or cfg.get("client_secret", "")
    resp = requests.post(
        "https://oauth2.googleapis.com/token",
        data={
            "client_id": cid,
            "client_secret": csec,
            "refresh_token": tok["refresh_token"],
            "grant_type": "refresh_token",
        },
        timeout=20,
    )
    if resp.status_code == 200 and "access_token" in resp.json():
        fresh = resp.json()
        tok["access_token"] = fresh["access_token"]
        tok["expires_at"] = (
            datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=int(fresh.get("expires_in", 3500)))
        ).isoformat()
        _yt_token_path().write_text(json.dumps(tok, indent=2), encoding="utf-8")
        return tok["access_token"]
    return ""


def get_youtube_oauth_status() -> Dict[str, Any]:
    secret_cfg = _parse_google_client_secret()
    has_secret = bool(secret_cfg.get("client_id"))
    if not _yt_token_path().exists():
        return {"has_client_secret": has_secret, "connected": False}
    try:
        tok = json.loads(_yt_token_path().read_text(encoding="utf-8"))
        return {
            "has_client_secret": has_secret,
            "connected": bool(tok.get("refresh_token") or tok.get("access_token")),
            "channel_title": tok.get("connected_channel_title", "TopperLab 3D"),
            "channel_id": tok.get("connected_channel_id", ""),
            "custom_url": tok.get("connected_custom_url", ""),
        }
    except Exception:
        return {"has_client_secret": has_secret, "connected": False}


def save_meta_credentials(page_access_token: str, facebook_page_id: str, instagram_account_id: str) -> Dict[str, str]:
    CREDS_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "page_access_token": page_access_token.strip(),
        "facebook_page_id": facebook_page_id.strip(),
        "instagram_account_id": instagram_account_id.strip(),
    }
    (CREDS_DIR / "meta_credentials.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def load_meta_credentials() -> Dict[str, str]:
    p = CREDS_DIR / "meta_credentials.json"
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {
        "page_access_token": os.environ.get("META_PAGE_ACCESS_TOKEN", ""),
        "facebook_page_id": os.environ.get("FACEBOOK_PAGE_ID", ""),
        "instagram_account_id": os.environ.get("INSTAGRAM_BUSINESS_ACCOUNT_ID", ""),
    }


# ============================================================================
# 4. STEP 2: SYLLABUS / STRATEGY IDEA ENGINE & DUAL SCRIPT + 3D THUMBNAILS
# ============================================================================
def generate_viral_highschool_topics(
    pillar_id: str,
    exam_track: str,
    custom_chapter_query: str = "",
) -> List[Dict[str, str]]:
    pillars_cfg = load_pillars_config()
    pillar = next((p for p in pillars_cfg["pillars"] if p["id"] == pillar_id), pillars_cfg["pillars"][0])
    fallback_topics = pillar["starter_topics"]

    if not custom_chapter_query.strip() and not get_gemini_api_key():
        return fallback_topics

    chapter_clause = (
        f"specifically focused on the chapter/topic '{custom_chapter_query.strip()}'"
        if custom_chapter_query.strip()
        else "covering high-search NCERT, CBSE Board, JEE & NEET pain points"
    )
    prompt = (
        f"You are the head producer of TopperLab 3D (@TopperLab3D), an elite faceless 3D science & exam strategy YouTube channel "
        f"for Indian High-School students ({exam_track}).\n"
        f"Content Pillar: {pillar['name']} — {pillar['description']}\n"
        f"Generate 5 viral, high-CTR faceless video ideas {chapter_clause}.\n"
        f"Return a JSON array of 5 objects with keys: title, exam_track, thumb_hook (max 3 bold words), short_hook (max 3 bold words), why_viral."
    )
    res = call_gemini_json(prompt, fallback_topics)
    return res if isinstance(res, list) and len(res) > 0 else fallback_topics


def _default_gyroscope_scenes(topic_title: str, is_hinglish: bool = False) -> List[Dict[str, Any]]:
    if "gyroscope" in topic_title.lower() or "rotational" in topic_title.lower():
        return [
            {
                "scene_id": 1,
                "headline": "DEFIES GRAVITY?!",
                "concept_takeaway": "Spinning wheel stays horizontal on a needle tip instead of falling",
                "narration": (
                    "Drop a heavy metal wheel balanced on the tip of a thin needle, and gravity slams it straight down in half a second. "
                    "Now spin that exact same wheel at three thousand revolutions per minute—and suddenly it floats sideways in mid-air, seemingly defying gravity. "
                    "Textbooks bury this magic under dry equations, so let us step inside 3D space and actually see the invisible vectors holding it up."
                    if not is_hinglish
                    else "Agar aap ek heavy metal wheel ko patli needle par chhod dein, toh gravity usse turant neeche gira degi. Lekin usi wheel ko 3000 RPM par spin kijiye—aur woh hawa mein horizontal float karne lagta hai! Chaliye 3D space mein dekhte hain ki Torque aur Angular Momentum ise kaise sambhalte hain."
                ),
                "image_3d_prompt": "Photorealistic 8k 3D render of a gleaming brass and neon-cyan gyroscope spinning rapidly balanced horizontally on a steel needle tip inside a dark obsidian physics lab, glowing yellow Angular Momentum vector L and cyan Torque vector tau, bold 3D text 'DEFIES GRAVITY?!', zero human faces.",
                "google_flow_veo_prompt": "Cinematic 8k 3D slow-motion physics simulation: a glowing brass and cyan precision gyroscope wheel spinning rapidly on a sharp needle pivot, orbiting smoothly horizontally in mid-air with luminous golden angular momentum vector arrows, dark obsidian lab, subtle mechanical hum SFX.",
                "fallback_plate": "scene_01_16x9.jpg",
            },
            {
                "scene_id": 2,
                "headline": "TORQUE AT 90°",
                "concept_takeaway": "τ = r × mg points perpendicular to both position r and gravity mg",
                "narration": (
                    "First, freeze the frame and trace the two real forces. Position vector r points straight out along the axle from the pivot, while gravity pulls straight down with force m g. "
                    "When you curl your right-hand fingers from r toward downward gravity, the cross product torque tau equals r cross F shoots horizontally at a perfect ninety-degree angle—not downward!"
                    if not is_hinglish
                    else "Sabse pehle frame ko freeze karke vectors dekhiye. Pivot se bahar ki taraf jaata hai position vector r, aur neeche pull karta hai gravity vector mg. Right-hand rule lagaiye—r cross mg se banne wala Torque vector neeche nahi, balki 90 degree sideways point karta hai!"
                ),
                "image_3d_prompt": "Minimalist 3Blue1Brown meets Veritasium 3D physics stage on matte-black grid: glowing golden position vector r and vertical red force vector mg meeting at pivot, producing perpendicular glowing cyan torque vector tau = r x F at 90 degrees, zero human faces.",
                "google_flow_veo_prompt": "3Blue1Brown style 3D mathematical animation on a dark space grid: a golden vector r and downward red gravity vector mg sweep together to spawn a glowing cyan perpendicular torque arrow at 90 degrees, smooth orbital camera dolly.",
                "fallback_plate": "scene_02_16x9.jpg",
            },
            {
                "scene_id": 3,
                "headline": "PRECESSION LOOP",
                "concept_takeaway": "ΔL = τ · Δt swings the spinning Angular Momentum vector sideways in a circle",
                "narration": (
                    "When the wheel is not spinning, its initial angular momentum L is zero, so that sideways torque simply tips the wheel over. "
                    "But when spinning fast, the wheel already carries a huge horizontal angular momentum vector L. Because torque equals the rate of change of angular momentum, delta L pulls the tip of L sideways—forcing the entire axle to orbit smoothly in a horizontal circle called gyroscopic precession!"
                    if not is_hinglish
                    else "Jab wheel spin nahi kar raha hota, tab Angular Momentum L zero hota hai aur wheel gir jaata hai. Lekin fast spin mein ek bada horizontal vector L maujood hota hai. Sideways torque is L vector ki tip ko lagataar sideways ghumaata hai—jise hum Gyroscopic Precession kehte hain!"
                ),
                "image_3d_prompt": "Photorealistic 8k 3D cutaway simulation inside dark physics lab: a glowing spinning 3D wheel suspended from one end of its axle, orbiting horizontally in a luminous golden circular precession path with cyan dL arrows, zero human faces.",
                "google_flow_veo_prompt": "Photorealistic 3D physics lab simulation: a fast-spinning illuminated wheel hanging from a single cable orbits smoothly in a glowing golden horizontal circle without falling, glowing vector trails tracing the circular precession ring.",
                "fallback_plate": "scene_03_16x9.jpg",
            },
            {
                "scene_id": 4,
                "headline": "4-MARK EXAM RULE",
                "concept_takeaway": "Precession speed Ω = mgr / (Iω) — faster spin ω means slower precession!",
                "narration": (
                    "Here is the exact four-mark JEE and Class 11 takeaway: precession angular speed Omega equals m g r divided by rotational inertia I times spin speed omega. "
                    "Notice the inverse relationship—the faster the wheel spins, the slower and steadier it precesses! Grab the free one-page 3D Rotational Motion formula sheet linked in the description below, and subscribe to TopperLab 3D to see your entire syllabus in 3D."
                    if not is_hinglish
                    else "Ab yaad rakhiye woh 4-mark exam formula: Precession speed Omega barabar hota hai mgr divided by I into omega. Yaani wheel jitna tez spin karega, precession utna slow aur stable hoga! Description mein diye free 1-page 3D Formula Sheet ko abhi download karein aur TopperLab 3D ko subscribe karein."
                ),
                "image_3d_prompt": "Futuristic dark obsidian 3D study desk with a floating luminous holographic 3D blueprint card displaying clean glowing cyan physics diagrams of a gyroscope and rotational inertia ring, crisp 3D header '1-PAGE FORMULA SHEET', zero human faces.",
                "google_flow_veo_prompt": "Sleek futuristic 3D dark glass study desk where a glowing cyan holographic 1-page physics formula blueprint rises and rotates gently in volumetric golden light, crisp 3D vectors.",
                "fallback_plate": "scene_04_16x9.jpg",
            },
        ]

    return [
        {
            "scene_id": 1,
            "headline": "THE 2D TEXTBOOK TRAP",
            "concept_takeaway": f"Why 90% struggle with {topic_title} on flat 2D pages",
            "narration": f"Look at how most students study {topic_title}: staring at flat 2D black-and-white diagrams while trying to memorize disconnected formulas. Within forty-eight hours, brain recall drops below twenty percent. Let us rebuild {topic_title} inside 3D space so your brain locks it in permanently.",
            "image_3d_prompt": f"Dramatic 8k Octane 3D scientific cutaway visualization introducing '{topic_title}' inside a dark obsidian glass laboratory with glowing cyan and golden 3D vectors, zero human faces.",
            "google_flow_veo_prompt": f"Cinematic 8k 3D camera push-in through a dark obsidian STEM lab onto a glowing holographic 3D model illustrating '{topic_title}' with luminous golden energy pathways.",
            "fallback_plate": "scene_01_16x9.jpg",
        },
        {
            "scene_id": 2,
            "headline": "CORE 3D MECHANISM",
            "concept_takeaway": f"Step-by-step 3D vector & structural breakdown of {topic_title}",
            "narration": f"When we isolate the core mechanism of {topic_title} in three dimensions, every cause-and-effect arrow lines up logically. Instead of cramming sign conventions blindly, watch how the primary variables interact along perpendicular 3D axes.",
            "image_3d_prompt": f"3Blue1Brown meets Veritasium 3D mathematical and scientific diagram of '{topic_title}' on a deep matte-black grid with glowing cyan and gold vector arrows, zero human faces.",
            "google_flow_veo_prompt": f"Smooth 3Blue1Brown style 3D orbital camera motion around glowing geometric vectors and molecular/physics mechanisms demonstrating '{topic_title}'.",
            "fallback_plate": "scene_02_16x9.jpg",
        },
        {
            "scene_id": 3,
            "headline": "THE EXAM TRAP",
            "concept_takeaway": "Fixing the #1 negative-marking mistake tested in Boards, JEE & NEET",
            "narration": f"Now watch where ninety percent of exam-takers lose four marks on {topic_title}: they apply the standard shortcut without checking the boundary condition. In 3D, you can immediately spot why that shortcut flips direction under extreme cases.",
            "image_3d_prompt": f"High-contrast 8k 3D split comparison simulation showing the common misconception versus the true 3D physical pathway for '{topic_title}', glowing sapphire and gold highlights, zero human faces.",
            "google_flow_veo_prompt": f"Dynamic 3D laboratory simulation showing glowing golden pathways locking into place to solve the classic exam trap in '{topic_title}'.",
            "fallback_plate": "scene_03_16x9.jpg",
        },
        {
            "scene_id": 4,
            "headline": "3X RECALL SHEET",
            "concept_takeaway": "1-Page 3D Summary + Active Recall Check in Description",
            "narration": f"Test yourself right now without looking back: can you visualize all three stages of {topic_title} with your eyes closed? Download the free one-page 3D visual cheat sheet and revision tracker from the description below, and subscribe to TopperLab 3D for your next chapter.",
            "image_3d_prompt": f"Futuristic dark obsidian 3D study desk with a floating luminous holographic 1-page formula & 3D diagram summary card for '{topic_title}', zero human faces.",
            "google_flow_veo_prompt": "Cinematic slow zoom onto a glowing holographic 3D 1-page revision sheet floating above a dark obsidian desk with golden light particles.",
            "fallback_plate": "scene_04_16x9.jpg",
        },
    ]


def generate_dual_script_and_thumbnails(
    topic_title: str,
    pillar_id: str,
    exam_track: str,
    voice_mode: str,
    visual_theme_key: str,
    scene_count: int = 4,
    custom_thumb_prompt: str = "",
    force_regenerate_thumbs: bool = False,
) -> Dict[str, Any]:
    ch = load_active_channel()
    project_slug = slugify(topic_title)
    project_dir = WORKSPACES_DIR / project_slug
    project_dir.mkdir(parents=True, exist_ok=True)

    voice_cfg = ch["voice_presets"].get(voice_mode, ch["voice_presets"][ch["default_voice_mode"]])
    theme_cfg = ch["visual_themes"].get(visual_theme_key, ch["visual_themes"][ch["default_visual_theme"]])
    is_hinglish = voice_cfg.get("language_code") == "hi-IN"

    default_scenes = _default_gyroscope_scenes(topic_title, is_hinglish=is_hinglish)
    fallback_blueprint = {
        "title_variations": [
            topic_title,
            f"{topic_title.split('—')[0].strip()} — See What 2D Textbooks Hide (3D Breakdown)",
            f"Master {topic_title.split('—')[0].strip()} in 3D | Boards, JEE & NEET Visual Guide",
        ],
        "thumb_hook_3words": "DEFIES GRAVITY?!" if "gyroscope" in topic_title.lower() else "SEE IT IN 3D!",
        "short_hook_3words": "3X MEMORY LOOP" if "memory" in topic_title.lower() or "blank" in topic_title.lower() else "99% MISS THIS!",
        "thumbnail_16x9_prompt": custom_thumb_prompt.strip()
        or (
            f"High-CTR 16:9 3D science YouTube thumbnail in Veritasium and Zack D. Films 3D style for '{topic_title}'. "
            f"{theme_cfg['style_prompt']} Bold 3D yellow impact text in top-left (max 3 words)."
        ),
        "short_cover_9x16_prompt": (
            f"High-retention 9:16 vertical 3D YouTube Short cover for '{topic_title}'. "
            f"{theme_cfg['style_prompt']} Bold 3D yellow-white headline in upper-middle safe zone (max 3 words)."
        ),
        "scenes": default_scenes,
    }

    ai_prompt = (
        f"Create a complete faceless 3D video production blueprint for TopperLab 3D (@TopperLab3D).\n"
        f"Topic: {topic_title}\n"
        f"Target Indian Audience: {exam_track}\n"
        f"Voice Instruction: {voice_cfg['script_instruction']}\n"
        f"Visual Theme: {theme_cfg['style_prompt']}\n"
        f"Number of Scenes: {scene_count} (Scene 1 = Counter-intuitive 3D Hook, middle scenes = 3D step-by-step scientific/memory breakdown + exam trap, final scene = 4-mark summary + CTA to download free 1-Page 3D Formula Sheet in description).\n"
        f"Return JSON with keys:\n"
        f"- title_variations (array of 3 high-CTR student titles)\n"
        f"- thumb_hook_3words (max 3 bold words)\n"
        f"- short_hook_3words (max 3 bold words)\n"
        f"- thumbnail_16x9_prompt (detailed pure 3D prompt, zero human faces)\n"
        f"- short_cover_9x16_prompt (detailed vertical 9:16 3D prompt, zero human faces)\n"
        f"- scenes: array of {scene_count} objects each having keys: scene_id (1..{scene_count}), headline (max 3 words), concept_takeaway, narration (35-55 words spoken script), image_3d_prompt (pure 3D render prompt, zero human faces), google_flow_veo_prompt (8-second cinematic 3D motion prompt for Google Veo 3.1 / Flow)."
    )
    blueprint = call_gemini_json(ai_prompt, fallback_blueprint)
    if not isinstance(blueprint, dict) or not blueprint.get("scenes"):
        blueprint = fallback_blueprint

    plate_cycle = ["scene_01_16x9.jpg", "scene_02_16x9.jpg", "scene_03_16x9.jpg", "scene_04_16x9.jpg"]
    for idx, sc in enumerate(blueprint["scenes"]):
        sc["scene_id"] = idx + 1
        sc.setdefault("fallback_plate", plate_cycle[idx % len(plate_cycle)])

    thumb_path = project_dir / "thumbnail_16x9.jpg"
    short_cover_path = project_dir / "short_cover_9x16.jpg"
    final_t_prompt = custom_thumb_prompt.strip() or blueprint.get("thumbnail_16x9_prompt", fallback_blueprint["thumbnail_16x9_prompt"])

    generate_pure_3d_image(
        prompt=final_t_prompt,
        output_path=thumb_path,
        target_size=(1920, 1080),
        fallback_plate="sample_thumb_16x9.jpg",
        force_live=force_regenerate_thumbs or bool(custom_thumb_prompt.strip()),
    )
    generate_pure_3d_image(
        prompt=blueprint.get("short_cover_9x16_prompt", fallback_blueprint["short_cover_9x16_prompt"]),
        output_path=short_cover_path,
        target_size=(1080, 1920),
        fallback_plate="sample_reel_9x16.jpg",
        force_live=force_regenerate_thumbs,
    )

    pkg = {
        "topic_title": topic_title,
        "pillar_id": pillar_id,
        "exam_track": exam_track,
        "voice_mode": voice_mode,
        "visual_theme_key": visual_theme_key,
        "project_dir": to_portable_path(project_dir),
        "title_variations": blueprint.get("title_variations", fallback_blueprint["title_variations"]),
        "thumb_hook_3words": blueprint.get("thumb_hook_3words", "SEE IT IN 3D!"),
        "short_hook_3words": blueprint.get("short_hook_3words", "3X MEMORY LOOP"),
        "thumbnail_16x9_path": to_portable_path(thumb_path),
        "short_cover_9x16_path": to_portable_path(short_cover_path),
        "thumbnail_16x9_prompt": final_t_prompt,
        "scenes": blueprint["scenes"],
    }
    (project_dir / "topperlab_blueprint.json").write_text(json.dumps(pkg, indent=2, ensure_ascii=False), encoding="utf-8")
    return pkg


# ============================================================================
# 5. STEP 3: FACELESS 3D SCENE RENDERER, CLEAN VOICEOVER & VEO/FLOW STITCHER
# ============================================================================
def _write_fallback_wav(wav_path: Path, duration_sec: float = 12.0) -> float:
    sample_rate = 44100
    n_samples = int(sample_rate * duration_sec)
    wav_path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(wav_path), "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        frames = bytearray()
        for i in range(n_samples):
            env = min(1.0, i / 2000.0, (n_samples - i) / 2000.0)
            val = int(env * 450 * math.sin(2.0 * math.pi * 196.0 * (i / sample_rate)))
            frames.extend(struct.pack("<h", val))
        wf.writeframes(bytes(frames))
    return duration_sec


def _probe_wav_duration(wav_path: Path) -> float:
    try:
        with wave.open(str(wav_path), "rb") as wf:
            return max(3.0, round(wf.getnframes() / float(wf.getframerate()), 2))
    except Exception:
        return 12.0


def synthesize_scene_voiceover(narration: str, out_wav: Path, voice_preset: Dict[str, Any]) -> float:
    out_wav.parent.mkdir(parents=True, exist_ok=True)
    mp3_tmp = out_wav.with_suffix(".mp3")
    ffmpeg_bin = get_ffmpeg_exe()

    try:
        import edge_tts

        async def _run_tts() -> None:
            comm = edge_tts.Communicate(
                text=narration,
                voice=voice_preset.get("edge_voice", "en-IN-PrabhatNeural"),
                rate=voice_preset.get("rate", "+6%"),
                pitch=voice_preset.get("pitch", "+0Hz"),
            )
            await comm.save(str(mp3_tmp))

        asyncio.run(_run_tts())
        if mp3_tmp.exists() and mp3_tmp.stat().st_size > 400:
            subprocess.run(
                [
                    ffmpeg_bin,
                    "-y",
                    "-i",
                    str(mp3_tmp),
                    "-af",
                    "loudnorm=I=-14:TP=-1.5:LRA=11",
                    "-ar",
                    "44100",
                    "-ac",
                    "2",
                    str(out_wav),
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True,
            )
            return _probe_wav_duration(out_wav)
    except Exception:
        pass

    words = max(8, len((narration or "").split()))
    est_sec = round(max(6.0, words / 2.6), 1)
    return _write_fallback_wav(out_wav, duration_sec=est_sec)


def render_faceless_scene_media(
    scene: Dict[str, Any],
    project_dir: Path,
    voice_preset: Dict[str, Any],
    visual_theme_prompt: str,
    force_live_image: bool = False,
    custom_motion_mp4: Path | None = None,
) -> Dict[str, Any]:
    sid = int(scene["scene_id"])
    scenes_dir = project_dir / "scenes"
    scenes_dir.mkdir(parents=True, exist_ok=True)

    img_16x9 = scenes_dir / f"scene_{sid:02d}_16x9.jpg"
    img_9x16 = scenes_dir / f"scene_{sid:02d}_9x16.jpg"
    wav_path = scenes_dir / f"scene_{sid:02d}_voice.wav"
    mp4_16x9 = scenes_dir / f"scene_{sid:02d}_16x9.mp4"
    mp4_9x16 = scenes_dir / f"scene_{sid:02d}_9x16.mp4"

    full_img_prompt = f"{scene.get('image_3d_prompt', '')} {visual_theme_prompt}"
    plate_16x9 = scene.get("fallback_plate", f"scene_{((sid - 1) % 4) + 1:02d}_16x9.jpg")

    generate_pure_3d_image(
        prompt=full_img_prompt,
        output_path=img_16x9,
        target_size=(1920, 1080),
        fallback_plate=plate_16x9,
        force_live=force_live_image,
    )
    # Build vertical 9:16 pure 3D frame (live if key present & forced, else center-fitted from pure 3D render or vertical plate)
    if force_live_image and get_gemini_api_key():
        generate_pure_3d_image(
            prompt=f"Vertical 9:16 composition: {full_img_prompt}",
            output_path=img_9x16,
            target_size=(1080, 1920),
            fallback_plate="sample_reel_9x16.jpg",
            force_live=True,
        )
    else:
        src_for_vert = Image.open(img_16x9)
        _fit_and_save_image(src_for_vert, img_9x16, (1080, 1920))

    dur_sec = synthesize_scene_voiceover(scene["narration"], wav_path, voice_preset)
    ffmpeg_bin = get_ffmpeg_exe()
    frames_total = max(50, int(math.ceil(dur_sec * 25)))

    saved_motion = scenes_dir / f"scene_{sid:02d}_custom_motion.mp4"
    if custom_motion_mp4 and Path(custom_motion_mp4).exists():
        if Path(custom_motion_mp4).resolve() != saved_motion.resolve():
            shutil.copyfile(custom_motion_mp4, saved_motion)

    if saved_motion.exists():
        # Stitch real Google Flow / Veo 3D motion clip looped/trimmed to exact narration duration
        for target_mp4, vf_scale in [
            (mp4_16x9, "scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,fps=25,format=yuv420p"),
            (mp4_9x16, "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,fps=25,format=yuv420p"),
        ]:
            subprocess.run(
                [
                    ffmpeg_bin,
                    "-y",
                    "-stream_loop",
                    "-1",
                    "-i",
                    str(saved_motion),
                    "-i",
                    str(wav_path),
                    "-t",
                    f"{dur_sec:.2f}",
                    "-vf",
                    vf_scale,
                    "-map",
                    "0:v:0",
                    "-map",
                    "1:a:0",
                    "-c:v",
                    "libx264",
                    "-preset",
                    "veryfast",
                    "-pix_fmt",
                    "yuv420p",
                    "-c:a",
                    "aac",
                    "-b:a",
                    "192k",
                    "-shortest",
                    str(target_mp4),
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        scene["motion_source"] = "Google Flow / Veo 3.1 Motion Clip"
    else:
        # Smooth 3D camera push-in (Ken Burns) at 25fps
        for src_img, target_mp4, res_str in [
            (img_16x9, mp4_16x9, "1920x1080"),
            (img_9x16, mp4_9x16, "1080x1920"),
        ]:
            zp_filter = (
                f"zoompan=z='min(zoom+0.0009,1.12)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
                f":d={frames_total}:s={res_str}:fps=25,format=yuv420p"
            )
            subprocess.run(
                [
                    ffmpeg_bin,
                    "-y",
                    "-loop",
                    "1",
                    "-i",
                    str(src_img),
                    "-i",
                    str(wav_path),
                    "-t",
                    f"{dur_sec:.2f}",
                    "-vf",
                    zp_filter,
                    "-c:v",
                    "libx264",
                    "-preset",
                    "veryfast",
                    "-pix_fmt",
                    "yuv420p",
                    "-c:a",
                    "aac",
                    "-b:a",
                    "192k",
                    "-shortest",
                    str(target_mp4),
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        scene["motion_source"] = "3D Camera Push-In (Nano Banana Plate)"

    scene["duration_sec"] = dur_sec
    scene["img_16x9"] = to_portable_path(img_16x9)
    scene["img_9x16"] = to_portable_path(img_9x16)
    scene["audio_wav"] = to_portable_path(wav_path)
    scene["mp4_16x9"] = to_portable_path(mp4_16x9)
    scene["mp4_9x16"] = to_portable_path(mp4_9x16)
    return scene


def stitch_master_videos(project_dir: Path, scenes: List[Dict[str, Any]], short_max_scenes: int = 4) -> Dict[str, Any]:
    renders_dir = resolve_workspace_path(project_dir) / "renders"
    renders_dir.mkdir(parents=True, exist_ok=True)
    ffmpeg_bin = get_ffmpeg_exe()

    # Keep vertical Short/Reel under ~59s (Scene 1 Hook + middle proof if it fits + final CTA scene)
    if len(scenes) >= 2:
        short_scenes = [scenes[0]]
        running = float(scenes[0].get("duration_sec", 15.0)) + float(scenes[-1].get("duration_sec", 15.0))
        for mid in scenes[1:-1]:
            d = float(mid.get("duration_sec", 15.0))
            if running + d <= 59.5 and len(short_scenes) < short_max_scenes - 1:
                short_scenes.append(mid)
                running += d
        short_scenes.append(scenes[-1])
    else:
        short_scenes = scenes

    long_txt = renders_dir / "concat_16x9.txt"
    short_txt = renders_dir / "concat_9x16.txt"
    long_txt.write_text(
        "\n".join(f"file '{resolve_workspace_path(s['mp4_16x9']).resolve().as_posix()}'" for s in scenes) + "\n",
        encoding="utf-8",
    )
    short_txt.write_text(
        "\n".join(f"file '{resolve_workspace_path(s['mp4_9x16']).resolve().as_posix()}'" for s in short_scenes) + "\n",
        encoding="utf-8",
    )

    out_long = renders_dir / "TOPPERLAB_LONG_16x9.mp4"
    out_short = renders_dir / "TOPPERLAB_SHORT_9x16.mp4"

    for list_path, out_mp4 in [(long_txt, out_long), (short_txt, out_short)]:
        subprocess.run(
            [ffmpeg_bin, "-y", "-f", "concat", "-safe", "0", "-i", str(list_path), "-c", "copy", str(out_mp4)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

    return {
        "long_16x9_mp4": to_portable_path(out_long),
        "short_9x16_mp4": to_portable_path(out_short),
        "long_duration_sec": round(sum(float(s.get("duration_sec", 12.0)) for s in scenes), 1),
        "short_duration_sec": round(sum(float(s.get("duration_sec", 12.0)) for s in short_scenes), 1),
    }


def render_full_topperlab_project(blueprint: Dict[str, Any], short_max_scenes: int = 4) -> Dict[str, Any]:
    ch = load_active_channel()
    project_dir = resolve_workspace_path(blueprint["project_dir"])
    voice_mode = blueprint.get("voice_mode", ch["default_voice_mode"])
    theme_key = blueprint.get("visual_theme_key", ch["default_visual_theme"])
    voice_preset = ch["voice_presets"].get(voice_mode, ch["voice_presets"][ch["default_voice_mode"]])
    theme_prompt = ch["visual_themes"].get(theme_key, ch["visual_themes"][ch["default_visual_theme"]])["style_prompt"]

    scenes = blueprint["scenes"]
    for sc in scenes:
        render_faceless_scene_media(sc, project_dir, voice_preset, theme_prompt, force_live_image=False)

    renders = stitch_master_videos(project_dir, scenes, short_max_scenes=short_max_scenes)
    draft_state = {
        **blueprint,
        "project_dir": to_portable_path(project_dir),
        "scenes": scenes,
        "renders": renders,
        "rendered_at": datetime.datetime.now().isoformat(timespec="seconds"),
    }
    (project_dir / "topperlab_draft_state.json").write_text(
        json.dumps(draft_state, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return draft_state


def update_single_faceless_scene(
    draft_state: Dict[str, Any],
    scene_id: int,
    new_narration: str,
    new_3d_prompt: str,
    regenerate_3d_image: bool = False,
    uploaded_motion_bytes: bytes | None = None,
) -> Dict[str, Any]:
    ch = load_active_channel()
    project_dir = resolve_workspace_path(draft_state["project_dir"])
    voice_mode = draft_state.get("voice_mode", ch["default_voice_mode"])
    theme_key = draft_state.get("visual_theme_key", ch["default_visual_theme"])
    voice_preset = ch["voice_presets"].get(voice_mode, ch["voice_presets"][ch["default_voice_mode"]])
    theme_prompt = ch["visual_themes"].get(theme_key, ch["visual_themes"][ch["default_visual_theme"]])["style_prompt"]

    target = next((s for s in draft_state["scenes"] if int(s["scene_id"]) == int(scene_id)), None)
    if not target:
        raise ValueError(f"Scene {scene_id} not found.")

    target["narration"] = new_narration.strip()
    target["image_3d_prompt"] = new_3d_prompt.strip()

    motion_file: Path | None = None
    if uploaded_motion_bytes:
        motion_file = project_dir / "scenes" / f"scene_{int(scene_id):02d}_custom_motion.mp4"
        motion_file.parent.mkdir(parents=True, exist_ok=True)
        motion_file.write_bytes(uploaded_motion_bytes)

    render_faceless_scene_media(
        scene=target,
        project_dir=project_dir,
        voice_preset=voice_preset,
        visual_theme_prompt=theme_prompt,
        force_live_image=regenerate_3d_image,
        custom_motion_mp4=motion_file,
    )
    draft_state["renders"] = stitch_master_videos(project_dir, draft_state["scenes"])
    (project_dir / "topperlab_draft_state.json").write_text(
        json.dumps(draft_state, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return draft_state


# ============================================================================
# 6. STEP 4: STUDENT SEO BUNDLE & LIVE YOUTUBE / META CLOUD SCHEDULER
# ============================================================================
def generate_student_seo_bundle(
    video_title: str,
    exam_track: str,
    scenes: List[Dict[str, Any]],
    resource_links: List[Dict[str, str]],
) -> Dict[str, Any]:
    ch = load_active_channel()
    ch_name = ch["channel_name"]
    ch_handle = ch["channel_handle"]

    link_lines = []
    for item in resource_links:
        lbl = item.get("label", "").strip()
        url = item.get("url", "").strip()
        cat = item.get("category", "")
        if lbl and url:
            icon = "📄" if "PDF" in cat or "Formula" in cat else ("📊" if "Sheet" in cat or "Tracker" in cat else "📚")
            link_lines.append(f"{icon} {lbl}: {url}")
    links_block = "\n".join(link_lines) or "📄 Free 1-Page 3D Formula & Vector Summary Sheet: Coming in Pinned Comment"

    chapters = []
    elapsed = 0.0
    for sc in scenes:
        mm = int(elapsed // 60)
        ss = int(elapsed % 60)
        chapters.append(f"{mm}:{ss:02d} {sc.get('headline', '3D Concept')} — {sc.get('concept_takeaway', '')[:58]}")
        elapsed += float(sc.get("duration_sec", 12.0))
    chapters_block = "\n".join(chapters) if chapters else "0:00 3D Hook & Core Mystery\n0:20 3D Vector Breakdown\n0:45 Exam Trap & 1-Page Sheet"

    hashtags = [
        "#TopperLab3D",
        "#3DScience",
        "#Class12",
        "#Class11",
        "#JEEMains",
        "#NEETUG",
        "#CBSEBoards",
        "#PhysicsIn3D",
        "#StudyStrategy",
        "#ActiveRecall",
    ]
    seo_tags = [
        video_title.lower(),
        "topperlab 3d",
        "3d science animation india",
        "class 11 physics 3d",
        "class 12 ncert 3d",
        "jee mains visual concepts",
        "neet biology 3d",
        "topper study strategy",
        "active recall revision",
    ]

    yt_description = (
        f"{video_title} — Visualized in crystal-clear 3D by {ch_name} ({ch_handle}) for {exam_track}.\n\n"
        f"📥 FREE 1-PAGE FORMULA SHEETS, REVISION TRACKERS & STUDY RESOURCES:\n"
        f"{links_block}\n\n"
        f"⏱️ 3D CHAPTER TIMESTAMPS:\n"
        f"{chapters_block}\n\n"
        f"🔬 Subscribe to {ch_name} ({ch_handle}) — See What 2D Textbooks Can't Show!\n\n"
        f"{' '.join(hashtags)}"
    )

    short_caption = (
        f"{video_title} ⚡🔬\n\n"
        f"Stop memorizing flat 2D diagrams — once you see the 3D vectors, you can never unsee it!\n\n"
        f"📥 Grab the Free 1-Page 3D Formula Sheet & Tracker:\n{links_block}\n\n"
        f"{' '.join(hashtags[:7])}"
    )

    pinned_comment = (
        f"📌 PINNED BY {ch_name.upper()} ({ch_handle}):\n"
        f"Download today's Free 1-Page 3D Formula Sheet & Spaced-Repetition Tracker here 👇\n"
        f"{links_block}\n\n"
        f"Which NCERT / JEE / NEET chapter should we build in 3D next? Drop it in the replies! 👇"
    )

    return {
        "youtube_description": yt_description,
        "short_reel_caption": short_caption,
        "pinned_comment": pinned_comment,
        "hashtags_str": " ".join(hashtags),
        "seo_tags_list": seo_tags,
        "seo_tags_str": ", ".join(seo_tags),
    }


def _get_schedule_db() -> sqlite3.Connection:
    db_path = ROOT_DIR / "workspaces" / "topperlab_schedule.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS publish_queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT,
            scheduled_for_ist TEXT,
            platform TEXT,
            format_type TEXT,
            title TEXT,
            video_path TEXT,
            status TEXT,
            remote_url_or_note TEXT
        )
        """
    )
    conn.commit()
    return conn


def upload_video_to_youtube_api(
    video_path: Path,
    title: str,
    description: str,
    tags: List[str],
    publish_now: bool,
    scheduled_ist_dt: datetime.datetime,
    thumbnail_path: Path | None = None,
) -> Dict[str, Any]:
    access_token = get_valid_youtube_access_token()
    if not access_token:
        return {"ok": False, "error": "YouTube OAuth not connected yet."}

    ist_tz = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
    aware_ist = scheduled_ist_dt.replace(tzinfo=ist_tz)
    utc_dt = aware_ist.astimezone(datetime.timezone.utc)

    status_body: Dict[str, Any] = {
        "selfDeclaredMadeForKids": False,
    }
    if publish_now or utc_dt <= datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=5):
        status_body["privacyStatus"] = "public"
    else:
        status_body["privacyStatus"] = "private"
        status_body["publishAt"] = utc_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    metadata = {
        "snippet": {
            "title": title[:100],
            "description": description[:4900],
            "tags": tags[:20],
            "categoryId": "27",  # Education
            "defaultLanguage": "en-IN",
            "defaultAudioLanguage": "en-IN",
        },
        "status": status_body,
    }

    file_size = video_path.stat().st_size
    init_resp = requests.post(
        "https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json; charset=UTF-8",
            "X-Upload-Content-Length": str(file_size),
            "X-Upload-Content-Type": "video/mp4",
        },
        data=json.dumps(metadata).encode("utf-8"),
        timeout=30,
    )
    if init_resp.status_code not in (200, 201) or "Location" not in init_resp.headers:
        return {"ok": False, "error": f"YouTube upload init HTTP {init_resp.status_code}: {init_resp.text[:280]}"}

    upload_url = init_resp.headers["Location"]
    with video_path.open("rb") as vf:
        put_resp = requests.put(
            upload_url,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Length": str(file_size),
                "Content-Type": "video/mp4",
            },
            data=vf,
            timeout=600,
        )
    if put_resp.status_code not in (200, 201):
        return {"ok": False, "error": f"YouTube binary upload HTTP {put_resp.status_code}: {put_resp.text[:280]}"}

    vid_data = put_resp.json()
    video_id = vid_data.get("id", "")
    thumb_note = ""
    if video_id and thumbnail_path and thumbnail_path.exists():
        mime = "image/jpeg" if thumbnail_path.suffix.lower() in (".jpg", ".jpeg") else "image/png"
        t_resp = requests.post(
            f"https://www.googleapis.com/upload/youtube/v3/thumbnails/set?videoId={video_id}",
            headers={"Authorization": f"Bearer {access_token}", "Content-Type": mime},
            data=thumbnail_path.read_bytes(),
            timeout=60,
        )
        if t_resp.status_code in (200, 201):
            thumb_note = " + Custom 3D Thumbnail Set"
        else:
            thumb_note = " (Verify Phone OTP in YT Studio -> Feature Eligibility to enable API Custom Thumbnails)"

    mode_str = "LIVE ON YOUTUBE" if status_body["privacyStatus"] == "public" else f"CLOUD SCHEDULED ({status_body.get('publishAt')})"
    return {
        "ok": True,
        "video_id": video_id,
        "status": mode_str,
        "url": f"https://youtu.be/{video_id}{thumb_note}",
    }


def upload_reel_to_facebook_api(
    video_path: Path,
    caption: str,
    publish_now: bool,
    scheduled_ist_dt: datetime.datetime,
) -> Dict[str, Any]:
    creds = load_meta_credentials()
    token = creds.get("page_access_token", "").strip()
    page_id = creds.get("facebook_page_id", "").strip()
    if not token or not page_id:
        return {"ok": False, "error": "Meta Page Access Token / Page ID not configured."}

    start_r = requests.post(
        f"https://graph.facebook.com/v21.0/{page_id}/video_reels",
        data={"upload_phase": "start", "access_token": token},
        timeout=30,
    )
    if start_r.status_code != 200 or "video_id" not in start_r.json():
        return {"ok": False, "error": f"FB Reel init failed: {start_r.text[:240]}"}

    s_json = start_r.json()
    vid_id = s_json["video_id"]
    upload_url = s_json["upload_url"]
    file_bytes = video_path.read_bytes()

    up_r = requests.post(
        upload_url,
        headers={
            "Authorization": f"OAuth {token}",
            "offset": "0",
            "file_size": str(len(file_bytes)),
        },
        data=file_bytes,
        timeout=300,
    )
    if up_r.status_code != 200:
        return {"ok": False, "error": f"FB Reel binary upload failed: {up_r.text[:240]}"}

    ist_tz = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
    unix_ts = int(scheduled_ist_dt.replace(tzinfo=ist_tz).timestamp())
    finish_params: Dict[str, Any] = {
        "upload_phase": "finish",
        "access_token": token,
        "video_id": vid_id,
        "description": caption[:2200],
    }
    if not publish_now and unix_ts > int(datetime.datetime.now(datetime.timezone.utc).timestamp()) + 660:
        finish_params["video_state"] = "SCHEDULED"
        finish_params["scheduled_publish_time"] = str(unix_ts)
        status_lbl = "FB CLOUD SCHEDULED"
    else:
        finish_params["video_state"] = "PUBLISHED"
        status_lbl = "LIVE ON FACEBOOK REELS"

    fin_r = requests.post(f"https://graph.facebook.com/v21.0/{page_id}/video_reels", data=finish_params, timeout=45)
    if fin_r.status_code != 200:
        return {"ok": False, "error": f"FB Reel finish failed: {fin_r.text[:240]}"}
    return {"ok": True, "status": status_lbl, "url": f"https://www.facebook.com/reel/{vid_id}"}


def publish_or_schedule_deliverable(
    platform: str,
    format_type: str,
    title: str,
    description_or_caption: str,
    tags: List[str],
    video_path: str,
    scheduled_ist_dt: datetime.datetime,
    publish_now: bool = False,
    thumbnail_path: str | None = None,
    public_mp4_url_for_ig: str = "",
) -> Dict[str, Any]:
    vpath = resolve_workspace_path(video_path)
    tpath = resolve_workspace_path(thumbnail_path) if thumbnail_path else None
    sched_str = scheduled_ist_dt.strftime("%Y-%m-%d %H:%M IST")

    status = "QUEUED_READY_TO_EXPORT"
    note = f"Ready in workspace ({sched_str}) — connect API in Step 1 for auto-upload or use 1-Click Download."

    if platform.startswith("YouTube") and vpath.exists():
        yt_oauth = get_youtube_oauth_status()
        if yt_oauth.get("connected"):
            res = upload_video_to_youtube_api(
                video_path=vpath,
                title=title,
                description=description_or_caption,
                tags=tags,
                publish_now=publish_now,
                scheduled_ist_dt=scheduled_ist_dt,
                thumbnail_path=tpath if "Long" in platform else None,
            )
            if res.get("ok"):
                status = res["status"]
                note = res["url"]
            else:
                status = "API_NOTICE (SAVED LOCALLY)"
                note = res.get("error", "")

    elif platform.startswith("Facebook") and vpath.exists():
        creds = load_meta_credentials()
        if creds.get("page_access_token") and creds.get("facebook_page_id"):
            res = upload_reel_to_facebook_api(vpath, description_or_caption, publish_now, scheduled_ist_dt)
            if res.get("ok"):
                status = res["status"]
                note = res["url"]
            else:
                status = "API_NOTICE (SAVED LOCALLY)"
                note = res.get("error", "")

    elif platform.startswith("Instagram"):
        creds = load_meta_credentials()
        if creds.get("page_access_token") and creds.get("instagram_account_id") and public_mp4_url_for_ig.strip():
            token = creds["page_access_token"].strip()
            ig_id = creds["instagram_account_id"].strip()
            c_resp = requests.post(
                f"https://graph.facebook.com/v21.0/{ig_id}/media",
                data={
                    "media_type": "REELS",
                    "video_url": public_mp4_url_for_ig.strip(),
                    "caption": description_or_caption[:2150],
                    "access_token": token,
                },
                timeout=30,
            )
            if c_resp.status_code == 200 and "id" in c_resp.json():
                creation_id = c_resp.json()["id"]
                status = "IG CONTAINER CREATED"
                note = f"Container {creation_id} queued on Instagram Graph API."
            else:
                status = "API_NOTICE (SAVED LOCALLY)"
                note = f"IG API response: {c_resp.text[:220]}"

    conn = _get_schedule_db()
    conn.execute(
        """
        INSERT INTO publish_queue (created_at, scheduled_for_ist, platform, format_type, title, video_path, status, remote_url_or_note)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            datetime.datetime.now().isoformat(timespec="seconds"),
            sched_str,
            platform,
            format_type,
            title,
            str(vpath),
            status,
            note,
        ),
    )
    conn.commit()
    conn.close()
    return {"platform": platform, "status": status, "scheduled_for": sched_str, "note": note}


def list_publish_queue() -> List[Dict[str, Any]]:
    conn = _get_schedule_db()
    cur = conn.execute(
        "SELECT id, created_at, scheduled_for_ist, platform, format_type, title, status, remote_url_or_note FROM publish_queue ORDER BY id DESC"
    )
    rows = [
        {
            "ID": r[0],
            "Created": r[1],
            "Scheduled (IST)": r[2],
            "Platform": r[3],
            "Format": r[4],
            "Title": r[5],
            "Status": r[6],
            "Live Link / Note": r[7],
        }
        for r in cur.fetchall()
    ]
    conn.close()
    return rows


def fetch_live_youtube_channel_videos(max_results: int = 10) -> List[Dict[str, Any]]:
    """Fetch actual uploaded & cloud-scheduled videos directly from the connected YouTube channel via Data API v3."""
    access_token = get_valid_youtube_access_token()
    if not access_token:
        return []
    headers = {"Authorization": f"Bearer {access_token}"}
    try:
        ch_r = requests.get(
            "https://www.googleapis.com/youtube/v3/channels",
            params={"part": "contentDetails", "mine": "true"},
            headers=headers,
            timeout=15,
        )
        if ch_r.status_code != 200 or not ch_r.json().get("items"):
            return []
        uploads_id = ch_r.json()["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]
        pl_r = requests.get(
            "https://www.googleapis.com/youtube/v3/playlistItems",
            params={"part": "contentDetails", "playlistId": uploads_id, "maxResults": max_results},
            headers=headers,
            timeout=15,
        )
        vid_ids = [it["contentDetails"]["videoId"] for it in pl_r.json().get("items", [])]
        if not vid_ids:
            return []
        v_r = requests.get(
            "https://www.googleapis.com/youtube/v3/videos",
            params={"part": "snippet,status,contentDetails,processingDetails", "id": ",".join(vid_ids)},
            headers=headers,
            timeout=15,
        )
        ist_tz = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
        out = []
        for it in v_r.json().get("items", []):
            vid_id = it["id"]
            st_obj = it.get("status", {})
            cd_obj = it.get("contentDetails", {})
            sn_obj = it.get("snippet", {})
            pub_at = st_obj.get("publishAt", "")
            sched_ist = "Immediate / Public"
            if pub_at:
                try:
                    dt_utc = datetime.datetime.fromisoformat(pub_at.replace("Z", "+00:00"))
                    sched_ist = dt_utc.astimezone(ist_tz).strftime("%Y-%m-%d %I:%M %p IST")
                except Exception:
                    sched_ist = pub_at
            is_short = "#shorts" in sn_obj.get("title", "").lower() or cd_obj.get("duration", "").startswith("PT5")
            out.append(
                {
                    "Video ID": vid_id,
                    "Type": "9:16 Short" if is_short else "16:9 Long-Form",
                    "Title": sn_obj.get("title", ""),
                    "Duration": cd_obj.get("duration", "").replace("PT", ""),
                    "Privacy / Schedule": f"SCHEDULED ({sched_ist})" if pub_at else st_obj.get("privacyStatus", "").upper(),
                    "Custom Thumb": "✅ Yes" if cd_obj.get("hasCustomThumbnail") else "Auto Frame",
                    "Processing": f"{st_obj.get('uploadStatus', '')} ({cd_obj.get('definition', '').upper()})",
                    "Studio Edit URL": f"https://studio.youtube.com/video/{vid_id}/edit",
                }
            )
        return out
    except Exception:
        return []
