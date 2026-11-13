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

from array import array
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
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

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


def load_curriculum_catalog() -> Dict[str, Any]:
    path = CONFIG_DIR / "curriculum_chapters.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"boards": ["CBSE", "ICSE"], "classes": ["Class 10", "Class 9", "Class 8", "Class 11", "Class 12"], "duration_badges": ["6 Mins", "5 Mins", "8 Mins", "10 Mins", "15 Mins"], "curriculum": {}, "booster_modes": {}}


def get_curriculum_subjects(board: str = "CBSE", class_name: str = "Class 10") -> List[str]:
    cat = load_curriculum_catalog().get("curriculum", {})
    b_map = cat.get(board, {}) or next(iter(cat.values()), {})
    c_map = b_map.get(class_name, {}) or next(iter(b_map.values()), {})
    return list(c_map.keys()) or ["Mathematics", "Physics", "Chemistry", "Biology"]


def get_curriculum_chapters(board: str = "CBSE", class_name: str = "Class 10", subject: str = "Mathematics") -> List[str]:
    cat = load_curriculum_catalog().get("curriculum", {})
    b_map = cat.get(board, {}) or next(iter(cat.values()), {})
    c_map = b_map.get(class_name, {}) or next(iter(b_map.values()), {})
    return list(c_map.get(subject, []))


def strip_3d_text(text: str) -> str:
    """Remove all '3D' / '3d' labels from public titles, descriptions, captions, hooks, and hashtags."""
    s = str(text or "")
    if not s:
        return ""
    s = re.sub(r"\(\s*@?TopperLab\s*3[dD]\s*\)", "", s, flags=re.IGNORECASE)
    s = re.sub(r"@TopperLab3[dD]\b", "@TopperLab", s, flags=re.IGNORECASE)
    s = re.sub(r"\bTopperLab\s*3[dD]\b", "TopperLab", s, flags=re.IGNORECASE)
    s = re.sub(r"\(\s*(?:easy\s+|friendly\s+|pure\s+)?3[dD][^)]*\)", "", s, flags=re.IGNORECASE)
    s = re.sub(
        r"\b(?:visualized\s+in\s+(?:crystal[- ]clear\s+)?|explained\s+in\s+|in\s+easy\s+|in\s+friendly\s+|in\s+crystal[- ]clear\s+|as\s+|in\s+)3[dD]\b",
        "",
        s,
        flags=re.IGNORECASE,
    )
    s = re.sub(r"#3[dD][A-Za-z0-9_]*\b", "", s)
    s = re.sub(r"#([A-Za-z0-9_]+?)3[dD]\b", r"#\1", s)
    s = re.sub(r"\b3[dD]\b", "", s)
    cleaned_lines: List[str] = []
    for raw_ln in s.splitlines():
        if "http://" in raw_ln or "https://" in raw_ln:
            # Clean label part before URL while preserving exact URL characters
            m_url = re.search(r"https?://\S+", raw_ln)
            if m_url:
                prefix = re.sub(r"[ \t]{2,}", " ", raw_ln[: m_url.start()]).strip()
                cleaned_lines.append(f"{prefix} {m_url.group(0)}".strip())
                continue
        ln = re.sub(r"[ \t]{2,}", " ", raw_ln)
        ln = re.sub(r"\s+([,.:;!?])", r"\1", ln)
        ln = re.sub(r"—\s*—", "—", ln)
        cleaned_lines.append(ln.strip(" —-|"))
    return "\n".join(cleaned_lines).strip()


def format_syllabus_chapter_title(chapter_name: str, duration_badge: str = "6 Mins") -> str:
    clean_ch = re.sub(r"^\s*\d+[\.\)\-:]\s*", "", strip_3d_text(chapter_name)).strip()
    clean_ch = re.sub(r"\s+in\s+\d+\s*mins?\s+complete\s*$", "", clean_ch, flags=re.IGNORECASE).strip(" —-|")
    dur = (duration_badge or "6 Mins").strip()
    if not clean_ch:
        clean_ch = "Heights and Distances"
    return f"{clean_ch} in {dur} Complete"


def format_booster_video_title(
    chapter_name: str,
    booster_mode_key: str = "toppers_hack",
    generic_topic: str = "",
) -> str:
    if generic_topic and generic_topic.strip():
        return strip_3d_text(generic_topic.strip())
    clean_ch = re.sub(r"^\s*\d+[\.\)\-:]\s*", "", strip_3d_text(chapter_name)).strip() or "Board Exams"
    modes = load_curriculum_catalog().get("booster_modes", {})
    pattern = modes.get(booster_mode_key, {}).get("title_pattern", "{chapter} — Toppers Secret Hack & Exam Tricks")
    return strip_3d_text(pattern.format(chapter=clean_ch))


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

    http_opts = types.HttpOptions(timeout=timeout_ms) if hasattr(types, "HttpOptions") else {"timeout": timeout_ms}
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
                    http_options=http_opts,
                )
            except Exception:
                pass

    key = (api_key_override or get_gemini_api_key()).strip()
    if key:
        return genai.Client(api_key=key, http_options=http_opts)
    return None


SCRIPT_MODEL_PRESETS: Dict[str, str] = {
    "gemini-4-argon": "Gemini 4 Argon ⭐ (Best STEM & JEE/NEET Reasoning)",
    "gemini-4-hydrogen": "Gemini 4 Hydrogen ⚡ (Fastest Gemini 4 Workhorse)",
    "gemini-4-carbon": "Gemini 4 Carbon 🧠 (Deepest Frontier — Auto-Fallback to Argon)",
}

SCRIPT_MODEL_SHORT_NAMES: Dict[str, str] = {
    "gemini-4-argon": "Gemini 4 Argon",
    "gemini-4-hydrogen": "Gemini 4 Hydrogen",
    "gemini-4-carbon": "Gemini 4 Carbon",
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
    for m in (first, "gemini-4-argon", "gemini-4-hydrogen"):
        if m and m not in ordered:
            ordered.append(m)
    return ordered


def check_gemini_api_key_health(api_key: str | None = None, preferred_model: str | None = None) -> Dict[str, Any]:
    runtime_override = os.environ.get("RUNTIME_GEMINI_API_KEY", "").strip()
    effective_override = runtime_override if runtime_override else (None if has_vertex_adc() else (api_key if api_key else None))
    client = build_genai_client(location="global", timeout_ms=12000, api_key_override=effective_override)
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
        # Fast health probe: verify Vertex AI / Gemini 4 live via fast Hydrogen first if Argon is selected,
        # while keeping Argon as primary in call_gemini_json so sidebar load never stalls!
        probe_list = ["gemini-4-hydrogen"] + [m for m in candidates if m != "gemini-4-hydrogen"] if is_vertex else candidates
        last_err = ""
        for probe_model in probe_list:
            try:
                if not is_vertex and hasattr(client, "interactions"):
                    inter = client.interactions.create(model=probe_model, input="Reply OK")
                    if getattr(inter, "output_text", None):
                        short_lbl = SCRIPT_MODEL_SHORT_NAMES.get(requested, requested)
                        return {
                            "ok": True,
                            "code": "ACTIVE",
                            "active_model": requested,
                            "summary": f"{short_lbl} Active (Gemini AI Key)",
                            "detail": f"Verified live ({probe_model}).",
                        }
                resp = client.models.generate_content(model=probe_model, contents="Reply OK")
                if getattr(resp, "text", None):
                    display_model = "gemini-4-argon" if requested == "gemini-4-carbon" and is_vertex else requested
                    short_lbl = SCRIPT_MODEL_SHORT_NAMES.get(display_model, display_model)
                    mode_lbl = "Vertex AI Cloud Credits" if is_vertex else "Gemini AI Studio Key"
                    fallback_note = (
                        " (Carbon auto-routes to Argon on Vertex AI)"
                        if requested == "gemini-4-carbon" and is_vertex
                        else ""
                    )
                    return {
                        "ok": True,
                        "code": "ACTIVE",
                        "active_model": display_model,
                        "summary": f"{short_lbl} + Nano Banana 3D Active ({mode_lbl})",
                        "detail": (
                            f"Verified live on {project_label() if is_vertex else 'AI Studio'}{fallback_note} "
                            f"— {short_lbl} scripts, 3D renders & Veo 3.1 ready!"
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


def _sanitize_drawable_text(text: str) -> str:
    """Keep ASCII + standard Latin/Greek/Math/Arrow BMP symbols supported by DejaVuSans & Segoe UI; strip astral emojis."""
    cleaned = []
    for ch in str(text or ""):
        code = ord(ch)
        if code <= 0x25FF and ch not in ("\ufe0f", "\u200d"):
            cleaned.append(ch)
    return re.sub(r"\s+", " ", "".join(cleaned)).strip()


def _load_studio_font(size: int, weight: str = "bold") -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    if weight == "heavy":
        candidates = [
            r"C:\Windows\Fonts\impact.ttf",
            r"C:\Windows\Fonts\arialbd.ttf",
            r"C:\Windows\Fonts\segoeuib.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        ]
    elif weight == "bold":
        candidates = [
            r"C:\Windows\Fonts\segoeuib.ttf",
            r"C:\Windows\Fonts\arialbd.ttf",
            r"C:\Windows\Fonts\calibrib.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        ]
    else:
        candidates = [
            r"C:\Windows\Fonts\segoeui.ttf",
            r"C:\Windows\Fonts\arial.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        ]
    for fp in candidates:
        if os.path.exists(fp):
            try:
                return ImageFont.truetype(fp, size=size)
            except Exception:
                continue
    return ImageFont.load_default()


def infer_class_badge_label(
    exam_track: str = "",
    topic_title: str = "",
    class_override: str = "",
    subject_override: str = "",
) -> str:
    cls = strip_3d_text(class_override or "").strip().upper()
    if not cls:
        low = f"{exam_track} {topic_title}".lower()
        if "class 10" in low:
            cls = "CLASS 10"
        elif "class 9" in low:
            cls = "CLASS 9"
        elif "class 8" in low:
            cls = "CLASS 8"
        elif "class 12" in low:
            cls = "CLASS 12"
        elif "class 11" in low:
            cls = "CLASS 11"
        else:
            cls = "CLASS 10"

    subj = strip_3d_text(subject_override or "").strip().upper()
    if subj == "COMPUTER SCIENCE & AI":
        subj = "COMPUTER & AI"
    if not subj:
        t_low = f"{topic_title} {exam_track}".lower()
        if any(k in t_low for k in ("trig", "math", "height", "distance", "factorial", "algebra", "geometry", "quadratic", "circle", "triangle", "polynomial", "probability", "statistics", "calculus")):
            subj = "MATHEMATICS"
        elif any(k in t_low for k in ("heart", "dna", "mitosis", "biology", "life process", "cell", "heredity", "reproduc")):
            subj = "BIOLOGY"
        elif any(k in t_low for k in ("sn1", "chemistry", "metal", "calcination", "acid", "carbon", "periodic", "mole")):
            subj = "CHEMISTRY"
        elif any(k in t_low for k in ("memory", "recall", "revision", "blank out", "score 95", "score 98", "topper")):
            subj = "TOPPER HACKS"
        else:
            subj = "PHYSICS"
    return f"{cls} • {subj}"


def _split_hook_two_lines(hook_text: str) -> tuple[str, str]:
    clean = _sanitize_drawable_text(strip_3d_text(hook_text)).upper() or "6 MINS COMPLETE!"
    words = clean.split()
    if len(words) == 1:
        return words[0], "COMPLETE!"
    if len(words) == 2:
        return words[0], words[1]
    best_idx = 1
    best_diff = 999
    for idx in range(1, len(words)):
        l1 = " ".join(words[:idx])
        l2 = " ".join(words[idx:])
        diff = abs(len(l1) - len(l2))
        if diff < best_diff:
            best_diff = diff
            best_idx = idx
    return " ".join(words[:best_idx]), " ".join(words[best_idx:])


def _fit_font_for_width(
    draw: ImageDraw.ImageDraw,
    text: str,
    max_w: int,
    start_size: int,
    min_size: int = 44,
    weight: str = "heavy",
):
    sz = start_size
    while sz >= min_size:
        fnt = _load_studio_font(sz, weight=weight)
        bbox = draw.textbbox((0, 0), text, font=fnt, stroke_width=8)
        if (bbox[2] - bbox[0]) <= max_w:
            return fnt
        sz -= 6
    return _load_studio_font(min_size, weight=weight)


def apply_consistent_topperlab_thumbnail_branding(
    image_path: Path,
    hook_text: str,
    class_badge_text: str = "CLASS 10 • MATHEMATICS",
    sub_tagline: str = "ALL FORMULAS + EXAM HACKS",
    is_vertical: bool = False,
) -> Path:
    """
    Applies 100% consistent, high-CTR TopperLab branding across EVERY video thumbnail:
      - Crimson Red Class Name Pill (e.g., CLASS 10 • MATHEMATICS)
      - Giant Line 1 Heading in Electric Yellow (#FFD600) with thick black stroke
      - Explosive Line 2 Vibrant Red Banner (#DC2626) with bold White pop
      - Electric Yellow outer frame accent while keeping the bright visual model vivid and clear!
    """
    if not image_path.exists():
        return image_path

    base = Image.open(image_path).convert("RGBA")
    W, H = base.size
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    odraw = ImageDraw.Draw(overlay)

    if not is_vertical:
        grad_w = int(W * 0.56)
        for x in range(grad_w):
            ratio = 1.0 - (x / float(grad_w))
            alpha = int(224 * (ratio ** 1.45))
            odraw.line([(x, 0), (x, H)], fill=(10, 18, 38, alpha))
    else:
        grad_h = int(H * 0.44)
        for y in range(grad_h):
            ratio = 1.0 - (y / float(grad_h))
            alpha = int(220 * (ratio ** 1.35))
            odraw.line([(0, y), (W, y)], fill=(10, 18, 38, alpha))

    comp = Image.alpha_composite(base, overlay)
    draw = ImageDraw.Draw(comp)

    draw.rectangle([4, 4, W - 5, H - 5], outline=(255, 214, 0, 255), width=10)

    badge_str = _sanitize_drawable_text(strip_3d_text(class_badge_text)).upper()
    line1, line2 = _split_hook_two_lines(hook_text)
    sub_str = _sanitize_drawable_text(strip_3d_text(sub_tagline)).upper()

    if not is_vertical:
        f_badge = _load_studio_font(38, weight="bold")
        bb = draw.textbbox((0, 0), badge_str, font=f_badge)
        bw, bh = (bb[2] - bb[0]) + 48, (bb[3] - bb[1]) + 28
        bx, by = 56, 52
        draw.rounded_rectangle([bx + 5, by + 6, bx + bw + 5, by + bh + 6], radius=18, fill=(0, 0, 0, 165))
        draw.rounded_rectangle([bx, by, bx + bw, by + bh], radius=18, fill=(220, 38, 38, 255), outline=(255, 255, 255, 255), width=4)
        draw.text((bx + 24, by + 11 - bb[1]), badge_str, font=f_badge, fill=(255, 255, 255, 255))

        max_w = int(W * 0.47)
        f_h1 = _fit_font_for_width(draw, line1, max_w=max_w, start_size=132, min_size=64, weight="heavy")
        b1 = draw.textbbox((0, 0), line1, font=f_h1, stroke_width=10)
        y1 = by + bh + 34
        draw.text((64, y1 + 8 - b1[1]), line1, font=f_h1, fill=(0, 0, 0, 200), stroke_width=10, stroke_fill=(0, 0, 0, 200))
        draw.text((56, y1 - b1[1]), line1, font=f_h1, fill=(255, 214, 0, 255), stroke_width=10, stroke_fill=(9, 13, 22, 255))

        y2_box = y1 + (b1[3] - b1[1]) + 22
        f_h2 = _fit_font_for_width(draw, line2, max_w=max_w - 44, start_size=122, min_size=60, weight="heavy")
        b2 = draw.textbbox((0, 0), line2, font=f_h2, stroke_width=7)
        r_w = (b2[2] - b2[0]) + 56
        r_h = (b2[3] - b2[1]) + 34
        draw.rounded_rectangle([64, y2_box + 8, 64 + r_w, y2_box + r_h + 8], radius=22, fill=(0, 0, 0, 185))
        draw.rounded_rectangle(
            [56, y2_box, 56 + r_w, y2_box + r_h],
            radius=22,
            fill=(220, 38, 38, 255),
            outline=(255, 214, 0, 255),
            width=5,
        )
        draw.text(
            (56 + 28, y2_box + 15 - b2[1]),
            line2,
            font=f_h2,
            fill=(255, 255, 255, 255),
            stroke_width=7,
            stroke_fill=(69, 10, 10, 255),
        )

        y3 = y2_box + r_h + 28
        f_sub = _load_studio_font(31, weight="bold")
        bs = draw.textbbox((0, 0), sub_str, font=f_sub)
        sw, sh = (bs[2] - bs[0]) + 40, (bs[3] - bs[1]) + 22
        if y3 + sh < H - 135:
            draw.rounded_rectangle(
                [56, y3, 56 + sw, y3 + sh],
                radius=14,
                fill=(15, 23, 42, 235),
                outline=(56, 189, 248, 255),
                width=3,
            )
            draw.text((56 + 20, y3 + 9 - bs[1]), sub_str, font=f_sub, fill=(253, 224, 71, 255))

        stamp_txt = "TOPPERLAB • CBSE & ICSE"
        f_st = _load_studio_font(28, weight="bold")
        bst = draw.textbbox((0, 0), stamp_txt, font=f_st)
        stw, sth = (bst[2] - bst[0]) + 36, (bst[3] - bst[1]) + 20
        sy = H - sth - 44
        draw.rounded_rectangle([56, sy, 56 + stw, sy + sth], radius=12, fill=(255, 214, 0, 255), outline=(15, 23, 42, 255), width=3)
        draw.text((56 + 18, sy + 8 - bst[1]), stamp_txt, font=f_st, fill=(15, 23, 42, 255))
    else:
        f_badge = _load_studio_font(38, weight="bold")
        bb = draw.textbbox((0, 0), badge_str, font=f_badge)
        bw, bh = (bb[2] - bb[0]) + 48, (bb[3] - bb[1]) + 26
        bx, by = (W - bw) // 2, 86
        draw.rounded_rectangle([bx, by, bx + bw, by + bh], radius=18, fill=(220, 38, 38, 255), outline=(255, 255, 255, 255), width=4)
        draw.text((bx + 24, by + 11 - bb[1]), badge_str, font=f_badge, fill=(255, 255, 255, 255))

        max_w = W - 110
        f_h1 = _fit_font_for_width(draw, line1, max_w=max_w, start_size=118, min_size=56, weight="heavy")
        b1 = draw.textbbox((0, 0), line1, font=f_h1, stroke_width=9)
        w1 = b1[2] - b1[0]
        x1 = (W - w1) // 2
        y1 = by + bh + 30
        draw.text((x1 + 6, y1 + 7 - b1[1]), line1, font=f_h1, fill=(0, 0, 0, 200), stroke_width=9, stroke_fill=(0, 0, 0, 200))
        draw.text((x1, y1 - b1[1]), line1, font=f_h1, fill=(255, 214, 0, 255), stroke_width=9, stroke_fill=(9, 13, 22, 255))

        y2_box = y1 + (b1[3] - b1[1]) + 20
        f_h2 = _fit_font_for_width(draw, line2, max_w=max_w - 50, start_size=112, min_size=54, weight="heavy")
        b2 = draw.textbbox((0, 0), line2, font=f_h2, stroke_width=7)
        r_w = (b2[2] - b2[0]) + 56
        r_h = (b2[3] - b2[1]) + 32
        rx = (W - r_w) // 2
        draw.rounded_rectangle(
            [rx, y2_box, rx + r_w, y2_box + r_h],
            radius=22,
            fill=(220, 38, 38, 255),
            outline=(255, 214, 0, 255),
            width=5,
        )
        draw.text(
            (rx + 28, y2_box + 14 - b2[1]),
            line2,
            font=f_h2,
            fill=(255, 255, 255, 255),
            stroke_width=7,
            stroke_fill=(69, 10, 10, 255),
        )

    out_rgb = comp.convert("RGB")
    if image_path.suffix.lower() in (".jpg", ".jpeg"):
        out_rgb.save(image_path, format="JPEG", quality=94, optimize=True)
    else:
        out_rgb.save(image_path, format="PNG", optimize=True)
    return image_path


def generate_pure_3d_image(
    prompt: str,
    output_path: Path,
    target_size: tuple[int, int] = (1920, 1080),
    fallback_plate: str = "sample_thumb_16x9.jpg",
    force_live: bool = False,
) -> Path:
    """
    Generates a bright, student-friendly 100% faceless 3D educational model render.
    Uses Vertex AI / Gemini Nano Banana 2.1 when active, otherwise uses
    pre-rendered TopperLab 3D plates in assets/topperlab_3d/.
    """
    if output_path.exists() and not force_live:
        return output_path

    clean_prompt = (
        f"{prompt.strip()} "
        "100% faceless bright colorful 3D educational classroom cutaway model, "
        "easy for a Class 10 school student to understand immediately, clean bright studio lighting, "
        "zero dark alien sci-fi clutter, zero human faces, zero people, zero text or letters inside the 3D scene."
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

    blank = Image.new("RGB", target_size, (224, 242, 254))
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
    tok_p = _yt_token_path()
    if tok_p.exists():
        try:
            tok_raw = json.loads(tok_p.read_text(encoding="utf-8"))
            if tok_raw.get("client_id") and tok_raw.get("client_secret"):
                return {
                    "client_id": tok_raw["client_id"].strip(),
                    "client_secret": tok_raw["client_secret"].strip(),
                    "redirect_uris": ["https://onebillionviews.streamlit.app", "http://localhost:8501"],
                }
        except Exception:
            pass
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
        "scope": (
            "https://www.googleapis.com/auth/youtube "
            "https://www.googleapis.com/auth/youtube.upload "
            "https://www.googleapis.com/auth/youtube.readonly"
        ),
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

    if not custom_chapter_query.strip() and not get_gemini_api_key() and not has_vertex_adc():
        return fallback_topics

    chapter_clause = (
        f"specifically focused on the chapter/topic '{custom_chapter_query.strip()}'"
        if custom_chapter_query.strip()
        else "covering high-search NCERT, CBSE/ICSE Board, JEE & NEET pain points"
    )
    prompt = (
        f"You are the head producer of TopperLab, an elite faceless science, maths & exam strategy YouTube channel "
        f"for Indian High-School students ({exam_track}).\n"
        f"Content Pillar: {pillar['name']} — {pillar['description']}\n"
        f"Generate 5 viral, high-CTR faceless video ideas {chapter_clause}.\n"
        f"STRICT RULE: Do NOT include the word '3D' or '3d' anywhere in title, thumb_hook, short_hook, or why_viral. "
        f"For complete syllabus chapters, format titles like '<Chapter Name> in 6 Mins Complete'. "
        f"For toppers hacks / exam tricks / super memory, make crisp student-friendly titles.\n"
        f"Return a JSON array of 5 objects with keys: title, exam_track, thumb_hook (max 3 bold words), short_hook (max 3 bold words), why_viral."
    )
    res = call_gemini_json(prompt, fallback_topics)
    if isinstance(res, list) and len(res) > 0:
        for item in res:
            if isinstance(item, dict):
                item["title"] = strip_3d_text(item.get("title", ""))
                item["thumb_hook"] = strip_3d_text(item.get("thumb_hook", ""))
                item["short_hook"] = strip_3d_text(item.get("short_hook", ""))
                item["why_viral"] = strip_3d_text(item.get("why_viral", ""))
        return res
    return fallback_topics


def _resolve_voice_preset(ch: Dict[str, Any], voice_mode: str) -> Dict[str, Any]:
    presets = ch.get("voice_presets", {})
    if voice_mode in presets:
        return presets[voice_mode]
    low = (voice_mode or "").lower()
    if "hinglish" in low or "hi-in" in low:
        for k, v in presets.items():
            if v.get("language_code") == "hi-IN":
                return v
    if "female" in low or "teacher" in low:
        for k, v in presets.items():
            if "female" in k.lower() or v.get("gemini_voice") == "Aoede":
                return v
    return presets.get(ch.get("default_voice_mode", ""), next(iter(presets.values())))


def _resolve_visual_theme(ch: Dict[str, Any], visual_theme_key: str) -> Dict[str, Any]:
    themes = ch.get("visual_themes", {})
    if visual_theme_key in themes:
        return themes[visual_theme_key]
    return themes.get(ch.get("default_visual_theme", ""), next(iter(themes.values())))


def _default_gyroscope_scenes(topic_title: str, is_hinglish: bool = False) -> List[Dict[str, Any]]:
    t_low = topic_title.lower()
    if "height" in t_low or "distance" in t_low or "elevation" in t_low:
        return [
            {
                "scene_id": 1,
                "headline": "ELEVATION VS DEPRESSION",
                "concept_takeaway": "Looking UP from eye-level = Elevation; Looking DOWN = Depression (Equal by Z-Rule!)",
                "formula_badge": "tan θ = Perpendicular (Height) / Base (Ground Distance)",
                "quick_tip": "Z-Angle Hack: Angle of Depression from top ALWAYS equals Angle of Elevation from ground!",
                "narration": (
                    "Wait a second—have you ever looked up at the top of a tall lighthouse or a flying kite and wondered how engineers measure its exact height without climbing it?! "
                    "Draw a straight horizontal eye-level line: looking UP gives Angle of Elevation, looking DOWN gives Angle of Depression—and by the Z-rule, both angles are always equal!"
                    if not is_hinglish
                    else "Ruko zara! Kya aapne kabhi kisi oonche lighthouse ya udti patang ko dekh kar socha hai ki bina chadhe uski exact height kaise naapte hain?! Eye-level se upar dekho toh Angle of Elevation, neeche dekho toh Angle of Depression—aur Z-rule se dono hamesha barabar hote hain!"
                ),
                "image_3d_prompt": "Bright sunny Pixar-style 3D classroom geometry tabletop model: a cheerful red-and-white striped coastal lighthouse on a green cliff overlooking a small yellow boat on calm blue water, crisp yellow horizontal eye-level beam and a vivid red diagonal line-of-sight forming a clear right-angled triangle, warm sunlit sky backdrop, zero text, zero faces.",
                "google_flow_veo_prompt": "Bright colorful Pixar-style 3D classroom model of a red-and-white lighthouse and boat showing yellow horizontal eye-level ray and red diagonal sight ray forming a crisp right triangle.",
                "fallback_plate": "scene_01_16x9.jpg",
            },
            {
                "scene_id": 2,
                "headline": "30-45-60 MAGIC RATIOS",
                "concept_takeaway": "95% of Class 10 Board questions use ONLY tan 30°, tan 45°, and tan 60°!",
                "formula_badge": "tan 30° = 1/√3   |   tan 45° = 1   |   tan 60° = √3",
                "quick_tip": "1-Second 45° Hack: Whenever angle is 45°, Tower Height = Ground Shadow Length instantly!",
                "narration": (
                    "Here is the coolest Class 10 Maths secret: ninety-five percent of Heights and Distances questions need just THREE values! "
                    "Tan thirty is one over root three, tan forty-five is one, and tan sixty is root three! "
                    "Spot forty-five degrees in an MCQ? Boom—height and ground shadow are immediately equal in one second flat!"
                    if not is_hinglish
                    else "Ab suniye Class 10 Maths ka sabse bada secret: ninety-five percent board sawalon mein sirf TEEN values lagti hain! Tan thirty hota hai one by root three, tan forty-five hota hai one, aur tan sixty hota hai root three! Jahan 45 degree dikhe—height aur shadow turant barabar!"
                ),
                "image_3d_prompt": "Vibrant sunny 3D school maths tabletop model: a bright red clock tower standing vertically on a neat green courtyard board with three color-coded yellow, blue, and emerald right-triangle beams touching three ground pegs at short, medium, and long shadow distances, bright Pixar educational lighting, zero text, zero faces.",
                "google_flow_veo_prompt": "Sunny colorful 3D school geometry model of a red clock tower casting three distinct color-coded triangle rays onto ground pegs.",
                "fallback_plate": "scene_02_16x9.jpg",
            },
            {
                "scene_id": 3,
                "headline": "TWO-POINT TOWER HACK",
                "concept_takeaway": "Walking closer from 30° to 60°? Distance walked is ALWAYS twice the remaining base!",
                "formula_badge": "d = h (cot 30° − cot 60°)  ⇒  h = (d × √3) / 2",
                "quick_tip": "30° → 60° Topper Trick: Walked 40m closer? Remaining base is half (20m), Height = 20√3 m!",
                "narration": (
                    "Now watch the famous five-mark board question where someone walks closer to a tower and the angle jumps from thirty degrees to sixty degrees! "
                    "Don't waste five minutes solving long equations—when thirty becomes sixty, the remaining distance to the base is ALWAYS exact half of what you walked, and height is half-walked times root three!"
                    if not is_hinglish
                    else "Ab dekhiye woh famous five-mark board question jahan tower ke paas chalne par angle thirty degree se sixty degree ho jata hai! Lambe equations mein time mat gawaiye—jab 30 se 60 bane, bacha hua base hamesha chali gayi doori ka aadha hota hai!"
                ),
                "image_3d_prompt": "Crisp colorful 3D classroom demonstration on a sunlit desk: a tall royal-blue communication tower on the right with two bright yellow milestone pins on a straight road moving closer to the tower base, connected by clean red and emerald diagonal beams forming nested right triangles, zero text, zero faces.",
                "google_flow_veo_prompt": "Smooth camera glide along a bright 3D tabletop model showing two road milestone markers approaching a royal-blue tower with nested red and green triangle rays.",
                "fallback_plate": "scene_03_16x9.jpg",
            },
            {
                "scene_id": 4,
                "headline": "#1 BOARD EXAM TRAP!",
                "concept_takeaway": "When observer height is given, ALWAYS add eye-height to triangle height at the end!",
                "formula_badge": "Total Building Height (H) = Triangle Height (h) + Observer Height",
                "quick_tip": "Full-Marks Checklist: √3 = 1.732  •  Add boy's height  •  Write 'metres' unit at the end!",
                "narration": (
                    "Hold on—don't lose your final mark to the number-one board exam trap! "
                    "Whenever a question gives a student's height, like one point five metres, your triangle sits at eye level—so ALWAYS add that one point five metres at the end! "
                    "Download the free one-page Formula and Shortcut Sheet below, and subscribe for the next chapter!"
                    if not is_hinglish
                    else "Ruko—board exam ke number-one trap mein mat phasna! Jab bhi sawal mein ladke ki height di ho, jaise 1.5 metre, toh triangle eye-level se banta hai—isliye aakhir mein 1.5 metre jodna mat bhoolna! Neeche description se free 1-page Formula Sheet download karein aur subscribe karein!"
                ),
                "image_3d_prompt": "Cheerful sunlit 3D classroom model: a colorful miniature viewing stand on the left facing a tall yellow-and-red apartment tower on the right, showing a clear elevated horizontal green platform line and a bright golden star trophy on the desk, Pixar educational style, zero text, zero faces.",
                "google_flow_veo_prompt": "Cheerful sunlit 3D classroom model showing an elevated viewing stand, apartment tower right-triangle beam, and golden star trophy.",
                "fallback_plate": "scene_04_16x9.jpg",
            },
        ]

    if "gyroscope" in t_low or "rotational" in t_low or "bicycle" in t_low or "wheel" in t_low:
        return [
            {
                "scene_id": 1,
                "headline": "CYCLE WHEEL MYSTERY!",
                "concept_takeaway": "A fast-spinning bicycle wheel stays upright on one rope instead of falling!",
                "formula_badge": "Angular Momentum (L) = I × ω  (Mass Spread × Spin Speed)",
                "quick_tip": "Try it in class: Stationary cycle wheel falls instantly — spinning wheel balances!",
                "narration": (
                    "Hold on—imagine hanging a real bicycle wheel from just one rope on one side of its axle! "
                    "If the wheel isn't spinning, boom—gravity slams it straight down! "
                    "But give that exact same cycle wheel a super-fast spin... and wait—why is it floating sideways in mid-air without falling?! Let's unlock the secret!"
                    if not is_hinglish
                    else "Ruko zara! Socho agar aap ek normal cycle ke wheel ko sirf ek side ki rassi se latka dein! Bina spin kiye chhodoge, toh dhadam se neeche girega! Lekin usi wheel ko zor se spin kijiye... arey wah—yeh hawa mein seedha kaise tair raha hai?! Chaliye iska secret dekhte hain!"
                ),
                "image_3d_prompt": "Bright sunny Pixar-style 3D classroom tabletop demonstration: a colorful red-and-yellow school bicycle wheel spinning fast while hanging horizontally from one bright white rope attached to one side of its axle, bold yellow 3D spin arrows around the tire and a bright blue balance arrow along the axle, warm sky-blue classroom background, super clear for Class 10 students, zero text, zero faces.",
                "google_flow_veo_prompt": "Bright colorful Pixar-style 3D science classroom model: a red and yellow bicycle wheel hanging from a single rope spins rapidly and glides smoothly in a horizontal circle without falling, bright yellow and blue 3D arrows.",
                "fallback_plate": "scene_01_16x9.jpg",
            },
            {
                "scene_id": 2,
                "headline": "DOOR & SPANNER RULE",
                "concept_takeaway": "Turning effect (Torque) = Force × Distance from the hinge or pivot!",
                "formula_badge": "Torque (τ) = Force (F) × Perpendicular Distance (r)",
                "quick_tip": "Board Exam Hack: Door handles are placed FAR from hinges so small push gives HUGE Torque!",
                "narration": (
                    "First, think about pushing your heavy classroom door! Why is the handle always on the far edge—never right next to the hinges? "
                    "Because turning power, called Torque, equals Force times Distance! "
                    "On our cycle wheel, gravity pulls down at a distance from the rope—creating a sideways twist instead of a straight drop!"
                    if not is_hinglish
                    else "Sabse pehle apne classroom ke darwaze ko socho! Handle hamesha kabze se door kyun laga hota hai? Kyunki ghumane wali taqat—yaani Torque—hota hai Force guna Distance! Cycle wheel par bhi gravity rassi se thodi door neeche kheenchti hai, jo wheel ko sideways twist deti hai!"
                ),
                "image_3d_prompt": "Friendly colorful 3D classroom comparison model on a bright clean desk: a bright wooden toy door with hinges and a yellow spanner turning a large silver nut, vivid green Distance arrow (r) and red Push Force arrow (F) creating a bright golden turning arrow, sunlit studio backdrop, zero text, zero faces.",
                "google_flow_veo_prompt": "Colorful 3D educational classroom animation: a bright yellow spanner turns a bolt easily when pushed at the long handle end, glowing red force arrow and green distance arrow.",
                "fallback_plate": "scene_02_16x9.jpg",
            },
            {
                "scene_id": 3,
                "headline": "SIDEWAYS STEERING!",
                "concept_takeaway": "Spin + Gravity Twist steers the wheel smoothly in a horizontal circle!",
                "formula_badge": "Change in Spin Direction (ΔL) = Torque (τ) × Time (Δt)",
                "quick_tip": "Right-Hand Thumb Trick: Curl fingers with wheel spin → Your thumb points along the axle!",
                "narration": (
                    "Here comes the magic moment! When you ride a bicycle fast, spinning wheels resist tipping over! "
                    "Instead of letting gravity knock the wheel down, that sideways Torque gently steers the spinning axle around in a smooth horizontal merry-go-round circle! "
                    "Scientists call this cool circular glide precession!"
                    if not is_hinglish
                    else "Ab dekhiye asli jaadu! Jaise chalti hui cycle kabhi nahi girti, waise hi fast spinning wheel neeche girne se mana kar deta hai! Sideways Torque us ghoomte hue axle ko gol-gol horizontal circle mein steer karta rehta hai—jise kehte hain Precession!"
                ),
                "image_3d_prompt": "Bright colorful Kurzgesagt-meets-Pixar 3D classroom model: a glossy blue-and-yellow spinning bicycle wheel and a colorful toy spinning top orbiting smoothly along a dotted golden circular path above a bright wooden lab table, clear red and yellow 3D directional arrows, sunny sky backdrop, zero text, zero faces.",
                "google_flow_veo_prompt": "Sunny colorful 3D classroom model: a spinning blue-and-yellow bicycle wheel and colorful spinning top trace a smooth golden circular path above a wooden table.",
                "fallback_plate": "scene_03_16x9.jpg",
            },
            {
                "scene_id": 4,
                "headline": "FASTER SPIN = STEADIER!",
                "concept_takeaway": "Faster wheel spin (ω) keeps your cycle & gyroscope super steady — 4 Marks Locked!",
                "formula_badge": "Balance Rule: Faster Spin (↑ ω) → Slower Wobble (↓ Ω)",
                "quick_tip": "Topper Shortcut: Heavy rim + Fast spin = Maximum stability (Used in satellites & bikes)!",
                "narration": (
                    "Boom—here is your guaranteed exam takeaway! The faster a wheel spins, and the heavier its outer tire rim, the steadier it stays! "
                    "That's the exact same science keeping your bicycle upright and spacecraft pointed straight! "
                    "Grab the free one-page Formula and Hack Sheet in the description below, and hit subscribe for your next chapter!"
                    if not is_hinglish
                    else "Boom—ab lock kar lijiye pakke exam marks! Wheel jitna tez ghoomega aur uska bahari rim jitna bhaari hoga, balance utna hi rock-solid rahega! Yahi science aapki cycle aur satellites dono ko seedha rakhti hai! Description se free 1-page Formula Sheet download karein aur TopperLab ko subscribe karein!"
                ),
                "image_3d_prompt": "Bright cheerful 3D student study desk in sunlit classroom: a miniature colorful 3D bicycle model, a spinning toy top, a golden star trophy, and an open colorful 3D science model kit with neat color-coded arrows, warm inviting Pixar educational style, zero text, zero faces.",
                "google_flow_veo_prompt": "Cheerful sunlit 3D student desk with a miniature spinning bicycle wheel model, colorful magnets, and a golden trophy rotating gently.",
                "fallback_plate": "scene_04_16x9.jpg",
            },
        ]

    clean_core = strip_3d_text(topic_title.split("—")[0].replace("Complete", "").strip())
    return [
        {
            "scene_id": 1,
            "headline": "REAL-LIFE HOOK!",
            "concept_takeaway": f"Understand {clean_core} using an everyday real-life classroom model!",
            "formula_badge": f"Core Rule: {clean_core[:44]}",
            "quick_tip": "Visual Memory Trick: Picture the real-life object first — never cram blind definitions!",
            "narration": f"Wait a second! Have you ever wondered why {clean_core} confuses so many students in boring black-and-white textbook pages? Once you see how it works in real life, every single formula clicks in ten seconds flat! Let's break down the whole chapter step by step!",
            "image_3d_prompt": f"Bright colorful Pixar-style 3D classroom tabletop cutaway model illustrating '{topic_title}' using everyday real-life student objects and bold red, yellow, and blue 3D arrows, sunny sky-blue backdrop, zero text, zero faces.",
            "google_flow_veo_prompt": f"Bright colorful 3D classroom model camera zoom onto an everyday real-life demonstration of '{topic_title}'.",
            "fallback_plate": "scene_01_16x9.jpg",
        },
        {
            "scene_id": 2,
            "headline": "CORE LAWS & FORMULAS",
            "concept_takeaway": f"Step-by-step visual breakdown of {clean_core}",
            "formula_badge": "Master Formula: Direct Cause (Red) → Output (Yellow)",
            "quick_tip": "Board Exam Tip: Always draw neat labelled diagrams in your answer sheet for full marks!",
            "narration": f"Look closely at our classroom model! When we open it up from the side, every part connects like simple building blocks. Follow the bright yellow arrow from start to finish—zero scary jargon, just pure common sense!",
            "image_3d_prompt": f"Vibrant well-lit 3D school science lab cutaway model of '{topic_title}' on a clean bright desk, primary-colored red, yellow, and royal-blue parts sliced open clearly, zero text, zero faces.",
            "google_flow_veo_prompt": f"Smooth orbital 3D camera around a colorful classroom model demonstrating '{topic_title}'.",
            "fallback_plate": "scene_02_16x9.jpg",
        },
        {
            "scene_id": 3,
            "headline": "#1 BOARD EXAM TRAP!",
            "concept_takeaway": "Spot and fix the #1 silly mistake students make in the exam hall!",
            "formula_badge": "Check Units & +/- Signs Before Final Answer!",
            "quick_tip": "Topper Hack: Circle the asked unit in the question before writing your formula!",
            "narration": f"Hold on—here is where ninety percent of students lose easy marks in the exam hall! They rush the sign or mix up the two cases. Compare the green right setup with the red mistake—now you will never fall for that trap again!",
            "image_3d_prompt": f"Bright colorful 3D side-by-side classroom model comparing the wrong vs right setup for '{topic_title}' using vivid emerald green and crimson red 3D indicators on a sunny tabletop, zero text, zero faces.",
            "google_flow_veo_prompt": f"Colorful 3D classroom demonstration locking bright green parts together for '{topic_title}'.",
            "fallback_plate": "scene_03_16x9.jpg",
        },
        {
            "scene_id": 4,
            "headline": "COMPLETE RECAP!",
            "concept_takeaway": "Rapid Formula Recap + Free 1-Page Summary Sheet in Description!",
            "formula_badge": "1-3-7 Recall Rule: Revise Today • Day 3 • Day 7",
            "quick_tip": "Quick Test: Pause for 3 seconds and recall all key formulas with your eyes closed!",
            "narration": f"Awesome job! Close your eyes for two seconds—can you recall every core formula clearly? Boom, that means your brain just locked in full marks! Download the free one-page Formula and Quick-Tip Sheet linked below, and subscribe to TopperLab!",
            "image_3d_prompt": f"Cheerful sunlit 3D student desk with a colorful miniature 3D science model of '{topic_title}', a bright golden star trophy, and colourful study markers, Pixar educational style, zero text, zero faces.",
            "google_flow_veo_prompt": "Bright cheerful 3D student desk with miniature science models and a golden star trophy.",
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
    target_class_label: str = "Class 10",
    target_subject_label: str = "Mathematics",
    selected_board: str = "CBSE",
    selected_chapter: str = "",
    video_category: str = "syllabus_chapter",
    duration_badge: str = "6 Mins",
) -> Dict[str, Any]:
    ch = load_active_channel()
    topic_title = strip_3d_text(topic_title)
    project_slug = slugify(topic_title)
    project_dir = WORKSPACES_DIR / project_slug
    project_dir.mkdir(parents=True, exist_ok=True)

    voice_cfg = _resolve_voice_preset(ch, voice_mode)
    theme_cfg = _resolve_visual_theme(ch, visual_theme_key)
    is_hinglish = voice_cfg.get("language_code") == "hi-IN"
    class_badge_text = infer_class_badge_label(
        exam_track=exam_track,
        topic_title=topic_title,
        class_override=target_class_label,
        subject_override=target_subject_label,
    )

    clean_chapter = strip_3d_text(selected_chapter).strip()
    if not clean_chapter:
        clean_chapter = re.sub(r"\s+in\s+\d+\s*mins?\s+complete.*$", "", topic_title, flags=re.IGNORECASE).split("—")[0].strip()

    default_scenes = _default_gyroscope_scenes(topic_title, is_hinglish=is_hinglish)
    is_syllabus = video_category == "syllabus_chapter"
    dur_upper = (duration_badge or "6 Mins").strip().upper()
    default_hook = f"{dur_upper} COMPLETE!" if is_syllabus else "TOPPER HACK!"
    fallback_blueprint = {
        "title_variations": [
            topic_title,
            f"{clean_chapter} in {duration_badge} Complete | {selected_board} {target_class_label} {target_subject_label}",
            f"{clean_chapter} One Shot — All Formulas, Shortcuts & Board Questions",
        ]
        if is_syllabus
        else [
            topic_title,
            f"{clean_chapter} — Toppers Secret Hack & 5-Second Exam Shortcuts",
            f"How Toppers Master {clean_chapter} Without Cramming | {selected_board} {target_class_label}",
        ],
        "thumb_hook_3words": default_hook,
        "short_hook_3words": f"{clean_chapter[:16].upper()}!" if len(clean_chapter) <= 16 else "EXAM SHORTCUT!",
        "thumb_sub_tagline": "ALL FORMULAS + EXAM HACKS" if is_syllabus else "TOPPERS SECRET SHORTCUT",
        "thumbnail_16x9_prompt": custom_thumb_prompt.strip()
        or (
            f"Bright, exciting, colorful Pixar-style 16:9 3D classroom educational model for '{clean_chapter}' ({target_subject_label}) positioned prominently on the RIGHT half of the frame, "
            f"leaving clean sunlit sky-blue studio space on the left side for title overlay. "
            f"{theme_cfg['style_prompt']} Everyday relatable objects a {target_class_label} student loves, vivid red, yellow, and royal-blue parts, zero text inside the raw 3D render."
        ),
        "short_cover_9x16_prompt": (
            f"Bright, exciting vertical 9:16 3D classroom educational model for '{clean_chapter}' ({target_subject_label}) positioned in the lower-center two-thirds of the frame, "
            f"leaving clean studio space at the top for headline overlay. {theme_cfg['style_prompt']} Zero text inside the raw 3D render."
        ),
        "scenes": default_scenes,
    }

    mode_brief = (
        f"FOUNDATION COMPLETE SYLLABUS CHAPTER VIDEO ('{topic_title}'): Cover the ENTIRE {selected_board} {target_class_label} {target_subject_label} chapter '{clean_chapter}' systematically from start to finish across {scene_count} crisp scenes: "
        f"(1) Everyday real-life hook & core chapter intuition, (2) Core concepts, theorems/laws & visual model, (3) Must-know formulas & #1 high-scoring numerical/board shortcut, and (4) #1 exam-hall mistake trap + complete chapter rapid recap."
        if is_syllabus
        else f"POST-FOUNDATION BOOSTER VIDEO ({video_category.upper()} — '{topic_title}'): Deliver ultra-actionable topper study hacks, 5-second exam shortcuts, sign-convention tricks, and super-memory mnemonics for {selected_board} {target_class_label} {target_subject_label} ('{clean_chapter}')."
    )

    ai_prompt = (
        f"Create an exciting, super-clear faceless educational video blueprint for TopperLab.\n"
        f"Topic Title: {topic_title}\n"
        f"Board / Class / Subject / Chapter: {selected_board} • {target_class_label} • {target_subject_label} • {clean_chapter}\n"
        f"Mission: {mode_brief}\n"
        f"Expressive Narration Style: {voice_cfg['script_instruction']}\n"
        f"Visual Model Style (for image_3d_prompt ONLY — NO dark sci-fi!): {theme_cfg['style_prompt']}\n"
        f"Number of Scenes: {scene_count}\n"
        f"CRITICAL RULES:\n"
        f"1. STRICTLY FORBIDDEN: NEVER write the word '3D' or '3d' anywhere in `title_variations`, `thumb_hook_3words`, `short_hook_3words`, `thumb_sub_tagline`, `headline`, `concept_takeaway`, `formula_badge`, `quick_tip`, or `narration`! (Only use 3D visual rendering terms inside `image_3d_prompt` and `google_flow_veo_prompt`).\n"
        f"2. Every `image_3d_prompt` MUST describe bright, colorful, everyday classroom/real-life visual models (lighthouses, towers, bicycles, cricket balls, magnets, batteries, prisms, water pipes, heart models, globes, geometry blocks) on a bright studio desk — NEVER dark sci-fi labs, ZERO human faces, and ZERO text/letters inside the raw image.\n"
        f"3. Every `narration` (38–52 words) MUST be super expressive, lively, conversational, with questions ('Wait—why does...?!'), exclamations, and everyday analogies — NEVER flat textbook monotone!\n"
        f"4. Every scene MUST include an accurate syllabus `formula_badge` (exact equation/law/rule for '{clean_chapter}', max 52 chars) AND a punchy `quick_tip` (shortcut, mnemonic, or board exam hack, max 68 chars) that will fly in and fly out on screen!\n"
        f"Return JSON with keys:\n"
        f"- title_variations (array of 3 clean student titles — first one matching '{topic_title}', ZERO '3D' text)\n"
        f"- thumb_hook_3words (2 to 3 punchy words for the Yellow+Red thumbnail heading, e.g. '{default_hook}' or '5-SEC TRIG HACK!')\n"
        f"- short_hook_3words (2 to 3 punchy words for 9:16 cover, ZERO '3D' text)\n"
        f"- thumb_sub_tagline (3 to 5 words, e.g. 'ALL FORMULAS + EXAM HACKS', ZERO '3D' text)\n"
        f"- thumbnail_16x9_prompt (bright classroom 3D model positioned on RIGHT half of 16:9 frame, clean left side, zero raw text, zero faces)\n"
        f"- short_cover_9x16_prompt (bright classroom 3D model positioned in lower-center of 9:16 frame, clean top area, zero raw text, zero faces)\n"
        f"- scenes: array of {scene_count} objects with keys: scene_id, headline (max 3 words, no '3D'), concept_takeaway (max 72 chars, no '3D'), formula_badge (max 52 chars, no '3D'), quick_tip (max 68 chars, no '3D'), narration (38-52 expressive spoken words, no '3D'), image_3d_prompt, google_flow_veo_prompt."
    )
    blueprint = call_gemini_json(ai_prompt, fallback_blueprint)
    if not isinstance(blueprint, dict) or not blueprint.get("scenes"):
        blueprint = fallback_blueprint

    clean_vars = [strip_3d_text(t) for t in blueprint.get("title_variations", fallback_blueprint["title_variations"]) if strip_3d_text(t)]
    if not clean_vars or clean_vars[0].lower() != topic_title.lower():
        clean_vars = [topic_title] + [v for v in clean_vars if v.lower() != topic_title.lower()]
    blueprint["title_variations"] = clean_vars[:3]

    plate_cycle = ["scene_01_16x9.jpg", "scene_02_16x9.jpg", "scene_03_16x9.jpg", "scene_04_16x9.jpg"]
    for idx, sc in enumerate(blueprint["scenes"]):
        sc["scene_id"] = idx + 1
        sc.setdefault("fallback_plate", plate_cycle[idx % len(plate_cycle)])
        def_sc = default_scenes[idx % len(default_scenes)]
        sc["headline"] = strip_3d_text(sc.get("headline", "")) or def_sc["headline"]
        sc["concept_takeaway"] = strip_3d_text(sc.get("concept_takeaway", "")) or def_sc["concept_takeaway"]
        sc["formula_badge"] = strip_3d_text(sc.get("formula_badge", "")) or def_sc["formula_badge"]
        sc["quick_tip"] = strip_3d_text(sc.get("quick_tip", "")) or def_sc["quick_tip"]
        sc["narration"] = strip_3d_text(sc.get("narration", "")) or def_sc["narration"]

    raw_thumb_16x9 = project_dir / "thumbnail_16x9_raw.jpg"
    raw_short_9x16 = project_dir / "short_cover_9x16_raw.jpg"
    thumb_path = project_dir / "thumbnail_16x9.jpg"
    short_cover_path = project_dir / "short_cover_9x16.jpg"
    final_t_prompt = custom_thumb_prompt.strip() or blueprint.get("thumbnail_16x9_prompt", fallback_blueprint["thumbnail_16x9_prompt"])

    generate_pure_3d_image(
        prompt=final_t_prompt,
        output_path=raw_thumb_16x9,
        target_size=(1920, 1080),
        fallback_plate="sample_thumb_16x9.jpg",
        force_live=force_regenerate_thumbs or bool(custom_thumb_prompt.strip()) or not raw_thumb_16x9.exists(),
    )
    generate_pure_3d_image(
        prompt=blueprint.get("short_cover_9x16_prompt", fallback_blueprint["short_cover_9x16_prompt"]),
        output_path=raw_short_9x16,
        target_size=(1080, 1920),
        fallback_plate="sample_reel_9x16.jpg",
        force_live=force_regenerate_thumbs or not raw_short_9x16.exists(),
    )

    shutil.copyfile(raw_thumb_16x9, thumb_path)
    shutil.copyfile(raw_short_9x16, short_cover_path)

    hook_16x9 = strip_3d_text(blueprint.get("thumb_hook_3words") or "") or fallback_blueprint["thumb_hook_3words"]
    if is_syllabus and dur_upper.split()[0] not in hook_16x9.upper():
        hook_16x9 = default_hook
    hook_9x16 = strip_3d_text(blueprint.get("short_hook_3words") or "") or hook_16x9
    sub_tag = strip_3d_text(blueprint.get("thumb_sub_tagline") or "") or fallback_blueprint["thumb_sub_tagline"]

    apply_consistent_topperlab_thumbnail_branding(
        image_path=thumb_path,
        hook_text=hook_16x9,
        class_badge_text=class_badge_text,
        sub_tagline=sub_tag,
        is_vertical=False,
    )
    apply_consistent_topperlab_thumbnail_branding(
        image_path=short_cover_path,
        hook_text=hook_9x16,
        class_badge_text=class_badge_text,
        sub_tagline=sub_tag,
        is_vertical=True,
    )

    pkg = {
        "topic_title": topic_title,
        "pillar_id": pillar_id,
        "exam_track": strip_3d_text(exam_track),
        "selected_board": selected_board,
        "target_class_label": target_class_label,
        "target_subject_label": target_subject_label,
        "selected_chapter": clean_chapter,
        "video_category": video_category,
        "duration_badge": duration_badge,
        "class_badge_text": class_badge_text,
        "voice_mode": voice_mode,
        "visual_theme_key": visual_theme_key,
        "project_dir": to_portable_path(project_dir),
        "title_variations": blueprint["title_variations"],
        "thumb_hook_3words": hook_16x9,
        "short_hook_3words": hook_9x16,
        "thumb_sub_tagline": sub_tag,
        "thumbnail_16x9_path": to_portable_path(thumb_path),
        "short_cover_9x16_path": to_portable_path(short_cover_path),
        "thumbnail_16x9_prompt": final_t_prompt,
        "scenes": blueprint["scenes"],
    }
    (project_dir / "topperlab_blueprint.json").write_text(json.dumps(pkg, indent=2, ensure_ascii=False), encoding="utf-8")
    return pkg


# ============================================================================
# 5. STEP 3: EXPRESSIVE VOICE, BGM + SFX, ANIMATED FLY-IN FORMULAS & RENDERER
# ============================================================================
def _write_fallback_wav(wav_path: Path, duration_sec: float = 12.0) -> float:
    sample_rate = 44100
    n_samples = int(sample_rate * duration_sec)
    wav_path.parent.mkdir(parents=True, exist_ok=True)
    buf = array("h", [0] * (n_samples * 2))
    for i in range(n_samples):
        env = min(1.0, i / 2000.0, (n_samples - i) / 2000.0)
        val = int(env * 450 * math.sin(2.0 * math.pi * 220.0 * (i / sample_rate)))
        buf[2 * i] = val
        buf[2 * i + 1] = val
    with wave.open(str(wav_path), "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(buf.tobytes())
    return duration_sec


def _probe_wav_duration(wav_path: Path) -> float:
    try:
        with wave.open(str(wav_path), "rb") as wf:
            return max(3.5, round(wf.getnframes() / float(wf.getframerate()), 2))
    except Exception:
        return 12.0


def synthesize_scene_voiceover(narration: str, out_wav: Path, voice_preset: Dict[str, Any]) -> float:
    """
    Synthesizes expressive, lively Indian-student mentor narration:
      1. Primary: Vertex AI / Gemini `gemini-3.8-flash-tts` expressive AI voice acting (Puck / Aoede)
      2. Fallback: Microsoft `en-IN-NeerjaExpressiveNeural` / `hi-IN-SwaraNeural` with dynamic prosody
      Normalized cleanly to -14 LUFS at 44.1 kHz stereo.
    """
    out_wav.parent.mkdir(parents=True, exist_ok=True)
    raw_tts_wav = out_wav.with_name(out_wav.stem + "_raw_tts.wav")
    mp3_tmp = out_wav.with_suffix(".mp3")
    ffmpeg_bin = get_ffmpeg_exe()

    clean_spoken = re.sub(r"[*_#`]+", "", (narration or "")).strip()

    # 1. Primary Expressive Voice: Gemini 3.8 Flash TTS (Vertex AI credits or AI Studio)
    client = build_genai_client(location="global", timeout_ms=42000)
    if client is not None and clean_spoken:
        try:
            from google.genai import types

            gem_voice = voice_preset.get("gemini_voice", "Puck")
            resp = client.models.generate_content(
                model="gemini-3.8-flash-tts",
                contents=clean_spoken,
                config=types.GenerateContentConfig(
                    response_modalities=["AUDIO"],
                    speech_config=types.SpeechConfig(
                        voice_config=types.VoiceConfig(
                            prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=gem_voice)
                        )
                    ),
                ),
            )
            for part in getattr(resp.candidates[0].content, "parts", []):
                inline = getattr(part, "inline_data", None)
                if inline and getattr(inline, "data", None):
                    raw_bytes = inline.data
                    if raw_bytes[:4] == b"RIFF":
                        raw_tts_wav.write_bytes(raw_bytes)
                    else:
                        with wave.open(str(raw_tts_wav), "wb") as wf:
                            wf.setnchannels(1)
                            wf.setsampwidth(2)
                            wf.setframerate(24000)
                            wf.writeframes(raw_bytes)
                    subprocess.run(
                        [
                            ffmpeg_bin,
                            "-y",
                            "-i",
                            str(raw_tts_wav),
                            "-af",
                            "highpass=f=75,equalizer=f=3100:t=q:w=1.2:g=2.0,loudnorm=I=-14:TP=-1.5:LRA=11",
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
                    try:
                        raw_tts_wav.unlink(missing_ok=True)
                    except Exception:
                        pass
                    return _probe_wav_duration(out_wav)
        except Exception:
            pass

    # 2. Expressive Neural Fallback: edge-tts (`en-IN-NeerjaExpressiveNeural`)
    try:
        import edge_tts

        async def _run_tts() -> None:
            comm = edge_tts.Communicate(
                text=clean_spoken,
                voice=voice_preset.get("edge_voice", "en-IN-NeerjaExpressiveNeural"),
                rate=voice_preset.get("rate", "+9%"),
                pitch=voice_preset.get("pitch", "+3Hz"),
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
                    "highpass=f=75,equalizer=f=3100:t=q:w=1.2:g=2.0,loudnorm=I=-14:TP=-1.5:LRA=11",
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
            try:
                mp3_tmp.unlink(missing_ok=True)
            except Exception:
                pass
            return _probe_wav_duration(out_wav)
    except Exception:
        pass

    words = max(8, len(clean_spoken.split()))
    est_sec = round(max(6.0, words / 2.7), 1)
    return _write_fallback_wav(out_wav, duration_sec=est_sec)


def _add_pluck_note(
    buf_l: List[float],
    buf_r: List[float],
    sr: int,
    start_sec: float,
    freq: float,
    dur_sec: float = 0.30,
    amp: float = 0.25,
    pan: float = 0.5,
) -> None:
    n_total = len(buf_l)
    i0 = max(0, int(start_sec * sr))
    n_len = min(int(dur_sec * sr), n_total - i0)
    if n_len <= 0:
        return
    gain_l = amp * math.sqrt(max(0.0, 1.0 - pan))
    gain_r = amp * math.sqrt(min(1.0, pan))
    two_pi_f = 2.0 * math.pi * freq / sr
    for k in range(n_len):
        t = k / float(sr)
        att = min(1.0, t / 0.005)
        dec = math.exp(-7.8 * t)
        wave_v = (
            math.sin(two_pi_f * k)
            + 0.34 * math.sin(2.0 * two_pi_f * k) * math.exp(-15.0 * t)
            + 0.11 * math.sin(3.0 * two_pi_f * k) * math.exp(-24.0 * t)
        )
        s = att * dec * wave_v
        idx = i0 + k
        buf_l[idx] += s * gain_l
        buf_r[idx] += s * gain_r


def _add_swept_whoosh(
    buf_l: List[float],
    buf_r: List[float],
    sr: int,
    start_sec: float,
    dur_sec: float = 0.30,
    f_start: float = 210.0,
    f_end: float = 590.0,
    amp: float = 0.32,
) -> None:
    n_total = len(buf_l)
    i0 = max(0, int(start_sec * sr))
    n_len = min(int(dur_sec * sr), n_total - i0)
    if n_len <= 0:
        return
    phase = 0.0
    noise_state = 1337
    for k in range(n_len):
        u = k / float(n_len)
        env = math.sin(math.pi * u) ** 1.3
        freq = f_start + (f_end - f_start) * (u ** 0.85)
        phase += 2.0 * math.pi * freq / sr
        noise_state = (1103515245 * noise_state + 12345) & 0x7FFFFFFF
        n_val = ((noise_state / 1073741824.0) - 1.0) * 0.28
        val = env * amp * (0.72 * math.sin(phase) + n_val)
        pan = 0.25 + 0.5 * u
        idx = i0 + k
        buf_l[idx] += val * (1.0 - 0.35 * pan)
        buf_r[idx] += val * (0.65 + 0.35 * pan)


def build_scene_master_audio(
    voice_wav: Path,
    out_mix_wav: Path,
    duration_sec: float,
    formula_in_sec: float,
    formula_out_sec: float,
    hack_in_sec: float,
    hack_out_sec: float,
    scene_id: int = 1,
    bgm_enabled: bool = True,
) -> Path:
    """
    Mixes the expressive -14 LUFS narration with:
      1. Lively, copyright-safe Curiosity Marimba + Warm Bass + Soft Shaker BGM (auto-ducked under voice!)
      2. Crisp Scene-Transition Whoosh + Formula Fly-In Bell Chime + Quick-Tip Sparkle Ding SFX!
    """
    if not bgm_enabled or not voice_wav.exists():
        if voice_wav.exists() and voice_wav.resolve() != out_mix_wav.resolve():
            shutil.copyfile(voice_wav, out_mix_wav)
        return out_mix_wav

    try:
        with wave.open(str(voice_wav), "rb") as wf:
            sr = wf.getframerate()
            n_ch = wf.getnchannels()
            n_frames = wf.getnframes()
            raw_v = wf.readframes(n_frames)
        v_samples = array("h")
        v_samples.frombytes(raw_v)
        if n_ch == 1:
            stereo_v = array("h", [0] * (n_frames * 2))
            for i in range(n_frames):
                stereo_v[2 * i] = v_samples[i]
                stereo_v[2 * i + 1] = v_samples[i]
            v_samples = stereo_v
    except Exception:
        if voice_wav.exists():
            shutil.copyfile(voice_wav, out_mix_wav)
        return out_mix_wav

    n_total = len(v_samples) // 2
    sr = 44100
    bgm_l = [0.0] * n_total
    bgm_r = [0.0] * n_total
    sfx_l = [0.0] * n_total
    sfx_r = [0.0] * n_total

    # 1. Cheerful 116-BPM Student Curiosity Groove (Cadd9 -> Am7 -> Fmaj7 -> G6)
    bpm = 116.0
    beat_sec = 60.0 / bpm
    eighth_sec = beat_sec / 2.0
    bars = [
        (130.81, [261.63, 329.63, 392.00, 523.25, 392.00, 329.63, 587.33, 523.25]),
        (110.00, [220.00, 261.63, 329.63, 440.00, 392.00, 329.63, 523.25, 440.00]),
        (87.31, [174.61, 261.63, 329.63, 440.00, 523.25, 440.00, 329.63, 261.63]),
        (98.00, [196.00, 246.94, 293.66, 392.00, 493.88, 392.00, 329.63, 293.66]),
    ]
    bar_offset = (scene_id - 1) % len(bars)
    total_eighths = int(duration_sec / eighth_sec) + 2

    for step in range(total_eighths):
        t0 = step * eighth_sec
        bar_idx = (bar_offset + (step // 8)) % len(bars)
        bass_f, arp_notes = bars[bar_idx]
        note_f = arp_notes[step % 8]
        pan = 0.30 if (step % 2 == 0) else 0.70
        _add_pluck_note(bgm_l, bgm_r, sr, t0, note_f, dur_sec=0.31, amp=0.34, pan=pan)

        # Warm bass pulse every quarter beat
        if step % 2 == 0:
            _add_pluck_note(bgm_l, bgm_r, sr, t0, bass_f, dur_sec=0.48, amp=0.36, pan=0.5)
        # Soft upbeat shaker on off-beats
        if step % 2 == 1:
            sh_i0 = int(t0 * sr)
            sh_len = min(int(0.032 * sr), n_total - sh_i0)
            st_seed = 4242 + step * 97
            for k in range(max(0, sh_len)):
                st_seed = (1103515245 * st_seed + 12345) & 0x7FFFFFFF
                nv = ((st_seed / 1073741824.0) - 1.0) * math.exp(-95.0 * (k / float(sr))) * 0.08
                bgm_l[sh_i0 + k] += nv
                bgm_r[sh_i0 + k] += nv

    # 2. Synced Attention-Catching SFX (Transition Whoosh + Formula Chime + Quick-Tip Sparkle Ding)
    _add_swept_whoosh(sfx_l, sfx_r, sr, 0.02, dur_sec=0.30, f_start=190.0, f_end=560.0, amp=0.30)

    # Formula Fly-In ascending crystal bell chime
    _add_pluck_note(sfx_l, sfx_r, sr, max(0.1, formula_in_sec), 587.33, dur_sec=0.26, amp=0.38, pan=0.25)
    _add_pluck_note(sfx_l, sfx_r, sr, max(0.1, formula_in_sec + 0.07), 880.00, dur_sec=0.32, amp=0.40, pan=0.35)
    _add_pluck_note(sfx_l, sfx_r, sr, max(0.1, formula_in_sec + 0.14), 1174.66, dur_sec=0.38, amp=0.36, pan=0.45)

    # Formula Fly-Out soft breeze
    if formula_out_sec < duration_sec - 0.3:
        _add_swept_whoosh(sfx_l, sfx_r, sr, formula_out_sec, dur_sec=0.18, f_start=460.0, f_end=210.0, amp=0.16)

    # Quick-Tip / Hack Fly-In bright double-sparkle ding
    _add_pluck_note(sfx_l, sfx_r, sr, max(0.2, hack_in_sec), 659.25, dur_sec=0.25, amp=0.38, pan=0.75)
    _add_pluck_note(sfx_l, sfx_r, sr, max(0.2, hack_in_sec + 0.07), 987.77, dur_sec=0.30, amp=0.42, pan=0.68)
    _add_pluck_note(sfx_l, sfx_r, sr, max(0.2, hack_in_sec + 0.14), 1318.51, dur_sec=0.38, amp=0.38, pan=0.60)

    if hack_out_sec < duration_sec - 0.15:
        _add_swept_whoosh(sfx_l, sfx_r, sr, hack_out_sec, dur_sec=0.18, f_start=480.0, f_end=220.0, amp=0.16)

    # 3. Auto-Ducked Envelope Mix (50ms window so BGM breathes up in pauses and ducks cleanly under words!)
    win = 2205
    n_wins = (n_total + win - 1) // win
    bgm_gains = [0.22] * n_wins
    for w_idx in range(n_wins):
        s0 = w_idx * win
        s1 = min(n_total, s0 + win)
        peak = 0
        for j in range(s0, s1, 8):
            av = abs(v_samples[2 * j])
            if av > peak:
                peak = av
        # Duck to 0.21 during active speech; swell gently to 0.36 in speech pauses
        bgm_gains[w_idx] = 0.21 if peak > 1800 else 0.36

    # Smooth gain transitions
    for w_idx in range(1, n_wins):
        bgm_gains[w_idx] = 0.65 * bgm_gains[w_idx - 1] + 0.35 * bgm_gains[w_idx]

    out_samples = array("h", [0] * (n_total * 2))
    scale_pcm = 26000.0
    fade_samples = min(int(0.25 * sr), n_total // 4)

    for i in range(n_total):
        g_bgm = bgm_gains[i // win]
        end_fade = min(1.0, (n_total - i) / float(max(1, fade_samples)))
        vl = v_samples[2 * i]
        vr = v_samples[2 * i + 1]
        ml = int(vl + end_fade * scale_pcm * (g_bgm * bgm_l[i] + 0.44 * sfx_l[i]))
        mr = int(vr + end_fade * scale_pcm * (g_bgm * bgm_r[i] + 0.44 * sfx_r[i]))
        out_samples[2 * i] = 32200 if ml > 32200 else (-32200 if ml < -32200 else ml)
        out_samples[2 * i + 1] = 32200 if mr > 32200 else (-32200 if mr < -32200 else mr)

    out_mix_wav.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(out_mix_wav), "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(out_samples.tobytes())
    return out_mix_wav


def _wrap_text_pixels(draw: ImageDraw.ImageDraw, text: str, font: Any, max_px: int, max_lines: int = 2) -> List[str]:
    words = _sanitize_drawable_text(text).split()
    if not words:
        return [""]
    lines: List[str] = []
    cur = words[0]
    for w in words[1:]:
        cand = f"{cur} {w}"
        bb = draw.textbbox((0, 0), cand, font=font)
        if (bb[2] - bb[0]) <= max_px:
            cur = cand
        else:
            lines.append(cur)
            cur = w
    lines.append(cur)
    if len(lines) > max_lines:
        kept = lines[: max_lines - 1]
        tail = " ".join(lines[max_lines - 1 :])
        while len(tail) > 8:
            bb = draw.textbbox((0, 0), tail + "...", font=font)
            if (bb[2] - bb[0]) <= max_px:
                break
            tail = tail[:-2].rstrip()
        kept.append(tail + "...")
        return kept
    return lines


def _build_flyin_card_png(
    out_png: Path,
    card_size: tuple[int, int],
    ribbon_label: str,
    body_text: str,
    ribbon_bg: tuple[int, int, int, int],
    ribbon_fg: tuple[int, int, int, int],
    border_col: tuple[int, int, int, int],
    body_fg: tuple[int, int, int, int],
    body_font_size: int = 33,
) -> Path:
    cw, ch = card_size
    img = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Drop shadow + high-contrast dark slate card body
    draw.rounded_rectangle([8, 10, cw - 2, ch - 2], radius=24, fill=(0, 0, 0, 145))
    draw.rounded_rectangle(
        [2, 2, cw - 10, ch - 10],
        radius=24,
        fill=(15, 23, 42, 244),
        outline=border_col,
        width=4,
    )

    # Top header ribbon inside card
    f_rib = _load_studio_font(25, weight="bold")
    rib_clean = _sanitize_drawable_text(ribbon_label).upper()
    rb = draw.textbbox((0, 0), rib_clean, font=f_rib)
    rw, rh = (rb[2] - rb[0]) + 34, (rb[3] - rb[1]) + 16
    draw.rounded_rectangle([24, 18, 24 + rw, 18 + rh], radius=12, fill=ribbon_bg)
    draw.text((24 + 17, 18 + 7 - rb[1]), rib_clean, font=f_rib, fill=ribbon_fg)

    # Crisp wrapped body formula / hack text
    f_body = _load_studio_font(body_font_size, weight="bold")
    lines = _wrap_text_pixels(draw, body_text, f_body, max_px=cw - 64, max_lines=2)
    y_cur = 18 + rh + 16
    for ln in lines:
        lb = draw.textbbox((0, 0), ln, font=f_body)
        draw.text((26, y_cur - lb[1]), ln, font=f_body, fill=body_fg)
        y_cur += (lb[3] - lb[1]) + 10

    out_png.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_png, format="PNG")
    return out_png


def _build_scene_hud_png(
    out_png: Path,
    frame_size: tuple[int, int],
    class_badge_text: str,
    scene_id: int,
    headline: str,
    concept_takeaway: str,
    is_vertical: bool = False,
) -> Path:
    W, H = frame_size
    hud = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(hud)

    cls_clean = _sanitize_drawable_text(class_badge_text).upper()
    sc_clean = f"SCENE {scene_id:02d} • {_sanitize_drawable_text(headline).upper()}"
    take_clean = _sanitize_drawable_text(concept_takeaway)

    if not is_vertical:
        # Top-left Class Pill + Scene Headline Pill
        f_top = _load_studio_font(26, weight="bold")
        b_cls = draw.textbbox((0, 0), cls_clean, font=f_top)
        cw = (b_cls[2] - b_cls[0]) + 34
        ch_h = 52
        draw.rounded_rectangle([42, 28, 42 + cw, 28 + ch_h], radius=14, fill=(220, 38, 38, 248), outline=(255, 255, 255, 245), width=3)
        draw.text((42 + 17, 28 + 12 - b_cls[1]), cls_clean, font=f_top, fill=(255, 255, 255, 255))

        b_sc = draw.textbbox((0, 0), sc_clean, font=f_top)
        sw = (b_sc[2] - b_sc[0]) + 36
        sx = 42 + cw + 12
        draw.rounded_rectangle([sx, 28, sx + sw, 28 + ch_h], radius=14, fill=(15, 23, 42, 236), outline=(255, 214, 0, 235), width=3)
        draw.text((sx + 18, 28 + 12 - b_sc[1]), sc_clean, font=f_top, fill=(255, 214, 0, 255))

        # Bottom High-Readability Takeaway Strip
        f_bot = _load_studio_font(32, weight="bold")
        lines = _wrap_text_pixels(draw, take_clean, f_bot, max_px=W - 240, max_lines=2)
        bar_h = 68 if len(lines) == 1 else 108
        by = H - bar_h - 32
        bx0, bx1 = 76, W - 76
        draw.rounded_rectangle([bx0 + 4, by + 6, bx1 + 4, by + bar_h + 6], radius=18, fill=(0, 0, 0, 140))
        draw.rounded_rectangle([bx0, by, bx1, by + bar_h], radius=18, fill=(15, 23, 42, 238), outline=(56, 189, 248, 220), width=3)
        draw.rounded_rectangle([bx0, by, bx0 + 14, by + bar_h], radius=8, fill=(255, 214, 0, 255))

        yc = by + 16
        for ln in lines:
            lb = draw.textbbox((0, 0), ln, font=f_bot)
            draw.text((bx0 + 34, yc - lb[1]), ln, font=f_bot, fill=(248, 250, 252, 255))
            yc += (lb[3] - lb[1]) + 8
    else:
        # Vertical 9:16 Safe Zones (Top y=68..195, Bottom y=1465..1625 above Shorts UI!)
        f_top = _load_studio_font(29, weight="bold")
        b_cls = draw.textbbox((0, 0), cls_clean, font=f_top)
        cw = (b_cls[2] - b_cls[0]) + 40
        cx = (W - cw) // 2
        draw.rounded_rectangle([cx, 66, cx + cw, 120], radius=15, fill=(220, 38, 38, 248), outline=(255, 255, 255, 245), width=3)
        draw.text((cx + 20, 78 - b_cls[1]), cls_clean, font=f_top, fill=(255, 255, 255, 255))

        f_sc = _load_studio_font(27, weight="bold")
        b_sc = draw.textbbox((0, 0), sc_clean, font=f_sc)
        sw = min(W - 80, (b_sc[2] - b_sc[0]) + 38)
        sx = (W - sw) // 2
        draw.rounded_rectangle([sx, 130, sx + sw, 182], radius=14, fill=(15, 23, 42, 236), outline=(255, 214, 0, 235), width=3)
        draw.text((sx + 19, 142 - b_sc[1]), sc_clean, font=f_sc, fill=(255, 214, 0, 255))

        f_bot = _load_studio_font(33, weight="bold")
        lines = _wrap_text_pixels(draw, take_clean, f_bot, max_px=W - 150, max_lines=2)
        bar_h = 80 if len(lines) == 1 else 126
        by = 1480
        bx0, bx1 = 46, W - 46
        draw.rounded_rectangle([bx0, by, bx1, by + bar_h], radius=20, fill=(15, 23, 42, 240), outline=(255, 214, 0, 235), width=3)
        yc = by + 18
        for ln in lines:
            lb = draw.textbbox((0, 0), ln, font=f_bot)
            lx = (W - (lb[2] - lb[0])) // 2
            draw.text((lx, yc - lb[1]), ln, font=f_bot, fill=(255, 255, 255, 255))
            yc += (lb[3] - lb[1]) + 10

    out_png.parent.mkdir(parents=True, exist_ok=True)
    hud.save(out_png, format="PNG")
    return out_png


def render_faceless_scene_media(
    scene: Dict[str, Any],
    project_dir: Path,
    voice_preset: Dict[str, Any],
    visual_theme_prompt: str,
    force_live_image: bool = False,
    custom_motion_mp4: Path | None = None,
    class_badge_text: str = "CLASS 10 • SCIENCE 3D",
    bgm_enabled: bool = True,
) -> Dict[str, Any]:
    sid = int(scene["scene_id"])
    scenes_dir = project_dir / "scenes"
    scenes_dir.mkdir(parents=True, exist_ok=True)

    img_16x9 = scenes_dir / f"scene_{sid:02d}_16x9.jpg"
    img_9x16 = scenes_dir / f"scene_{sid:02d}_9x16.jpg"
    wav_voice = scenes_dir / f"scene_{sid:02d}_voice.wav"
    wav_master = scenes_dir / f"scene_{sid:02d}_master_audio.wav"
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
    if force_live_image and (has_vertex_adc() or get_gemini_api_key()):
        generate_pure_3d_image(
            prompt=f"Vertical 9:16 bright classroom 3D model composition: {full_img_prompt}",
            output_path=img_9x16,
            target_size=(1080, 1920),
            fallback_plate="sample_reel_9x16.jpg",
            force_live=True,
        )
    else:
        src_for_vert = Image.open(img_16x9)
        _fit_and_save_image(src_for_vert, img_9x16, (1080, 1920))

    dur_sec = synthesize_scene_voiceover(scene["narration"], wav_voice, voice_preset)

    # Compute smooth Fly-In / Fly-Out windows so Formula (1st half) & Quick-Tip/Hack (2nd half) never collide!
    f_in = 0.55
    f_hold = round(min(f_in + 0.48, dur_sec * 0.20), 2)
    f_out = round(max(f_hold + 1.1, dur_sec * 0.44), 2)
    f_end = round(min(dur_sec * 0.50, f_out + 0.44), 2)

    h_in = round(max(f_end + 0.12, dur_sec * 0.51), 2)
    h_hold = round(min(h_in + 0.48, dur_sec * 0.65), 2)
    h_out = round(max(h_hold + 1.1, dur_sec - 0.58), 2)
    h_end = round(min(dur_sec - 0.08, h_out + 0.44), 2)

    build_scene_master_audio(
        voice_wav=wav_voice,
        out_mix_wav=wav_master,
        duration_sec=dur_sec,
        formula_in_sec=f_in,
        formula_out_sec=f_out,
        hack_in_sec=h_in,
        hack_out_sec=h_out,
        scene_id=sid,
        bgm_enabled=bgm_enabled,
    )

    formula_txt = strip_3d_text(scene.get("formula_badge") or "") or f"Core Rule: {strip_3d_text(scene.get('headline', 'Key Law'))}"
    hack_txt = strip_3d_text(scene.get("quick_tip") or "") or strip_3d_text(scene.get("concept_takeaway", "Write units & steps clearly for full marks!"))
    takeaway_txt = strip_3d_text(scene.get("concept_takeaway") or "") or strip_3d_text(scene.get("headline", ""))

    # Build crisp RGBA PNG overlays for 16:9 and 9:16
    hud_16 = scenes_dir / f"scene_{sid:02d}_hud_16x9.png"
    form_16 = scenes_dir / f"scene_{sid:02d}_formula_16x9.png"
    hack_16 = scenes_dir / f"scene_{sid:02d}_hack_16x9.png"

    hud_9 = scenes_dir / f"scene_{sid:02d}_hud_9x16.png"
    form_9 = scenes_dir / f"scene_{sid:02d}_formula_9x16.png"
    hack_9 = scenes_dir / f"scene_{sid:02d}_hack_9x16.png"

    _build_scene_hud_png(hud_16, (1920, 1080), class_badge_text, sid, scene.get("headline", ""), takeaway_txt, is_vertical=False)
    _build_flyin_card_png(
        form_16,
        (750, 198),
        "KEY FORMULA",
        formula_txt,
        ribbon_bg=(255, 214, 0, 255),
        ribbon_fg=(15, 23, 42, 255),
        border_col=(255, 214, 0, 255),
        body_fg=(254, 240, 138, 255),
        body_font_size=33,
    )
    _build_flyin_card_png(
        hack_16,
        (750, 206),
        "QUICK TIP & EXAM HACK",
        hack_txt,
        ribbon_bg=(220, 38, 38, 255),
        ribbon_fg=(255, 255, 255, 255),
        border_col=(244, 63, 94, 255),
        body_fg=(255, 255, 255, 255),
        body_font_size=31,
    )

    _build_scene_hud_png(hud_9, (1080, 1920), class_badge_text, sid, scene.get("headline", ""), takeaway_txt, is_vertical=True)
    _build_flyin_card_png(
        form_9,
        (960, 218),
        "KEY FORMULA",
        formula_txt,
        ribbon_bg=(255, 214, 0, 255),
        ribbon_fg=(15, 23, 42, 255),
        border_col=(255, 214, 0, 255),
        body_fg=(254, 240, 138, 255),
        body_font_size=35,
    )
    _build_flyin_card_png(
        hack_9,
        (960, 226),
        "QUICK TIP & EXAM HACK",
        hack_txt,
        ribbon_bg=(220, 38, 38, 255),
        ribbon_fg=(255, 255, 255, 255),
        border_col=(244, 63, 94, 255),
        body_fg=(255, 255, 255, 255),
        body_font_size=33,
    )

    ffmpeg_bin = get_ffmpeg_exe()
    frames_total = max(50, int(math.ceil(dur_sec * 25)))

    saved_motion = scenes_dir / f"scene_{sid:02d}_custom_motion.mp4"
    if custom_motion_mp4 and Path(custom_motion_mp4).exists():
        if Path(custom_motion_mp4).resolve() != saved_motion.resolve():
            shutil.copyfile(custom_motion_mp4, saved_motion)

    f_in_dur = round(max(0.18, f_hold - f_in), 3)
    f_out_dur = round(max(0.18, f_end - f_out), 3)
    h_in_dur = round(max(0.18, h_hold - h_in), 3)
    h_out_dur = round(max(0.18, h_end - h_out), 3)

    render_specs = [
        # (is_vert, img_src, target_mp4, hud_p, form_p, hack_p, W_frame, H_frame, fx_rest, hx_rest, fy, hy)
        (False, img_16x9, mp4_16x9, hud_16, form_16, hack_16, 1920, 1080, 42, 1920 - 750 - 42, 102, 102),
        (True, img_9x16, mp4_9x16, hud_9, form_9, hack_9, 1080, 1920, 60, 60, 206, 206),
    ]

    for is_vert, src_img, target_mp4, hud_p, form_p, hack_p, wf, hf, fx_r, hx_r, fy, hy in render_specs:
        # Formula slides in from LEFT (-w -> fx_r) and slides out to LEFT (fx_r -> -w)
        fx_expr = (
            f"if(lt(t,{f_hold}), -w+(w+{fx_r})*((t-{f_in})/{f_in_dur}), "
            f"if(gt(t,{f_out}), {fx_r}-(w+{fx_r})*((t-{f_out})/{f_out_dur}), {fx_r}))"
        )
        # Quick Tip / Hack slides in from RIGHT (W -> hx_r) and slides out to RIGHT (hx_r -> W)
        hx_expr = (
            f"if(lt(t,{h_hold}), {wf}-({wf}-{hx_r})*((t-{h_in})/{h_in_dur}), "
            f"if(gt(t,{h_out}), {hx_r}+({wf}-{hx_r})*((t-{h_out})/{h_out_dur}), {hx_r}))"
        )

        if saved_motion.exists():
            base_chain = f"[0:v]scale={wf}:{hf}:force_original_aspect_ratio=increase,crop={wf}:{hf},fps=25,format=rgba[bg]"
            in_args = ["-stream_loop", "-1", "-i", str(saved_motion)]
            scene["motion_source"] = "Google Flow / Veo 3.1 + Fly-In Cards + BGM"
        else:
            base_chain = (
                f"[0:v]zoompan=z='min(zoom+0.0008,1.10)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
                f":d={frames_total}:s={wf}x{hf}:fps=25,format=rgba[bg]"
            )
            in_args = ["-loop", "1", "-i", str(src_img)]
            scene["motion_source"] = "Bright 3D Classroom Model + Fly-In Cards + BGM"

        fc_graph = (
            f"{base_chain};"
            f"[bg][1:v]overlay=0:0:format=auto[v1];"
            f"[v1][2:v]overlay=x='{fx_expr}':y={fy}:enable='between(t,{f_in},{f_end})':format=auto[v2];"
            f"[v2][3:v]overlay=x='{hx_expr}':y={hy}:enable='between(t,{h_in},{h_end})':format=auto,format=yuv420p[vout]"
        )

        cmd = [
            ffmpeg_bin,
            "-y",
            *in_args,
            "-i",
            str(hud_p),
            "-i",
            str(form_p),
            "-i",
            str(hack_p),
            "-i",
            str(wav_master),
            "-t",
            f"{dur_sec:.2f}",
            "-filter_complex",
            fc_graph,
            "-map",
            "[vout]",
            "-map",
            "4:a:0",
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
        ]
        subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)

    # Remove bulky intermediate uncompressed WAVs & temp overlay PNGs once muxed into AAC MP4s
    for tmp_f in (wav_voice, wav_master, hud_16, form_16, hack_16, hud_9, form_9, hack_9):
        try:
            tmp_f.unlink(missing_ok=True)
        except Exception:
            pass

    scene["duration_sec"] = dur_sec
    scene["img_16x9"] = to_portable_path(img_16x9)
    scene["img_9x16"] = to_portable_path(img_9x16)
    scene["mp4_16x9"] = to_portable_path(mp4_16x9)
    scene["mp4_9x16"] = to_portable_path(mp4_9x16)
    return scene


def stitch_master_videos(project_dir: Path, scenes: List[Dict[str, Any]], short_max_scenes: int = 4) -> Dict[str, Any]:
    renders_dir = resolve_workspace_path(project_dir) / "renders"
    renders_dir.mkdir(parents=True, exist_ok=True)
    ffmpeg_bin = get_ffmpeg_exe()

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


def render_full_topperlab_project(
    blueprint: Dict[str, Any],
    short_max_scenes: int = 4,
    bgm_enabled: bool = True,
    force_live_images: bool = False,
) -> Dict[str, Any]:
    ch = load_active_channel()
    project_dir = resolve_workspace_path(blueprint["project_dir"])
    voice_mode = blueprint.get("voice_mode", ch["default_voice_mode"])
    theme_key = blueprint.get("visual_theme_key", ch["default_visual_theme"])
    voice_preset = _resolve_voice_preset(ch, voice_mode)
    theme_prompt = _resolve_visual_theme(ch, theme_key)["style_prompt"]
    class_badge_text = blueprint.get("class_badge_text") or infer_class_badge_label(
        exam_track=blueprint.get("exam_track", ""),
        topic_title=blueprint.get("topic_title", ""),
        class_override=blueprint.get("target_class_label", ""),
        subject_override=blueprint.get("target_subject_label", ""),
    )

    scenes = blueprint["scenes"]
    for sc in scenes:
        render_faceless_scene_media(
            sc,
            project_dir,
            voice_preset,
            theme_prompt,
            force_live_image=force_live_images,
            class_badge_text=class_badge_text,
            bgm_enabled=bgm_enabled,
        )

    renders = stitch_master_videos(project_dir, scenes, short_max_scenes=short_max_scenes)
    draft_state = {
        **blueprint,
        "class_badge_text": class_badge_text,
        "bgm_enabled": bgm_enabled,
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
    new_formula_badge: str | None = None,
    new_quick_tip: str | None = None,
    bgm_enabled: bool = True,
) -> Dict[str, Any]:
    ch = load_active_channel()
    project_dir = resolve_workspace_path(draft_state["project_dir"])
    voice_mode = draft_state.get("voice_mode", ch["default_voice_mode"])
    theme_key = draft_state.get("visual_theme_key", ch["default_visual_theme"])
    voice_preset = _resolve_voice_preset(ch, voice_mode)
    theme_prompt = _resolve_visual_theme(ch, theme_key)["style_prompt"]
    class_badge_text = draft_state.get("class_badge_text") or infer_class_badge_label(
        exam_track=draft_state.get("exam_track", ""),
        topic_title=draft_state.get("topic_title", ""),
        class_override=draft_state.get("target_class_label", ""),
        subject_override=draft_state.get("target_subject_label", ""),
    )

    target = next((s for s in draft_state["scenes"] if int(s["scene_id"]) == int(scene_id)), None)
    if not target:
        raise ValueError(f"Scene {scene_id} not found.")

    target["narration"] = new_narration.strip()
    target["image_3d_prompt"] = new_3d_prompt.strip()
    if new_formula_badge is not None:
        target["formula_badge"] = new_formula_badge.strip()
    if new_quick_tip is not None:
        target["quick_tip"] = new_quick_tip.strip()

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
        class_badge_text=class_badge_text,
        bgm_enabled=bgm_enabled,
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
def _to_camel_hashtag(phrase: str) -> str:
    clean = strip_3d_text(phrase)
    words = re.findall(r"[A-Za-z0-9]+", clean)
    if not words:
        return ""
    camel = "".join(w if w.isupper() and len(w) <= 5 else (w[0].upper() + w[1:]) for w in words)
    return f"#{camel}" if camel else ""


def _build_dynamic_hashtags_and_tags(
    video_title: str,
    exam_track: str = "",
    board: str = "CBSE",
    class_name: str = "Class 10",
    subject: str = "Mathematics",
    chapter_name: str = "",
    video_category: str = "syllabus_chapter",
) -> tuple[List[str], List[str]]:
    clean_title = strip_3d_text(video_title)
    b = (board or "CBSE").strip().upper()
    if b not in ("CBSE", "ICSE"):
        b = "ICSE" if "icse" in f"{exam_track} {clean_title}".lower() else "CBSE"

    cls = strip_3d_text(class_name or "").strip()
    if not cls:
        m_cls = re.search(r"Class\s*(8|9|10|11|12)", f"{exam_track} {clean_title}", flags=re.IGNORECASE)
        cls = f"Class {m_cls.group(1)}" if m_cls else "Class 10"
    cls_compact = cls.replace(" ", "")  # e.g., Class10

    subj = strip_3d_text(subject or "").strip()
    if not subj or subj.lower() == "science":
        low_all = f"{clean_title} {chapter_name} {exam_track}".lower()
        if any(k in low_all for k in ("height", "distance", "trig", "quadratic", "triangle", "circle", "polynomial", "probability", "statistics", "arithmetic", "number", "algebra", "calculus", "matrix", "vector", "math")):
            subj = "Mathematics"
        elif any(k in low_all for k in ("chemical", "acid", "metal", "carbon", "periodic", "mole", "electrochem", "organic", "chemistry")):
            subj = "Chemistry"
        elif any(k in low_all for k in ("life process", "heredity", "reproduc", "cell", "tissue", "heart", "dna", "ecosystem", "biology")):
            subj = "Biology"
        else:
            subj = subj or "Physics"

    subj_short_map = {
        "Mathematics": "Maths",
        "Physics": "Physics",
        "Chemistry": "Chemistry",
        "Biology": "Biology",
        "Science": "Science",
        "Computer Science & AI": "ComputerScience",
        "History & Civics": "SST",
        "Geography": "Geography",
        "Economics": "Economics",
        "English": "English",
        "Topper Hacks": "StudyHacks",
    }
    subj_short = subj_short_map.get(subj, re.sub(r"[^A-Za-z0-9]", "", subj) or "Science")

    chap = strip_3d_text(chapter_name or "").strip()
    if not chap:
        chap = re.sub(r"\s+in\s+\d+\s*mins?\s+complete.*$", "", clean_title, flags=re.IGNORECASE).split("—")[0].split("|")[0].strip()

    chap_low = chap.lower()
    related_tag = ""
    if any(k in chap_low for k in ("height", "distance", "trigonometr")):
        related_tag = "#Trigonometry"
    elif any(k in chap_low for k in ("quadratic", "polynomial", "linear", "arithmetic")):
        related_tag = "#Algebra"
    elif any(k in chap_low for k in ("triangle", "circle", "coordinate", "surface", "area", "mensuration")):
        related_tag = "#Geometry"
    elif any(k in chap_low for k in ("light", "eye", "optics", "prism")):
        related_tag = "#Optics"
    elif any(k in chap_low for k in ("electric", "magnetic", "current", "ohm")):
        related_tag = "#Electricity"
    elif any(k in chap_low for k in ("motion", "force", "gravitation", "work", "rotational", "torque")):
        related_tag = "#Mechanics"

    raw_hashtags: List[str] = [
        _to_camel_hashtag(chap),
        f"#{cls_compact}{subj_short}",
        f"#{b}{cls_compact}",
        f"#{cls_compact}",
        _to_camel_hashtag(subj),
        related_tag,
    ]
    if b == "CBSE":
        raw_hashtags.extend([f"#NCERT{subj_short}", "#NCERT", "#CBSEBoards"])
    else:
        raw_hashtags.extend([f"#ICSE{subj_short}", "#ICSEBoard", "#CISCE"])

    if cls in ("Class 11", "Class 12"):
        if subj in ("Mathematics", "Physics", "Chemistry"):
            raw_hashtags.append("#JEEMains")
        if subj in ("Biology", "Physics", "Chemistry"):
            raw_hashtags.append("#NEETUG")

    if video_category == "syllabus_chapter":
        raw_hashtags.extend(["#CompleteChapter", "#OneShotRevision", "#BoardExam2026", f"#{subj_short}Tricks"])
    elif video_category == "toppers_hack":
        raw_hashtags.extend(["#ToppersHack", "#StudyStrategy", "#Score95Plus", "#BoardExamTips"])
    elif video_category == "exam_tricks":
        raw_hashtags.extend(["#ExamTricks", f"#{subj_short}Tricks", "#ShortcutTricks", "#BoardExam2026"])
    elif video_category == "super_memory":
        raw_hashtags.extend(["#SuperMemory", "#ActiveRecall", "#FormulaTricks", "#StudyHacks"])
    else:
        raw_hashtags.extend(["#CompleteChapter", "#BoardExam2026", f"#{subj_short}Tricks"])

    raw_hashtags.append("#TopperLab")

    hashtags: List[str] = []
    seen_h = set()
    for h in raw_hashtags:
        hc = strip_3d_text(h).strip()
        if hc.startswith("#") and len(hc) > 2 and hc.lower() not in seen_h and "3d" not in hc.lower():
            seen_h.add(hc.lower())
            hashtags.append(hc)
        if len(hashtags) >= 14:
            break

    chap_clean_low = chap.lower()
    cls_low = cls.lower()
    subj_low = subj.lower()
    b_low = b.lower()
    raw_seo_tags = [
        clean_title.lower(),
        f"{chap_clean_low} {cls_low}",
        f"{chap_clean_low} in 6 mins",
        f"{chap_clean_low} one shot",
        f"{b_low} {cls_low} {subj_low}",
        f"{cls_low} {subj_short.lower()} {chap_clean_low}",
        f"{chap_clean_low} all formulas",
        f"{chap_clean_low} tricks and shortcuts",
        f"{chap_clean_low} important board questions",
        f"ncert {cls_low} {subj_short.lower()}" if b == "CBSE" else f"icse {cls_low} {subj_short.lower()}",
        f"{cls_low} board exam preparation",
        "toppers hack",
        "exam tricks",
        "topperlab",
    ]
    seo_tags: List[str] = []
    seen_t = set()
    total_chars = 0
    for tg in raw_seo_tags:
        tc = strip_3d_text(tg).strip().lower()
        if tc and "3d" not in tc and tc not in seen_t and (total_chars + len(tc) + 2) <= 460:
            seen_t.add(tc)
            seo_tags.append(tc)
            total_chars += len(tc) + 2

    return hashtags, seo_tags


def generate_student_seo_bundle(
    video_title: str,
    exam_track: str,
    scenes: List[Dict[str, Any]],
    resource_links: List[Dict[str, str]],
    board: str = "CBSE",
    class_name: str = "Class 10",
    subject: str = "Mathematics",
    chapter_name: str = "",
    video_category: str = "syllabus_chapter",
) -> Dict[str, Any]:
    ch = load_active_channel()
    ch_name = strip_3d_text(ch.get("channel_name", "TopperLab")) or "TopperLab"
    clean_title = strip_3d_text(video_title)
    clean_track = strip_3d_text(exam_track) or f"{board} {class_name} {subject}"

    link_lines = []
    for item in resource_links:
        lbl = strip_3d_text(item.get("label", "")).strip()
        url = item.get("url", "").strip()
        cat = strip_3d_text(item.get("category", ""))
        if lbl and url:
            icon = "📄" if "PDF" in cat or "Formula" in cat else ("📊" if "Sheet" in cat or "Tracker" in cat else "📚")
            link_lines.append(f"{icon} {lbl}: {url}")
    links_block = "\n".join(link_lines) or "📄 Free 1-Page Formula & Quick-Tip Summary Sheet: Linked in Pinned Comment"

    chapters = []
    elapsed = 0.0
    for sc in scenes:
        mm = int(elapsed // 60)
        ss = int(elapsed % 60)
        hl = strip_3d_text(sc.get("headline", "Core Concept"))
        raw_tk = strip_3d_text(sc.get("concept_takeaway", ""))
        tk = raw_tk if len(raw_tk) <= 78 else (raw_tk[:75].rsplit(" ", 1)[0] + "...")
        chapters.append(f"{mm}:{ss:02d} {hl} — {tk}".rstrip(" —"))
        elapsed += float(sc.get("duration_sec", 12.0))
    chapters_block = "\n".join(chapters) if chapters else "0:00 Real-Life Hook & Core Intuition\n0:20 Key Formulas & Visual Breakdown\n0:45 Board Exam Shortcut & Rapid Recap"

    hashtags, seo_tags = _build_dynamic_hashtags_and_tags(
        video_title=clean_title,
        exam_track=clean_track,
        board=board,
        class_name=class_name,
        subject=subject,
        chapter_name=chapter_name,
        video_category=video_category,
    )

    clean_chap = strip_3d_text(chapter_name).strip() or re.sub(r"\s+in\s+\d+\s*mins?\s+complete.*$", "", clean_title, flags=re.IGNORECASE).strip()

    yt_description = strip_3d_text(
        f"{clean_title} — Master {clean_chap} ({board} {class_name} {subject}) with crystal-clear visual models, "
        f"all must-know formulas, and high-scoring exam shortcuts by {ch_name} ({clean_track}).\n\n"
        f"📥 FREE 1-PAGE FORMULA SHEETS, REVISION TRACKERS & STUDY RESOURCES:\n"
        f"{links_block}\n\n"
        f"⏱️ CHAPTER TIMESTAMPS:\n"
        f"{chapters_block}\n\n"
        f"🔔 Subscribe to {ch_name} — Complete {board} & ICSE Class 8–12 Chapters, Toppers Hacks & Exam Tricks!\n\n"
        f"{' '.join(hashtags)}"
    )

    short_caption = strip_3d_text(
        f"{clean_title} ⚡📘\n\n"
        f"Lock in every formula and board exam shortcut for {clean_chap} ({class_name} {subject}) in minutes!\n\n"
        f"📥 Grab the Free 1-Page Formula & Exam Hack Sheet:\n{links_block}\n\n"
        f"{' '.join(hashtags[:8])}"
    )

    pinned_comment = strip_3d_text(
        f"📌 PINNED BY {ch_name.upper()}:\n"
        f"Download today's Free 1-Page Formula Sheet & Active-Recall Revision Tracker here 👇\n"
        f"{links_block}\n\n"
        f"Which {board} / ICSE chapter or Exam Trick should we cover next? Comment below! 👇"
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
    target_boards: List[str] | None = None,
    target_class: str = "",
    target_subject: str = "",
) -> Dict[str, Any]:
    title = strip_3d_text(title)
    description_or_caption = strip_3d_text(description_or_caption)
    tags = [strip_3d_text(t) for t in tags if strip_3d_text(t) and "3d" not in strip_3d_text(t).lower()]
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
                pl_suffix = ""
                vid_id = res.get("video_id", "")
                if vid_id and target_boards and target_class and target_subject:
                    added_pls = auto_assign_video_to_curriculum_playlists(
                        video_id=vid_id,
                        boards=target_boards,
                        class_name=target_class,
                        subject=target_subject,
                    )
                    if added_pls:
                        pl_suffix = f" | Added to: {', '.join(added_pls)}"
                note = f"{res['url']}{pl_suffix}"
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


# ============================================================================
# 8. CBSE & ICSE (CLASS 8–12) PLAYLIST & CHANNEL HOMEPAGE SECTION ARCHITECT
# ============================================================================
CURRICULUM_BOARDS: List[str] = ["CBSE", "ICSE"]
CURRICULUM_CLASSES: List[str] = ["Class 12", "Class 11", "Class 10", "Class 9", "Class 8"]
CORE_STEM_SUBJECTS: List[str] = ["Physics", "Chemistry", "Mathematics", "Biology"]
OPTIONAL_EXTRA_SUBJECTS: List[str] = [
    "Computer Science & AI",
    "History & Civics",
    "Geography",
    "Economics",
    "English",
]
ALL_CURRICULUM_SUBJECTS: List[str] = CORE_STEM_SUBJECTS + OPTIONAL_EXTRA_SUBJECTS

_YT_SCOPE_CACHE: Dict[str, bool] = {}


def check_youtube_playlist_scope() -> bool:
    """Returns True if the active YouTube OAuth token includes full `youtube` write scope for playlists & sections."""
    access_token = get_valid_youtube_access_token()
    if not access_token:
        return False
    if access_token in _YT_SCOPE_CACHE:
        return _YT_SCOPE_CACHE[access_token]
    try:
        r = requests.get(
            "https://oauth2.googleapis.com/tokeninfo",
            params={"access_token": access_token},
            timeout=10,
        )
        scopes = set((r.json().get("scope") or "").split())
        has_full = (
            "https://www.googleapis.com/auth/youtube" in scopes
            or "https://www.googleapis.com/auth/youtube.force-ssl" in scopes
        )
        _YT_SCOPE_CACHE[access_token] = has_full
        return has_full
    except Exception:
        return False


def format_curriculum_playlist_title(board: str, class_name: str, subject: str) -> str:
    b = board.strip().upper()
    c = class_name.strip()
    s = subject.strip()
    if b == "CBSE":
        tag = "Complete NCERT & JEE/NEET" if c in ("Class 11", "Class 12") else "Complete Chapters & Board Prep"
        return f"CBSE {c} {s} | {tag}"
    if c in ("Class 11", "Class 12"):
        return f"ISC / ICSE {c} {s} | Complete Chapters & Board Prep"
    return f"ICSE {c} {s} | Complete Chapters & Board Prep"


def _legacy_curriculum_playlist_title(board: str, class_name: str, subject: str) -> str:
    b = board.strip().upper()
    c = class_name.strip()
    s = subject.strip()
    if b == "CBSE":
        tag = "3D NCERT & JEE/NEET" if c in ("Class 11", "Class 12") else "3D NCERT Concepts & Board Prep"
        return f"CBSE {c} {s} | {tag}"
    if c in ("Class 11", "Class 12"):
        return f"ISC / ICSE {c} {s} | 3D Concepts & Board Prep"
    return f"ICSE {c} {s} | 3D Concepts & Board Prep"


def format_curriculum_playlist_description(board: str, class_name: str, subject: str) -> str:
    b_lbl = "CBSE (NCERT)" if board.strip().upper() == "CBSE" else ("ISC / ICSE Council" if class_name in ("Class 11", "Class 12") else "ICSE")
    return (
        f"Complete {b_lbl} {class_name} {subject} Foundation Chapter Series by TopperLab.\n\n"
        f"Master every syllabus chapter in minutes with crystal-clear visual models, animated formulas, "
        f"toppers hacks, and exam shortcuts — engineered for {b_lbl} {class_name} board exams, olympiads, JEE, and NEET.\n"
        f"📄 Free 1-Page Formula & Revision Sheets linked inside every video description!"
    )


def list_live_youtube_playlists() -> List[Dict[str, Any]]:
    access_token = get_valid_youtube_access_token()
    if not access_token:
        return []
    headers = {"Authorization": f"Bearer {access_token}"}
    items: List[Dict[str, Any]] = []
    page_token = ""
    try:
        for _ in range(5):
            params: Dict[str, Any] = {"part": "snippet,contentDetails,status", "mine": "true", "maxResults": 50}
            if page_token:
                params["pageToken"] = page_token
            r = requests.get("https://www.googleapis.com/youtube/v3/playlists", params=params, headers=headers, timeout=15)
            if r.status_code != 200:
                break
            body = r.json()
            for it in body.get("items", []):
                items.append(
                    {
                        "id": it["id"],
                        "title": it.get("snippet", {}).get("title", ""),
                        "videos": it.get("contentDetails", {}).get("itemCount", 0),
                        "privacy": it.get("status", {}).get("privacyStatus", "public"),
                        "url": f"https://www.youtube.com/playlist?list={it['id']}",
                    }
                )
            page_token = body.get("nextPageToken", "")
            if not page_token:
                break
    except Exception:
        pass
    return items


def add_video_to_youtube_playlist(video_id: str, playlist_id: str, access_token: str = "") -> bool:
    tok = access_token or get_valid_youtube_access_token()
    if not tok or not video_id or not playlist_id:
        return False
    headers = {"Authorization": f"Bearer {tok}", "Content-Type": "application/json; charset=UTF-8"}
    try:
        chk = requests.get(
            "https://www.googleapis.com/youtube/v3/playlistItems",
            params={"part": "id", "playlistId": playlist_id, "videoId": video_id, "maxResults": 1},
            headers={"Authorization": f"Bearer {tok}"},
            timeout=12,
        )
        if chk.status_code == 200 and chk.json().get("items"):
            return True
        ins = requests.post(
            "https://www.googleapis.com/youtube/v3/playlistItems?part=snippet",
            headers=headers,
            data=json.dumps(
                {
                    "snippet": {
                        "playlistId": playlist_id,
                        "resourceId": {"kind": "youtube#video", "videoId": video_id},
                    }
                }
            ).encode("utf-8"),
            timeout=15,
        )
        return ins.status_code in (200, 201)
    except Exception:
        return False


def auto_assign_video_to_curriculum_playlists(
    video_id: str,
    boards: List[str],
    class_name: str,
    subject: str,
) -> List[str]:
    """Finds (or creates) matching Board+Class+Subject playlists and adds `video_id` to each."""
    tok = get_valid_youtube_access_token()
    if not tok or not check_youtube_playlist_scope():
        return []
    existing_by_title = {p["title"]: p["id"] for p in list_live_youtube_playlists()}
    headers = {"Authorization": f"Bearer {tok}", "Content-Type": "application/json; charset=UTF-8"}
    added_titles: List[str] = []
    for b in boards:
        pl_title = format_curriculum_playlist_title(b, class_name, subject)
        leg_title = _legacy_curriculum_playlist_title(b, class_name, subject)
        pl_id = existing_by_title.get(pl_title) or existing_by_title.get(leg_title, "")
        if not pl_id:
            r = requests.post(
                "https://www.googleapis.com/youtube/v3/playlists?part=snippet,status",
                headers=headers,
                data=json.dumps(
                    {
                        "snippet": {
                            "title": pl_title,
                            "description": format_curriculum_playlist_description(b, class_name, subject),
                            "defaultLanguage": "en-IN",
                        },
                        "status": {"privacyStatus": "public"},
                    }
                ).encode("utf-8"),
                timeout=15,
            )
            if r.status_code in (200, 201):
                pl_id = r.json().get("id", "")
                existing_by_title[pl_title] = pl_id
        if pl_id and add_video_to_youtube_playlist(video_id, pl_id, access_token=tok):
            added_titles.append(f"{b} {class_name} {subject}")
    return added_titles


def sync_cbse_icse_playlists_and_sections(
    boards: List[str] | None = None,
    classes: List[str] | None = None,
    subjects: List[str] | None = None,
    attach_existing_videos: bool = True,
) -> Dict[str, Any]:
    """
    Idempotently creates all CBSE & ICSE (Class 8–12) subject-wise playlists on @TopperLab3D
    AND organizes the YouTube Channel Homepage into clean Board + Class horizontal shelves (`channelSections`).
    """
    tok = get_valid_youtube_access_token()
    if not tok:
        return {"ok": False, "error": "YouTube OAuth is not connected yet. Authorize in Step 1 first."}
    if not check_youtube_playlist_scope():
        return {
            "ok": False,
            "needs_reauth": True,
            "error": (
                "Your current YouTube token only has Upload + Read permission. "
                "Click 'Authorize @TopperLab3D (Unlock Playlist & Section Manager)' once above to grant Playlist & Homepage Section permission!"
            ),
        }

    sel_boards = boards or CURRICULUM_BOARDS
    sel_classes = classes or CURRICULUM_CLASSES
    sel_subjects = subjects or CORE_STEM_SUBJECTS

    headers = {"Authorization": f"Bearer {tok}", "Content-Type": "application/json; charset=UTF-8"}
    existing_pls = list_live_youtube_playlists()
    by_title: Dict[str, str] = {p["title"]: p["id"] for p in existing_pls}

    created_count = 0
    reused_count = 0
    errors: List[str] = []
    matrix_ids: Dict[tuple[str, str, str], str] = {}

    for b in sel_boards:
        for c in sel_classes:
            for s in sel_subjects:
                title = format_curriculum_playlist_title(b, c, s)
                leg_title = _legacy_curriculum_playlist_title(b, c, s)
                if title in by_title or leg_title in by_title:
                    matrix_ids[(b, c, s)] = by_title.get(title) or by_title[leg_title]
                    reused_count += 1
                    continue
                resp = requests.post(
                    "https://www.googleapis.com/youtube/v3/playlists?part=snippet,status",
                    headers=headers,
                    data=json.dumps(
                        {
                            "snippet": {
                                "title": title,
                                "description": format_curriculum_playlist_description(b, c, s),
                                "defaultLanguage": "en-IN",
                            },
                            "status": {"privacyStatus": "public"},
                        }
                    ).encode("utf-8"),
                    timeout=20,
                )
                if resp.status_code in (200, 201):
                    pid = resp.json()["id"]
                    by_title[title] = pid
                    matrix_ids[(b, c, s)] = pid
                    created_count += 1
                else:
                    errors.append(f"{title}: HTTP {resp.status_code} {sanitize_api_error(resp.text)[:140]}")
                    if resp.status_code == 403 and "quota" in resp.text.lower():
                        break
            if errors and "quota" in errors[-1].lower():
                break

    # Attach existing Rotational Motion & Torque videos to Class 11 Physics (CBSE + ICSE) so shelves populate!
    attached_videos = 0
    if attach_existing_videos:
        live_vids = fetch_live_youtube_channel_videos(max_results=10)
        for v in live_vids:
            t_low = v.get("Title", "").lower()
            vid_id = v.get("Video ID", "")
            if vid_id and ("gyroscope" in t_low or "rotational" in t_low or "torque" in t_low):
                for b in ("CBSE", "ICSE"):
                    pid = matrix_ids.get((b, "Class 11", "Physics"))
                    if pid and add_video_to_youtube_playlist(vid_id, pid, access_token=tok):
                        attached_videos += 1

    # Organize Channel Homepage Sections (`multiplePlaylists`) — max 8 custom shelves + Shorts + Recent Uploads = 10
    sections_created = 0
    sections_updated = 0
    try:
        sec_r = requests.get(
            "https://www.googleapis.com/youtube/v3/channelSections",
            params={"part": "snippet,contentDetails", "mine": "true"},
            headers={"Authorization": f"Bearer {tok}"},
            timeout=15,
        )
        existing_secs = sec_r.json().get("items", []) if sec_r.status_code == 200 else []
        existing_multi_by_title: Dict[str, Dict[str, Any]] = {}
        for sec in existing_secs:
            stype = (sec.get("snippet", {}).get("type") or "").lower()
            stitle = sec.get("snippet", {}).get("title", "")
            # Free up unused empty default shelves so YouTube's 10-shelf cap has room for CBSE + ICSE shelves
            if stype in ("completedevents", "allplaylists", "upcomingevents", "liveevents"):
                requests.delete(
                    "https://www.googleapis.com/youtube/v3/channelSections",
                    params={"id": sec["id"]},
                    headers={"Authorization": f"Bearer {tok}"},
                    timeout=12,
                )
            elif stype == "multipleplaylists" and stitle:
                existing_multi_by_title[stitle] = sec

        shelf_specs = [
            ("📘 CBSE Class 12 — All Subjects (Complete Chapters)", "CBSE", ["Class 12"]),
            ("📘 CBSE Class 11 — All Subjects (Complete Chapters)", "CBSE", ["Class 11"]),
            ("📘 CBSE Class 9 & 10 — All Subjects (Complete Board Prep)", "CBSE", ["Class 10", "Class 9"]),
            ("📘 CBSE Class 8 — All Subjects (Foundation)", "CBSE", ["Class 8"]),
            ("📗 ISC / ICSE Class 12 — All Subjects (Complete Chapters)", "ICSE", ["Class 12"]),
            ("📗 ISC / ICSE Class 11 — All Subjects (Complete Chapters)", "ICSE", ["Class 11"]),
            ("📗 ICSE Class 9 & 10 — All Subjects (Complete Board Prep)", "ICSE", ["Class 10", "Class 9"]),
            ("📗 ICSE Class 8 — All Subjects (Foundation)", "ICSE", ["Class 8"]),
        ]

        for shelf_title, board_key, cls_list in shelf_specs:
            if board_key not in sel_boards:
                continue
            pids = [
                matrix_ids[(board_key, c, s)]
                for c in cls_list
                for s in sel_subjects
                if (board_key, c, s) in matrix_ids
            ]
            if not pids:
                continue
            if shelf_title in existing_multi_by_title:
                sec_obj = existing_multi_by_title[shelf_title]
                up_r = requests.put(
                    "https://www.googleapis.com/youtube/v3/channelSections?part=snippet,contentDetails",
                    headers=headers,
                    data=json.dumps(
                        {
                            "id": sec_obj["id"],
                            "snippet": {"type": "multiplePlaylists", "title": shelf_title},
                            "contentDetails": {"playlists": pids[:25]},
                        }
                    ).encode("utf-8"),
                    timeout=15,
                )
                if up_r.status_code in (200, 201):
                    sections_updated += 1
            else:
                in_r = requests.post(
                    "https://www.googleapis.com/youtube/v3/channelSections?part=snippet,contentDetails",
                    headers=headers,
                    data=json.dumps(
                        {
                            "snippet": {"type": "multiplePlaylists", "title": shelf_title},
                            "contentDetails": {"playlists": pids[:25]},
                        }
                    ).encode("utf-8"),
                    timeout=15,
                )
                if in_r.status_code in (200, 201):
                    sections_created += 1
    except Exception as exc:
        errors.append(f"Section sync notice: {sanitize_api_error(exc)[:140]}")

    catalog_out = {
        "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "playlists": {f"{b}|{c}|{s}": pid for (b, c, s), pid in matrix_ids.items()},
    }
    try:
        (CONFIG_DIR / "playlists_catalog.json").write_text(json.dumps(catalog_out, indent=2), encoding="utf-8")
    except Exception:
        pass

    return {
        "ok": True,
        "created_playlists": created_count,
        "reused_playlists": reused_count,
        "total_playlists_ready": len(matrix_ids),
        "attached_video_links": attached_videos,
        "sections_created": sections_created,
        "sections_updated": sections_updated,
        "errors": errors,
    }
