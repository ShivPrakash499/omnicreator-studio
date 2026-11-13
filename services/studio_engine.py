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
    """Keep ASCII + standard Latin/Greek/Math symbols supported by DejaVuSans & Segoe UI; replace rare math symbols that cause tofu boxes."""
    s = str(text or "")
    replacements = {
        "\u2220": "Angle ",   # ∠
        "\u25b6": ">> ",      # ▶
        "\u2713": "",         # ✓
        "\u2714": "",         # ✔
        "\u21d2": "->",       # ⇒
        "\u2192": "->",       # →
        "\u2190": "<-",       # ←
        "\u2191": "^",        # ↑
        "\u2193": "v",        # ↓
        "\u22a5": " perp ",   # ⊥
        "\u25b3": "Triangle ",# △
        "\u2248": "~=",       # ≈
        "\u2260": "!=",       # ≠
        "\u2264": "<=",       # ≤
        "\u2265": ">=",       # ≥
    }
    for k, v in replacements.items():
        if k in s:
            s = s.replace(k, v)
    cleaned = []
    for ch in s:
        code = ord(ch)
        if code <= 0x221A and ch not in ("\ufe0f", "\u200d"):
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
    duration_seconds: int = 4,
) -> Dict[str, Any]:
    """
    Generates direct 3D physics/geometry B-roll motion clip via Vertex AI Veo 3.1
    (`veo-3.1-lite-generate-001` / `veo-3.1-fast-generate-001` / `veo-3.1-generate-001`)
    or Gemini Omni 1.2 Flash (`gemini-omni-1.2-flash`).
    """
    clean_prompt = (
        f"{veo_prompt.strip()} "
        "Bright colorful Pixar-style 3D educational classroom demonstration, smooth cinematic camera motion, "
        "100% faceless, zero human faces, zero text."
    )
    try:
        import time
        from google.genai import types

        v_client = build_genai_client(location="us-central1", timeout_ms=300000)
        if v_client is None:
            return {
                "ok": False,
                "message": "Add VERTEX_ADC_JSON in Streamlit Secrets (or use the Free Built-In Renderer at the top of Step 3!).",
            }

        is_vertex = _is_vertex_client(v_client)
        last_err = ""
        if is_vertex:
            for veo_model in ("veo-3.1-lite-generate-001", "veo-3.1-fast-generate-001", "veo-3.1-generate-001"):
                try:
                    cfg_kwargs: Dict[str, Any] = {"aspect_ratio": aspect_ratio}
                    if duration_seconds in (4, 6, 8):
                        cfg_kwargs["duration_seconds"] = duration_seconds
                    op = v_client.models.generate_videos(
                        model=veo_model,
                        prompt=clean_prompt,
                        config=types.GenerateVideosConfig(**cfg_kwargs),
                    )
                    for _ in range(42):
                        if getattr(op, "done", False):
                            break
                        time.sleep(4)
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
            "message": f"Motion API notice: {last_err[:200] or 'Use the Built-In Live Geometry + B-Roll Renderer above!'}",
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


ACT_BADGE_LABELS: Dict[int, str] = {
    1: "ACT 1: HOOK & ? PUZZLE",
    2: "ACT 2: VISUAL PROOF & ARCS",
    3: "ACT 3: 5-SEC BOSS CLIMAX",
    4: "ACT 4: EXAM TRAP & SUBSCRIBE",
}


def _parse_formula_into_three_portions(
    formula_badge: str,
    headline: str = "",
    custom_parts: List[Dict[str, str]] | None = None,
) -> List[Dict[str, str]]:
    """
    Splits any formula into 3 color-coded portions (Portion 1: Cyan, Portion 2: Yellow, Portion 3: Emerald/Coral)
    so that as each geometric segment (Base, Height, Angle Arc / Result) is drawn on screen, the matching
    formula portion lights up in real time (inspired by reference Short 8MXN6QjPJqc).
    """
    if isinstance(custom_parts, list) and len(custom_parts) >= 3:
        cleaned_custom: List[Dict[str, str]] = []
        for idx, item in enumerate(custom_parts[:3]):
            if isinstance(item, dict):
                lbl = _sanitize_drawable_text(strip_3d_text(item.get("label", f"PART {idx + 1}"))).upper()
                expr = _sanitize_drawable_text(strip_3d_text(item.get("expr", "")))
                if expr:
                    cleaned_custom.append({"label": lbl[:24], "expr": expr[:36]})
        if len(cleaned_custom) == 3:
            return cleaned_custom

    f_clean = _sanitize_drawable_text(strip_3d_text(formula_badge or ""))
    if "|" in f_clean:
        segs = [s.strip() for s in f_clean.split("|") if s.strip()]
        if len(segs) >= 3:
            return [
                {"label": "1. RATIO 30 DEG", "expr": segs[0][:34]},
                {"label": "2. RATIO 45 DEG", "expr": segs[1][:34]},
                {"label": "3. RATIO 60 DEG", "expr": segs[2][:34]},
            ]
    if "•" in f_clean:
        segs = [s.strip() for s in f_clean.split("•") if s.strip()]
        if len(segs) >= 3:
            return [
                {"label": "1. STEP ONE", "expr": segs[0][:34]},
                {"label": "2. STEP TWO", "expr": segs[1][:34]},
                {"label": "3. STEP THREE", "expr": segs[2][:34]},
            ]
    if "⇒" in f_clean or "->" in f_clean or "→" in f_clean:
        parts = re.split(r"⇒|->|→", f_clean)
        parts = [p.strip() for p in parts if p.strip()]
        if len(parts) >= 2:
            left = parts[0]
            right = parts[1]
            if "=" in left:
                l_sub = [x.strip() for x in left.split("=", 1)]
                return [
                    {"label": "1. GIVEN WALK (d)", "expr": l_sub[0][:34]},
                    {"label": "2. COT DIFFERENCE", "expr": l_sub[1][:34]},
                    {"label": "3. HEIGHT SHORTCUT", "expr": right[:34]},
                ]
            return [
                {"label": "1. INPUT CAUSE", "expr": left[:34]},
                {"label": "2. CORE LAW", "expr": (_sanitize_drawable_text(headline) or "Direct Relation")[:34]},
                {"label": "3. FINAL RESULT", "expr": right[:34]},
            ]
    if "=" in f_clean:
        lhs, rhs = [x.strip() for x in f_clean.split("=", 1)]
        if "/" in rhs:
            num, den = [x.strip() for x in rhs.split("/", 1)]
            return [
                {"label": "1. BASE (DENOMINATOR)", "expr": den[:34]},
                {"label": "2. HEIGHT (NUMERATOR)", "expr": num[:34]},
                {"label": "3. ANGLE RATIO", "expr": f"{lhs} = H / B"[:34]},
            ]
        if "+" in rhs:
            p1, p2 = [x.strip() for x in rhs.split("+", 1)]
            return [
                {"label": "1. TRIANGLE PART", "expr": p1[:34]},
                {"label": "2. OBSERVER EYE (+)", "expr": f"+ {p2}"[:34]},
                {"label": "3. TOTAL RESULT", "expr": f"{lhs} = {p1[:12]} + {p2[:12]}"[:34]},
            ]
        if "×" in rhs or "*" in rhs:
            p1, p2 = [x.strip() for x in re.split(r"[×*]", rhs, maxsplit=1)]
            return [
                {"label": "1. TERM ONE", "expr": p1[:34]},
                {"label": "2. TERM TWO", "expr": p2[:34]},
                {"label": "3. PRODUCT LAW", "expr": f"{lhs} = {rhs}"[:34]},
            ]
        return [
            {"label": "1. TARGET QUANTITY", "expr": lhs[:34]},
            {"label": "2. FORMULA EXPRESSION", "expr": rhs[:34]},
            {"label": "3. COMPLETE EQUATION", "expr": f_clean[:34]},
        ]

    return [
        {"label": "1. BASE & LINE", "expr": (f_clean[:32] or "Horizontal Base (B)")},
        {"label": "2. VERTICAL HEIGHT", "expr": (_sanitize_drawable_text(headline)[:32] or "Perpendicular (H)")},
        {"label": "3. ANGLE & RATIO", "expr": "tan θ = Opposite / Adjacent"},
    ]


def _default_gyroscope_scenes(topic_title: str, is_hinglish: bool = False) -> List[Dict[str, Any]]:
    t_low = topic_title.lower()
    if "height" in t_low or "distance" in t_low or "elevation" in t_low:
        return [
            {
                "scene_id": 1,
                "act_badge": ACT_BADGE_LABELS[1],
                "target_angle_deg": 45,
                "headline": "ELEVATION VS DEPRESSION",
                "concept_takeaway": "Looking UP from eye-level = Elevation; Looking DOWN = Depression (Equal by Z-Rule!)",
                "formula_badge": "tan θ = Perpendicular (Height) / Base (Ground Distance)",
                "formula_parts": [
                    {"label": "1. BASE (GROUND = B)", "expr": "Base = Ground Distance (B)"},
                    {"label": "2. HEIGHT (TOWER = H)", "expr": "Perpendicular = Height (H)"},
                    {"label": "3. TAN RATIO & Z-RULE", "expr": "tan θ = H / B  (Elev = Depr)"},
                ],
                "quick_tip": "Z-Angle Hack: Angle of Depression from top ALWAYS equals Angle of Elevation from ground!",
                "narration": (
                    "Wait a second—can you find the exact height of a giant lighthouse without ever climbing it?! "
                    "Watch the green markers 1, 2, 3 lock onto the ground base, then the yellow vertical height rises at ninety degrees, and the red laser sight-line slices down! "
                    "By the alternate Z-angle law, Angle of Depression from the top ALWAYS equals Angle of Elevation from the ground!"
                    if not is_hinglish
                    else "Ruko zara—kya aap bina chadhe kisi oonche lighthouse ki exact height sirf paanch second mein nikaal sakte hain?! Dekhiye green markers 1, 2, 3 ground base banate hain, yellow line seedhi height uthati hai, aur red laser sight-line angle lock karti hai! Z-rule se Depression aur Elevation hamesha barabar hote hain!"
                ),
                "image_3d_prompt": "Bright sunny Pixar-style 3D classroom geometry tabletop model: a cheerful red-and-white striped coastal lighthouse on a green cliff overlooking a small yellow boat on calm blue water, crisp yellow horizontal eye-level beam and a vivid red diagonal line-of-sight forming a clear right-angled triangle, warm sunlit sky backdrop, zero text, zero faces.",
                "google_flow_veo_prompt": "Dynamic camera sweep across a bright Pixar-style 3D coastal lighthouse and yellow boat as a glowing red laser sight-beam and yellow horizontal line trace a right-angled triangle over blue water.",
                "fallback_plate": "scene_01_16x9.jpg",
            },
            {
                "scene_id": 2,
                "act_badge": ACT_BADGE_LABELS[2],
                "target_angle_deg": 60,
                "headline": "30-45-60 COMPASS PROOF",
                "concept_takeaway": "95% of Class 10 Board questions use ONLY tan 30°, tan 45°, and tan 60°!",
                "formula_badge": "tan 30° = 1/√3   |   tan 45° = 1   |   tan 60° = √3",
                "formula_parts": [
                    {"label": "1. SHALLOW 30 DEG", "expr": "tan 30° = 1 / √3 (Long Base)"},
                    {"label": "2. EQUAL 45 DEG", "expr": "tan 45° = 1  (Height = Base!)"},
                    {"label": "3. STEEP 60 DEG", "expr": "tan 60° = √3 (Tall Height)"},
                ],
                "quick_tip": "1-Second 45° Hack: Whenever angle is 45°, Tower Height = Ground Shadow Length instantly!",
                "narration": (
                    "Now watch our metallic compass scratch the three golden angles that control ninety-five percent of board exams! "
                    "At thirty degrees, tan is one over root three. At forty-five degrees, tan is one—so Height equals Shadow instantly! "
                    "And as the compass sweeps up to sixty degrees, tan jumps to root three!"
                    if not is_hinglish
                    else "Ab dekhiye hamara compass kaise woh TEEN golden angles draw karta hai jinse 95 percent board sawal solve hote hain! Thirty degree par one by root three, forty-five degree par Height aur Shadow bilkul barabar, aur sixty degree par seedha root three!"
                ),
                "image_3d_prompt": "Vibrant sunny 3D school maths tabletop model: a bright red clock tower standing vertically on a neat green courtyard board with three color-coded yellow, blue, and emerald right-triangle beams touching three ground pegs at short, medium, and long shadow distances, bright Pixar educational lighting, zero text, zero faces.",
                "google_flow_veo_prompt": "Smooth orbital camera around a sunny 3D red clock tower casting three glowing cyan, yellow, and emerald triangle rays onto ground pegs at 30, 45, and 60 degrees.",
                "fallback_plate": "scene_02_16x9.jpg",
            },
            {
                "scene_id": 3,
                "act_badge": ACT_BADGE_LABELS[3],
                "target_angle_deg": 60,
                "headline": "5-SEC BOSS CHALLENGE!",
                "concept_takeaway": "Walking closer from 30° to 60°? Distance walked is ALWAYS twice the remaining base!",
                "formula_badge": "d = 2x (Walked)   |   Base = x (Half!)   |   h = x√3",
                "formula_parts": [
                    {"label": "1. WALKED (30->60)", "expr": "Walked Distance d = 2x"},
                    {"label": "2. REMAINING BASE", "expr": "Inner Base x = d / 2 (Half!)"},
                    {"label": "3. 5-SEC BOSS ANSWER", "expr": "Tower Height h = (d/2) × √3"},
                ],
                "quick_tip": "30° → 60° Topper Trick: Walked 40m closer? Remaining base is half (20m), Height = 20√3 m!",
                "narration": (
                    "Five-second Board Exam Boss Challenge—start the timer! You walk forty metres closer to a tower and the angle jumps from thirty to sixty degrees. "
                    "Don't touch long equations! When thirty becomes sixty, the remaining base is ALWAYS exact half—twenty metres—and tower height is twenty root three metres in five seconds flat!"
                    if not is_hinglish
                    else "Five-second Board Exam Boss Challenge—timer shuru! Aap tower ki taraf 40 metre chalte hain aur angle 30 se 60 degree ho jata hai! Lambe equations chhodiye—baca hua base hamesha aadha yaani 20 metre hota hai, aur height seedha 20 root 3 metre!"
                ),
                "image_3d_prompt": "Crisp colorful 3D classroom demonstration on a sunlit desk: a tall royal-blue communication tower on the right with two bright yellow milestone pins on a straight road moving closer to the tower base, connected by clean red and emerald diagonal beams forming nested right triangles, zero text, zero faces.",
                "google_flow_veo_prompt": "Fast energetic camera glide along a bright 3D tabletop road as two glowing milestone pins lock nested 30-degree and 60-degree laser triangles onto a tall royal-blue tower.",
                "fallback_plate": "scene_03_16x9.jpg",
            },
            {
                "scene_id": 4,
                "act_badge": ACT_BADGE_LABELS[4],
                "target_angle_deg": 45,
                "headline": "EXAM TRAP + SUBSCRIBE!",
                "concept_takeaway": "Always add Observer Eye-Height (+1.5m) to Triangle Height (h) + Subscribe to TopperLab!",
                "formula_badge": "Total Height (H) = Triangle Height (h) + Observer Eye-Height",
                "formula_parts": [
                    {"label": "1. TRIANGLE HEIGHT (h)", "expr": "Upper Triangle h = B × tan θ"},
                    {"label": "2. OBSERVER EYE (+1.5m)", "expr": "+ Boy/Stand Height (1.5 m)"},
                    {"label": "3. FULL-MARKS TOTAL (H)", "expr": "Total H = h + 1.5 m (Locked!)"},
                ],
                "quick_tip": "Smash SUBSCRIBE + Ring the Bell 🔔 & Download the Free 1-Page Formula Sheet Below!",
                "narration": (
                    "Warning—never lose your final mark to the number-one board exam trap! "
                    "When a student's height like one point five metres is given, your triangle starts at eye level—so ALWAYS add that one point five metres at the end! "
                    "Smash that red Subscribe button, ring the notification bell, and grab the free one-page Formula Sheet below!"
                    if not is_hinglish
                    else "Savdhaan—board exam ke number-one trap mein apna aakhri mark mat gawana! Jab student ki height 1.5 metre di ho, toh aakhir mein 1.5 metre jodna mat bhoolna! Abhi red Subscribe button dabayein, bell icon bajayein, aur neeche se free Formula Sheet download karein!"
                ),
                "image_3d_prompt": "Cheerful sunlit 3D classroom model: a colorful miniature viewing stand on the left facing a tall yellow-and-red apartment tower on the right, showing a clear elevated horizontal green platform line and a bright golden star trophy on the desk, Pixar educational style, zero text, zero faces.",
                "google_flow_veo_prompt": "Cheerful sunlit 3D classroom model zooming from an elevated green observer platform to a tall apartment tower and a gleaming golden trophy.",
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
        f"FOUNDATION COMPLETE SYLLABUS CHAPTER VIDEO ('{topic_title}'): Cover the ENTIRE {selected_board} {target_class_label} {target_subject_label} chapter '{clean_chapter}' using the 4-Act Big-Channel Retention Format (3Blue1Brown + Don't Memorise + Dear Sir + Next Toppers): "
        f"(Scene 1 — ACT 1 HOOK & ? PUZZLE) Open with an irresistible counter-intuitive real-life question or exam mystery hook; "
        f"(Scene 2 — ACT 2 VISUAL PROOF & COMPASS ARCS) Step-by-step geometric/visual breakdown where lines, angles, and circles connect 1-to-1 with the formula portions; "
        f"(Scene 3 — ACT 3 5-SEC BOSS CLIMAX) High-energy 5-second board exam numerical challenge solved using a topper ratio shortcut; "
        f"(Scene 4 — ACT 4 #1 EXAM TRAP + SUBSCRIBE CTA) Expose the #1 silly exam mistake, lock full marks, and explicitly invite students to smash Subscribe, ring the notification bell, and download the Free 1-Page Formula Sheet!"
        if is_syllabus
        else f"POST-FOUNDATION BOOSTER VIDEO ({video_category.upper()} — '{topic_title}'): Deliver ultra-actionable topper study hacks, 5-second exam shortcuts, sign-convention tricks, and super-memory mnemonics for {selected_board} {target_class_label} {target_subject_label} ('{clean_chapter}') across the 4-Act Retention Format (Hook -> Visual Proof -> 5-Sec Climax Challenge -> Exam Trap + Subscribe CTA)."
    )

    ai_prompt = (
        f"Create an exciting, high-retention faceless educational video blueprint for TopperLab.\n"
        f"Topic Title: {topic_title}\n"
        f"Board / Class / Subject / Chapter: {selected_board} • {target_class_label} • {target_subject_label} • {clean_chapter}\n"
        f"Mission: {mode_brief}\n"
        f"Expressive Narration Style: {voice_cfg['script_instruction']}\n"
        f"Visual Model Style (for image_3d_prompt ONLY — NO dark sci-fi!): {theme_cfg['style_prompt']}\n"
        f"Number of Scenes: {scene_count}\n"
        f"CRITICAL RULES:\n"
        f"1. STRICTLY FORBIDDEN: NEVER write the word '3D' or '3d' anywhere in `title_variations`, `thumb_hook_3words`, `short_hook_3words`, `thumb_sub_tagline`, `headline`, `concept_takeaway`, `formula_badge`, `formula_parts`, `quick_tip`, or `narration`! (Only use 3D visual rendering terms inside `image_3d_prompt` and `google_flow_veo_prompt`).\n"
        f"2. Every `image_3d_prompt` and `google_flow_veo_prompt` MUST describe bright, colorful, everyday classroom/real-life visual models (lighthouses, towers, bicycles, cricket balls, magnets, batteries, prisms, water pipes, heart models, globes, geometry blocks) on a bright studio desk — NEVER dark sci-fi labs, ZERO human faces, and ZERO text/letters inside the raw image.\n"
        f"3. Follow the 4-Act Big-Channel Format: Scene 1 = Curiosity Hook ('Wait a second—can you...?'), Scene 2 = Step-by-Step Visual Proof, Scene 3 = 5-Second Board Exam Boss Challenge ('Start the timer!'), Scene 4 = #1 Exam Trap Fix + Explicit Call to Subscribe, Like, Ring the Bell & Download the Free 1-Page Formula Sheet!\n"
        f"4. Every scene MUST include an accurate syllabus `formula_badge` (max 52 chars), `formula_parts` (an array of 3 objects `[{{'label': '1. ...', 'expr': '...'}}, {{'label': '2. ...', 'expr': '...'}}, {{'label': '3. ...', 'expr': '...'}}]` breaking the formula into 3 portions that highlight one-by-one as lines/angles draw!), AND a punchy `quick_tip` (max 68 chars).\n"
        f"Return JSON with keys:\n"
        f"- title_variations (array of 3 clean student titles — first one matching '{topic_title}', ZERO '3D' text)\n"
        f"- thumb_hook_3words (2 to 3 punchy words for the Yellow+Red thumbnail heading, e.g. '{default_hook}' or '5-SEC TRIG HACK!')\n"
        f"- short_hook_3words (2 to 3 punchy words for 9:16 cover, ZERO '3D' text)\n"
        f"- thumb_sub_tagline (3 to 5 words, e.g. 'ALL FORMULAS + EXAM HACKS', ZERO '3D' text)\n"
        f"- thumbnail_16x9_prompt (bright classroom 3D model positioned on RIGHT half of 16:9 frame, clean left side, zero raw text, zero faces)\n"
        f"- short_cover_9x16_prompt (bright classroom 3D model positioned in lower-center of 9:16 frame, clean top area, zero raw text, zero faces)\n"
        f"- scenes: array of {scene_count} objects with keys: scene_id, headline (max 3 words, no '3D'), concept_takeaway (max 72 chars, no '3D'), formula_badge (max 52 chars, no '3D'), formula_parts (array of 3 objects with keys label and expr), target_angle_deg (integer 30, 45, or 60), quick_tip (max 68 chars, no '3D'), narration (40-54 expressive spoken words, no '3D'), image_3d_prompt, google_flow_veo_prompt."
    )
    blueprint = call_gemini_json(ai_prompt, fallback_blueprint)
    if not isinstance(blueprint, dict) or not blueprint.get("scenes"):
        blueprint = fallback_blueprint

    clean_vars = [strip_3d_text(t) for t in blueprint.get("title_variations", fallback_blueprint["title_variations"]) if strip_3d_text(t)]
    if not clean_vars or clean_vars[0].lower() != topic_title.lower():
        clean_vars = [topic_title] + [v for v in clean_vars if v.lower() != topic_title.lower()]
    blueprint["title_variations"] = clean_vars[:3]

    plate_cycle = ["scene_01_16x9.jpg", "scene_02_16x9.jpg", "scene_03_16x9.jpg", "scene_04_16x9.jpg"]
    angle_cycle = [45, 60, 60, 45]
    for idx, sc in enumerate(blueprint["scenes"]):
        sid_num = idx + 1
        sc["scene_id"] = sid_num
        sc["act_badge"] = ACT_BADGE_LABELS.get(sid_num, f"ACT {sid_num}: KEY CONCEPT")
        sc.setdefault("fallback_plate", plate_cycle[idx % len(plate_cycle)])
        def_sc = default_scenes[idx % len(default_scenes)]
        sc["headline"] = strip_3d_text(sc.get("headline", "")) or def_sc["headline"]
        sc["concept_takeaway"] = strip_3d_text(sc.get("concept_takeaway", "")) or def_sc["concept_takeaway"]
        sc["formula_badge"] = strip_3d_text(sc.get("formula_badge", "")) or def_sc["formula_badge"]
        sc["quick_tip"] = strip_3d_text(sc.get("quick_tip", "")) or def_sc["quick_tip"]
        sc["narration"] = strip_3d_text(sc.get("narration", "")) or def_sc["narration"]
        sc["formula_parts"] = _parse_formula_into_three_portions(
            sc["formula_badge"],
            sc["headline"],
            sc.get("formula_parts") or def_sc.get("formula_parts"),
        )
        try:
            ang = int(sc.get("target_angle_deg") or def_sc.get("target_angle_deg") or angle_cycle[idx % 4])
            sc["target_angle_deg"] = ang if ang in (30, 45, 60) else angle_cycle[idx % 4]
        except Exception:
            sc["target_angle_deg"] = angle_cycle[idx % 4]

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


def _add_mechanical_ticks(
    buf_l: List[float],
    buf_r: List[float],
    sr: int,
    start_sec: float,
    dur_sec: float = 1.6,
    tick_rate_hz: float = 13.0,
    base_freq: float = 1280.0,
    amp: float = 0.22,
) -> None:
    """Crisp mechanical ruler/compass ratchet clicks (8MXN6QjPJqc tactile ASMR line-drawing sound)."""
    n_total = len(buf_l)
    step_sec = 1.0 / max(2.0, tick_rate_hz)
    n_ticks = max(1, int(dur_sec / step_sec))
    for idx_t in range(n_ticks):
        t0 = start_sec + idx_t * step_sec
        i0 = max(0, int(t0 * sr))
        click_len = min(int(0.018 * sr), n_total - i0)
        if click_len <= 0:
            break
        f_tick = base_freq * (1.0 + 0.03 * (idx_t % 4))
        pan = 0.35 + 0.30 * (idx_t / float(max(1, n_ticks)))
        for k in range(click_len):
            t = k / float(sr)
            env = math.exp(-210.0 * t)
            v = amp * env * (0.75 * math.sin(2.0 * math.pi * f_tick * t) + 0.25 * math.sin(2.0 * math.pi * (f_tick * 2.4) * t))
            buf_l[i0 + k] += v * (1.0 - 0.35 * pan)
            buf_r[i0 + k] += v * (0.65 + 0.35 * pan)


def _add_curiosity_chirp(
    buf_l: List[float],
    buf_r: List[float],
    sr: int,
    start_sec: float,
    dur_sec: float = 0.28,
    amp: float = 0.32,
) -> None:
    """Playful upward pitch-bend chirp for the '?' puzzle badge in Scene 1 (8MXN6QjPJqc hook cue)."""
    n_total = len(buf_l)
    i0 = max(0, int(start_sec * sr))
    n_len = min(int(dur_sec * sr), n_total - i0)
    if n_len <= 0:
        return
    phase = 0.0
    for k in range(n_len):
        u = k / float(n_len)
        env = math.sin(math.pi * u) ** 0.85
        freq = 390.0 + 690.0 * (u ** 1.5)
        phase += 2.0 * math.pi * freq / sr
        v = amp * env * (0.82 * math.sin(phase) + 0.18 * math.sin(2.0 * phase))
        buf_l[i0 + k] += v * 0.85
        buf_r[i0 + k] += v * 0.95


def _add_laser_sweep(
    buf_l: List[float],
    buf_r: List[float],
    sr: int,
    start_sec: float,
    dur_sec: float = 0.55,
    f_start: float = 780.0,
    f_end: float = 290.0,
    amp: float = 0.26,
) -> None:
    """Warm synth laser beam hum when the red sight-line slices across the triangle (8MXN6QjPJqc 0:30)."""
    n_total = len(buf_l)
    i0 = max(0, int(start_sec * sr))
    n_len = min(int(dur_sec * sr), n_total - i0)
    if n_len <= 0:
        return
    phase = 0.0
    for k in range(n_len):
        u = k / float(n_len)
        env = math.sin(math.pi * u) ** 1.15
        freq = f_start + (f_end - f_start) * (u ** 0.75)
        phase += 2.0 * math.pi * freq / sr
        v = amp * env * (0.70 * math.sin(phase) + 0.30 * math.sin(1.5 * phase))
        buf_l[i0 + k] += v * (0.9 - 0.3 * u)
        buf_r[i0 + k] += v * (0.6 + 0.3 * u)


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
      1. 4-Act Dynamic Marimba + Warm Bass + Shaker BGM (auto-ducked under voice!)
      2. Tactile ASMR Geometry SFX (inspired by reference Short 8MXN6QjPJqc):
         - Mechanical ruler/ratchet clicks as green markers 1, 2, 3 and Base line draw
         - Playful '?' curiosity chirp on Scene 1 hook
         - Warm laser beam hum on diagonal sight-ray sweep
         - 3 Ascending Crystal Chimes synced 1-to-1 with Formula Portion 1, 2, and 3 highlights
         - High-energy 5-second countdown ticks + victory chord in Scene 3 (Climax)
         - Mouse-click + Golden YouTube Notification Bell Ding in Scene 4 (Subscribe CTA)!
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

    # 1. 4-Act Student Curiosity Groove (Scene 3 Climax shifts slightly faster/brighter!)
    bpm = 122.0 if scene_id == 3 else 116.0
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
        _add_pluck_note(bgm_l, bgm_r, sr, t0, note_f, dur_sec=0.31, amp=0.35, pan=pan)

        if step % 2 == 0:
            _add_pluck_note(bgm_l, bgm_r, sr, t0, bass_f, dur_sec=0.48, amp=0.37, pan=0.5)
        if step % 2 == 1:
            sh_i0 = int(t0 * sr)
            sh_len = min(int(0.032 * sr), n_total - sh_i0)
            st_seed = 4242 + step * 97
            for k in range(max(0, sh_len)):
                st_seed = (1103515245 * st_seed + 12345) & 0x7FFFFFFF
                nv = ((st_seed / 1073741824.0) - 1.0) * math.exp(-95.0 * (k / float(sr))) * 0.085
                bgm_l[sh_i0 + k] += nv
                bgm_r[sh_i0 + k] += nv

    # 2. Tactile ASMR Geometry SFX Synced to Visual Drawing Phases (u = t / duration_sec)
    _add_swept_whoosh(sfx_l, sfx_r, sr, 0.02, dur_sec=0.28, f_start=190.0, f_end=560.0, amp=0.30)

    # Phase 1 (u = 0.06..0.34): Green markers 1, 2, 3 + Cyan Base line drawing + Portion 1 Highlight Chime
    t_p1 = max(0.25, duration_sec * 0.07)
    _add_pluck_note(sfx_l, sfx_r, sr, t_p1, 523.25, dur_sec=0.26, amp=0.38, pan=0.28)
    _add_pluck_note(sfx_l, sfx_r, sr, t_p1 + 0.06, 659.25, dur_sec=0.30, amp=0.40, pan=0.35)
    _add_mechanical_ticks(sfx_l, sfx_r, sr, start_sec=duration_sec * 0.09, dur_sec=min(1.8, duration_sec * 0.20), tick_rate_hz=12.0, base_freq=1180.0, amp=0.22)

    if scene_id == 1:
        # Playful '?' puzzle pop chirp in Act 1 Hook
        _add_curiosity_chirp(sfx_l, sfx_r, sr, start_sec=duration_sec * 0.22, dur_sec=0.26, amp=0.34)

    # Phase 2 (u = 0.36..0.66): Yellow Height line + 90-deg lock + Portion 2 Highlight Chime + Laser sight sweep
    t_p2 = duration_sec * 0.36
    _add_pluck_note(sfx_l, sfx_r, sr, t_p2, 659.25, dur_sec=0.26, amp=0.39, pan=0.48)
    _add_pluck_note(sfx_l, sfx_r, sr, t_p2 + 0.06, 783.99, dur_sec=0.32, amp=0.41, pan=0.52)
    _add_laser_sweep(sfx_l, sfx_r, sr, start_sec=duration_sec * 0.41, dur_sec=0.52, f_start=820.0, f_end=310.0, amp=0.25)

    # Phase 3 (u = 0.66..0.96): Compass angle arc scratch + Portion 3 Highlight Chime + Quick Hack Ding
    t_p3 = duration_sec * 0.66
    _add_pluck_note(sfx_l, sfx_r, sr, t_p3, 783.99, dur_sec=0.26, amp=0.40, pan=0.65)
    _add_pluck_note(sfx_l, sfx_r, sr, t_p3 + 0.06, 1046.50, dur_sec=0.34, amp=0.43, pan=0.70)
    _add_pluck_note(sfx_l, sfx_r, sr, t_p3 + 0.12, 1318.51, dur_sec=0.38, amp=0.38, pan=0.75)
    _add_mechanical_ticks(sfx_l, sfx_r, sr, start_sec=duration_sec * 0.68, dur_sec=min(1.2, duration_sec * 0.14), tick_rate_hz=16.0, base_freq=1480.0, amp=0.20)

    if scene_id == 3:
        # Climax 5-second Boss Countdown Ticks + Triumphant Victory Chord
        t_cd_start = duration_sec * 0.56
        cd_span = max(1.8, duration_sec * 0.30)
        for c_idx in range(6):
            tc = t_cd_start + c_idx * (cd_span / 5.5)
            f_beep = 880.0 if c_idx < 5 else 1318.51
            _add_pluck_note(sfx_l, sfx_r, sr, tc, f_beep, dur_sec=0.16 if c_idx < 5 else 0.45, amp=0.36 if c_idx < 5 else 0.46, pan=0.5)

    if scene_id == 4:
        # Scene 4 Subscribe Button Mouse-Click + YouTube Golden Notification Bell Ding!
        t_click = duration_sec * 0.77
        _add_mechanical_ticks(sfx_l, sfx_r, sr, start_sec=t_click, dur_sec=0.05, tick_rate_hz=35.0, base_freq=1750.0, amp=0.36)
        _add_pluck_note(sfx_l, sfx_r, sr, t_click + 0.07, 1046.50, dur_sec=0.42, amp=0.45, pan=0.55)
        _add_pluck_note(sfx_l, sfx_r, sr, t_click + 0.14, 1567.98, dur_sec=0.58, amp=0.48, pan=0.60)
        _add_pluck_note(sfx_l, sfx_r, sr, t_click + 0.22, 2093.00, dur_sec=0.65, amp=0.40, pan=0.50)

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
        bgm_gains[w_idx] = 0.21 if peak > 1800 else 0.36

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
        ml = int(vl + end_fade * scale_pcm * (g_bgm * bgm_l[i] + 0.46 * sfx_l[i]))
        mr = int(vr + end_fade * scale_pcm * (g_bgm * bgm_r[i] + 0.46 * sfx_r[i]))
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


def _clamp01(v: float) -> float:
    return 0.0 if v <= 0.0 else (1.0 if v >= 1.0 else v)


def _ease_out_cubic(v: float) -> float:
    c = _clamp01(v)
    return 1.0 - ((1.0 - c) ** 3)


def _draw_dashed_line(
    draw: ImageDraw.ImageDraw,
    p0: tuple[int, int],
    p1: tuple[int, int],
    fill: tuple[int, int, int, int],
    width: int = 3,
    dash_px: int = 12,
    gap_px: int = 8,
) -> None:
    x0, y0 = p0
    x1, y1 = p1
    dist = math.hypot(x1 - x0, y1 - y0)
    if dist < 2.0:
        return
    ux = (x1 - x0) / dist
    uy = (y1 - y0) / dist
    pos = 0.0
    while pos < dist:
        e = min(dist, pos + dash_px)
        draw.line(
            [(int(x0 + ux * pos), int(y0 + uy * pos)), (int(x0 + ux * e), int(y0 + uy * e))],
            fill=fill,
            width=width,
        )
        pos += dash_px + gap_px


def _render_animated_geometry_and_formula_scene_mp4(
    scene: Dict[str, Any],
    target_mp4: Path,
    wav_master: Path,
    dur_sec: float,
    src_img_path: Path,
    saved_motion_mp4: Path | None,
    class_badge_text: str,
    is_vertical: bool = False,
) -> Path:
    """
    Renders a live frame-by-frame (20 fps -> 25 fps) interactive geometry & formula studio canvas
    inspired by reference Short https://www.youtube.com/shorts/8MXN6QjPJqc and composited with
    Google Flow / Veo 3.1 live B-roll (`saved_motion_mp4`):
      - Vertical green guide lines with rounded green badges `1`, `2`, `3`
      - Unfolding neon circle & Cyan Horizontal Base (`Adjacent = B`)
      - Playful `?` curiosity badge transforming into Yellow Vertical Height (`Opposite = H`) + `90°` square
      - Red Laser Line-of-Sight + Metallic Compass scratching Angle Arc `θ` with `*` intersection markers
      - Real-time 3-Portion Formula Highlighter Bar where Portion 1 (Cyan), Portion 2 (Yellow), and
        Portion 3 (Emerald/Coral) light up in sync with the geometry being drawn!
      - Scene 3: 5-Second Board Exam Boss Countdown Ring + Concentric Ratio Waves (`30°-45°-60°`)
      - Scene 4: #1 Exam Trap (`+1.5m` Eye-Height) + Animated YouTube `SUBSCRIBE -> SUBSCRIBED + BELL` End-Screen CTA!
    """
    ffmpeg_bin = get_ffmpeg_exe()
    W, H = (1080, 1920) if is_vertical else (1920, 1080)
    fps = 20
    n_frames = max(40, int(math.ceil(dur_sec * fps)))

    sid = int(scene.get("scene_id", 1))
    act_badge = _sanitize_drawable_text(scene.get("act_badge") or ACT_BADGE_LABELS.get(sid, f"ACT {sid}: CONCEPT")).upper()
    headline = _sanitize_drawable_text(strip_3d_text(scene.get("headline", "KEY CONCEPT"))).upper()
    takeaway = _sanitize_drawable_text(strip_3d_text(scene.get("concept_takeaway", "")))
    quick_tip = _sanitize_drawable_text(strip_3d_text(scene.get("quick_tip", "")))
    formula_badge = _sanitize_drawable_text(strip_3d_text(scene.get("formula_badge", "")))
    formula_parts = _parse_formula_into_three_portions(formula_badge, headline, scene.get("formula_parts"))
    target_angle = int(scene.get("target_angle_deg") or (60 if sid in (2, 3) else 45))

    has_broll = bool(saved_motion_mp4 and saved_motion_mp4.exists() and saved_motion_mp4.stat().st_size > 1000)

    # Layout coordinates for 16:9 (1920x1080) vs 9:16 (1080x1920)
    if not is_vertical:
        broll_box = (42, 232, 742, 772)      # 700x540 Left B-Roll Viewport
        stage_box = (768, 232, 1878, 912)    # 1110x680 Right Live Geometry & Compass Stage
    else:
        broll_box = (54, 412, 1026, 842)     # 972x430 Top B-Roll Viewport
        stage_box = (54, 862, 1026, 1446)    # 972x584 Center Live Geometry & Compass Stage

    bw_v = broll_box[2] - broll_box[0]
    bh_v = broll_box[3] - broll_box[1]

    # Pre-load static B-roll fallback image fitted to broll_box
    if src_img_path.exists():
        broll_static_img = ImageOps.fit(Image.open(src_img_path).convert("RGBA"), (bw_v, bh_v), method=Image.Resampling.LANCZOS)
    else:
        broll_static_img = Image.new("RGBA", (bw_v, bh_v), (20, 32, 58, 255))

    # Build static base studio canvas with subtle coordinate grid so per-frame drawing is ultra fast
    base_canvas = Image.new("RGBA", (W, H), (10, 16, 30, 255))
    bdraw = ImageDraw.Draw(base_canvas)

    # Studio grid lines inside stage_box
    sx0, sy0, sx1, sy1 = stage_box
    bdraw.rounded_rectangle([sx0, sy0, sx1, sy1], radius=24, fill=(13, 22, 40, 255), outline=(38, 58, 92, 255), width=3)
    for gx in range(sx0 + 55, sx1, 55):
        bdraw.line([(gx, sy0 + 4), (gx, sy1 - 4)], fill=(22, 36, 62, 255), width=1)
    for gy in range(sy0 + 55, sy1, 55):
        bdraw.line([(sx0 + 4, gy), (sx1 - 4, gy)], fill=(22, 36, 62, 255), width=1)

    # B-Roll outer frame
    bx0, by0, bx1, by1 = broll_box
    bdraw.rounded_rectangle([bx0 - 4, by0 - 4, bx1 + 4, by1 + 4], radius=22, fill=(15, 23, 42, 255), outline=(56, 189, 248, 235), width=4)

    # Top Header Bar: Class Pill + 4-Act Badge + Headline
    cls_clean = _sanitize_drawable_text(class_badge_text).upper()
    f_hdr = _load_studio_font(25 if not is_vertical else 26, weight="bold")
    f_act = _load_studio_font(24 if not is_vertical else 24, weight="bold")
    if not is_vertical:
        bb_c = bdraw.textbbox((0, 0), cls_clean, font=f_hdr)
        cw_p = (bb_c[2] - bb_c[0]) + 32
        bdraw.rounded_rectangle([42, 22, 42 + cw_p, 72], radius=14, fill=(220, 38, 38, 255), outline=(255, 255, 255, 245), width=3)
        bdraw.text((42 + 16, 34 - bb_c[1]), cls_clean, font=f_hdr, fill=(255, 255, 255, 255))

        act_str = f"{act_badge}  •  {headline}"
        bb_a = bdraw.textbbox((0, 0), act_str, font=f_hdr)
        aw_p = (bb_a[2] - bb_a[0]) + 36
        ax0 = 42 + cw_p + 12
        bdraw.rounded_rectangle([ax0, 22, ax0 + aw_p, 72], radius=14, fill=(15, 23, 42, 255), outline=(255, 214, 0, 240), width=3)
        bdraw.text((ax0 + 18, 34 - bb_a[1]), act_str, font=f_hdr, fill=(255, 214, 0, 255))

        src_tag = "GOOGLE FLOW / VEO 3.1 + LIVE GEOMETRY" if has_broll else "LIVE GEOMETRY + COMPASS ENGINE"
        bb_s = bdraw.textbbox((0, 0), src_tag, font=f_act)
        sw_p = (bb_s[2] - bb_s[0]) + 30
        bdraw.rounded_rectangle([W - 42 - sw_p, 24, W - 42, 70], radius=13, fill=(6, 78, 59, 255), outline=(16, 185, 129, 255), width=2)
        bdraw.text((W - 42 - sw_p + 15, 35 - bb_s[1]), src_tag, font=f_act, fill=(167, 243, 208, 255))
    else:
        bb_c = bdraw.textbbox((0, 0), cls_clean, font=f_hdr)
        cw_p = (bb_c[2] - bb_c[0]) + 34
        cx_p = (W - cw_p) // 2
        bdraw.rounded_rectangle([cx_p, 56, cx_p + cw_p, 104], radius=14, fill=(220, 38, 38, 255), outline=(255, 255, 255, 245), width=3)
        bdraw.text((cx_p + 17, 68 - bb_c[1]), cls_clean, font=f_hdr, fill=(255, 255, 255, 255))

        act_str = f"{act_badge} • {headline}"[:44]
        bb_a = bdraw.textbbox((0, 0), act_str, font=f_act)
        aw_p = min(W - 60, (bb_a[2] - bb_a[0]) + 32)
        ax0 = (W - aw_p) // 2
        bdraw.rounded_rectangle([ax0, 112, ax0 + aw_p, 156], radius=12, fill=(15, 23, 42, 255), outline=(255, 214, 0, 240), width=3)
        bdraw.text((ax0 + 16, 122 - bb_a[1]), act_str, font=f_act, fill=(255, 214, 0, 255))

    # Bottom Takeaway Strip on Base Canvas
    f_take = _load_studio_font(27 if not is_vertical else 28, weight="bold")
    if not is_vertical:
        t_lines = _wrap_text_pixels(bdraw, takeaway, f_take, max_px=W - 180, max_lines=2)
        th_box = 62 if len(t_lines) == 1 else 94
        ty0 = H - th_box - 20
        bdraw.rounded_rectangle([42, ty0, W - 42, ty0 + th_box], radius=16, fill=(15, 23, 42, 245), outline=(56, 189, 248, 210), width=3)
        bdraw.rounded_rectangle([42, ty0, 56, ty0 + th_box], radius=8, fill=(255, 214, 0, 255))
        yc = ty0 + 14
        for ln in t_lines:
            lb = bdraw.textbbox((0, 0), ln, font=f_take)
            bdraw.text((74, yc - lb[1]), ln, font=f_take, fill=(248, 250, 252, 255))
            yc += (lb[3] - lb[1]) + 8
    else:
        t_lines = _wrap_text_pixels(bdraw, takeaway, f_take, max_px=W - 140, max_lines=2)
        th_box = 68 if len(t_lines) == 1 else 106
        ty0 = 1568
        bdraw.rounded_rectangle([54, ty0, W - 54, ty0 + th_box], radius=18, fill=(15, 23, 42, 245), outline=(255, 214, 0, 225), width=3)
        yc = ty0 + 14
        for ln in t_lines:
            lb = bdraw.textbbox((0, 0), ln, font=f_take)
            lx = (W - (lb[2] - lb[0])) // 2
            bdraw.text((lx, yc - lb[1]), ln, font=f_take, fill=(255, 255, 255, 255))
            yc += (lb[3] - lb[1]) + 8

    # Pre-cache fonts for fast per-frame rendering
    f_p_lbl = _load_studio_font(19 if not is_vertical else 18, weight="bold")
    f_p_exp = _load_studio_font(28 if not is_vertical else 24, weight="bold")
    f_num_badge = _load_studio_font(24, weight="bold")
    f_stage_lbl = _load_studio_font(25 if not is_vertical else 23, weight="bold")
    f_big_ang = _load_studio_font(34 if not is_vertical else 31, weight="bold")
    f_qmark = _load_studio_font(62 if not is_vertical else 54, weight="heavy")
    f_hack_hdr = _load_studio_font(22, weight="bold")
    f_hack_txt = _load_studio_font(25 if not is_vertical else 24, weight="bold")
    f_cta_big = _load_studio_font(34 if not is_vertical else 31, weight="bold")
    f_cta_sub = _load_studio_font(24 if not is_vertical else 22, weight="bold")

    part_colors = [
        ((0, 229, 255, 255), (8, 47, 73, 245), (186, 230, 253, 255)),     # Portion 1: Neon Cyan (Base)
        ((255, 214, 0, 255), (66, 32, 6, 245), (254, 240, 138, 255)),     # Portion 2: Electric Yellow (Height)
        ((16, 185, 129, 255), (6, 78, 59, 245), (167, 243, 208, 255)),    # Portion 3: Emerald Green (Angle/Result)
    ]

    # Build FFmpeg command (if saved_motion_mp4 exists, composite moving B-roll under our transparent B-roll viewport!)
    target_mp4.parent.mkdir(parents=True, exist_ok=True)
    if has_broll:
        # Input 0: rawvideo RGBA stream from Python pipe
        # Input 1: looped Veo 3.1 / Google Flow MP4 clip scaled to broll_box
        # Input 2: master audio WAV
        fc = (
            f"[0:v]fps=25,format=rgba[fg];"
            f"[1:v]scale={bw_v}:{bh_v}:force_original_aspect_ratio=increase,crop={bw_v}:{bh_v},fps=25,format=rgba[broll];"
            f"color=c=black:s={W}x{H}:r=25,format=rgba[blank];"
            f"[blank][broll]overlay={bx0}:{by0}:shortest=1[broll_pad];"
            f"[broll_pad][fg]overlay=0:0:shortest=1,format=yuv420p[vout]"
        )
        cmd = [
            ffmpeg_bin,
            "-y",
            "-loglevel",
            "error",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "rgba",
            "-s",
            f"{W}x{H}",
            "-r",
            str(fps),
            "-i",
            "-",
            "-stream_loop",
            "-1",
            "-i",
            str(saved_motion_mp4),
            "-i",
            str(wav_master),
            "-t",
            f"{dur_sec:.2f}",
            "-filter_complex",
            fc,
            "-map",
            "[vout]",
            "-map",
            "2:a:0",
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
    else:
        cmd = [
            ffmpeg_bin,
            "-y",
            "-loglevel",
            "error",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "rgba",
            "-s",
            f"{W}x{H}",
            "-r",
            str(fps),
            "-i",
            "-",
            "-i",
            str(wav_master),
            "-t",
            f"{dur_sec:.2f}",
            "-vf",
            "fps=25,format=yuv420p",
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
        ]

    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    try:
        assert proc.stdin is not None
        for f_idx in range(n_frames):
            u = f_idx / float(max(1, n_frames - 1))
            t_sec = u * dur_sec

            frame = base_canvas.copy()
            draw = ImageDraw.Draw(frame)

            # Determine which of the 3 Formula Portions is actively highlighted right now
            if u < 0.36:
                active_part = 0
                part_pulse = _ease_out_cubic((u - 0.04) / 0.18)
            elif u < 0.66:
                active_part = 1
                part_pulse = _ease_out_cubic((u - 0.36) / 0.18)
            else:
                active_part = 2
                part_pulse = _ease_out_cubic((u - 0.66) / 0.18)

            # ----------------------------------------------------------------
            # A. TOP 3-PORTION FORMULA HIGHLIGHTER BAR (8MXN6QjPJqc Style)
            # ----------------------------------------------------------------
            portion_centers: List[tuple[int, int]] = []
            if not is_vertical:
                bar_y0, bar_y1 = 86, 212
                gap = 18
                total_w = W - 84 - 2 * gap
                pw = total_w // 3
                for p_i in range(3):
                    px0 = 42 + p_i * (pw + gap)
                    px1 = px0 + pw
                    p_info = formula_parts[p_i]
                    b_col, bg_active, txt_col = part_colors[p_i]
                    is_act = p_i == active_part
                    is_done = p_i < active_part

                    box_y0 = bar_y0 - (4 if is_act else 0)
                    box_y1 = bar_y1 + (4 if is_act else 0)
                    fill_c = bg_active if is_act else ((17, 28, 48, 245) if is_done else (15, 23, 42, 225))
                    out_c = b_col if is_act else ((b_col[0], b_col[1], b_col[2], 150) if is_done else (51, 65, 85, 190))
                    out_w = 5 if is_act else 2

                    if is_act:
                        draw.rounded_rectangle([px0 - 4, box_y0 - 4, px1 + 4, box_y1 + 4], radius=20, outline=(b_col[0], b_col[1], b_col[2], 110), width=4)
                    draw.rounded_rectangle([px0, box_y0, px1, box_y1], radius=16, fill=fill_c, outline=out_c, width=out_w)

                    tag_txt = f"{p_info['label']}  {'[ACTIVE]' if is_act else ('[LOCKED]' if is_done else '')}".strip()
                    bb_tg = draw.textbbox((0, 0), tag_txt, font=f_p_lbl)
                    tg_w = min(pw - 32, (bb_tg[2] - bb_tg[0]) + 28)
                    draw.rounded_rectangle([px0 + 16, box_y0 + 12, px0 + 16 + tg_w, box_y0 + 42], radius=8, fill=b_col if is_act else (30, 41, 59, 255))
                    draw.text((px0 + 28, box_y0 + 15), tag_txt, font=f_p_lbl, fill=(10, 16, 30, 255) if is_act else b_col)

                    exp_lines = _wrap_text_pixels(draw, p_info["expr"], f_p_exp, max_px=pw - 36, max_lines=1)
                    draw.text((px0 + 20, box_y0 + 54), exp_lines[0], font=f_p_exp, fill=(255, 255, 255, 255) if is_act else txt_col)
                    portion_centers.append(((px0 + px1) // 2, box_y1))
            else:
                # 9:16 Vertical: 3 compact horizontal formula portion cards at y=166..396
                for p_i in range(3):
                    py0 = 168 + p_i * 74
                    py1 = py0 + 66
                    px0, px1 = 54, W - 54
                    p_info = formula_parts[p_i]
                    b_col, bg_active, txt_col = part_colors[p_i]
                    is_act = p_i == active_part
                    is_done = p_i < active_part
                    fill_c = bg_active if is_act else ((17, 28, 48, 245) if is_done else (15, 23, 42, 225))
                    out_c = b_col if is_act else ((b_col[0], b_col[1], b_col[2], 140) if is_done else (51, 65, 85, 190))
                    draw.rounded_rectangle([px0, py0, px1, py1], radius=14, fill=fill_c, outline=out_c, width=4 if is_act else 2)
                    draw.rounded_rectangle([px0 + 14, py0 + 12, px0 + 250, py1 - 12], radius=8, fill=b_col if is_act else (30, 41, 59, 255))
                    draw.text((px0 + 24, py0 + 19), p_info["label"][:20], font=f_p_lbl, fill=(10, 16, 30, 255) if is_act else b_col)
                    draw.text((px0 + 268, py0 + 16), p_info["expr"][:30], font=f_p_exp, fill=(255, 255, 255, 255) if is_act else txt_col)
                    portion_centers.append(((px0 + px1) // 2, py1))

            # ----------------------------------------------------------------
            # B. B-ROLL VIEWPORT (LIVE VEO 3.1 / FLOW VIDEO OR KEN-BURNS PLATE) + LASER HUD
            # ----------------------------------------------------------------
            if has_broll:
                # Punch transparent window so FFmpeg's [broll] layer shows through cleanly!
                draw.rectangle([bx0, by0, bx1, by1], fill=(0, 0, 0, 0))
            else:
                # Smooth Ken-Burns zoom on static 3D classroom plate
                zoom = 1.0 + 0.08 * u
                zw = int(bw_v * zoom)
                zh = int(bh_v * zoom)
                z_img = broll_static_img.resize((zw, zh), resample=Image.Resampling.BILINEAR)
                cx_crop = (zw - bw_v) // 2
                cy_crop = (zh - bh_v) // 2
                frame.paste(z_img.crop((cx_crop, cy_crop, cx_crop + bw_v, cy_crop + bh_v)), (bx0, by0))

            # Draw live geometric sight-lines & green badges 1, 2, 3 directly over the B-Roll viewport!
            b_base_y = by1 - int(bh_v * 0.18)
            b_left_x = bx0 + int(bw_v * 0.14)
            b_right_x = bx1 - int(bw_v * 0.16)
            b_top_y = by0 + int(bh_v * 0.20)

            p_broll_line = _ease_out_cubic((u - 0.05) / 0.25)
            if p_broll_line > 0.02:
                cur_bx = int(b_left_x + (b_right_x - b_left_x) * p_broll_line)
                draw.line([(b_left_x, b_base_y), (cur_bx, b_base_y)], fill=(0, 229, 255, 235), width=5)

            p_broll_h = _ease_out_cubic((u - 0.34) / 0.24)
            if p_broll_h > 0.02:
                cur_by = int(b_base_y - (b_base_y - b_top_y) * p_broll_h)
                draw.line([(b_right_x, b_base_y), (b_right_x, cur_by)], fill=(255, 214, 0, 240), width=5)

            p_broll_ray = _ease_out_cubic((u - 0.42) / 0.24)
            if p_broll_ray > 0.02:
                rx_end = int(b_right_x - (b_right_x - b_left_x) * p_broll_ray)
                ry_end = int(b_top_y + (b_base_y - b_top_y) * p_broll_ray)
                draw.line([(b_right_x, b_top_y), (rx_end, ry_end)], fill=(255, 59, 92, 245), width=5)

            # B-Roll top corner badge
            draw.rounded_rectangle([bx0 + 14, by0 + 14, bx0 + 276, by0 + 50], radius=10, fill=(15, 23, 42, 215), outline=(0, 229, 255, 220), width=2)
            draw.text((bx0 + 24, by0 + 20), "LIVE MODEL B-ROLL", font=f_p_lbl, fill=(0, 229, 255, 255))

            # For 16:9, place the Quick Exam Hack card right below the Left B-Roll Viewport (y=788..912)
            if not is_vertical:
                hk_y0, hk_y1 = 786, 912
                hk_glow = u >= 0.52
                draw.rounded_rectangle(
                    [bx0, hk_y0, bx1, hk_y1],
                    radius=18,
                    fill=(38, 16, 28, 245) if hk_glow else (15, 23, 42, 235),
                    outline=(255, 59, 92, 255) if hk_glow else (71, 85, 105, 200),
                    width=4 if hk_glow else 2,
                )
                draw.rounded_rectangle([bx0 + 16, hk_y0 + 12, bx0 + 265, hk_y0 + 42], radius=8, fill=(220, 38, 38, 255))
                draw.text((bx0 + 26, hk_y0 + 16), "TOPPER EXAM HACK", font=f_hack_hdr, fill=(255, 255, 255, 255))
                hk_lines = _wrap_text_pixels(draw, quick_tip, f_hack_txt, max_px=bw_v - 36, max_lines=2)
                hy_c = hk_y0 + 50
                for hln in hk_lines:
                    draw.text((bx0 + 18, hy_c), hln, font=f_hack_txt, fill=(254, 240, 138, 255) if hk_glow else (226, 232, 240, 255))
                    hy_c += 30
            else:
                # 9:16 Quick Hack strip at y=1456..1556
                hk_y0, hk_y1 = 1458, 1556
                hk_glow = u >= 0.52
                draw.rounded_rectangle(
                    [54, hk_y0, W - 54, hk_y1],
                    radius=16,
                    fill=(38, 16, 28, 245) if hk_glow else (15, 23, 42, 235),
                    outline=(255, 59, 92, 255) if hk_glow else (71, 85, 105, 200),
                    width=3,
                )
                hk_lines = _wrap_text_pixels(draw, f"HACK: {quick_tip}", f_hack_txt, max_px=W - 140, max_lines=2)
                hy_c = hk_y0 + 16
                for hln in hk_lines:
                    draw.text((74, hy_c), hln, font=f_hack_txt, fill=(254, 240, 138, 255))
                    hy_c += 30

            # ----------------------------------------------------------------
            # C. RIGHT / MAIN INTERACTIVE GEOMETRY & COMPASS STAGE (8MXN6QjPJqc Style)
            # ----------------------------------------------------------------
            sw_s = sx1 - sx0
            sh_s = sy1 - sy0
            ax_x = sx0 + int(sw_s * 0.16)   # Observer / Point A (left vertex)
            bx_x = sx0 + int(sw_s * 0.78)   # Tower Base / Point B (right-angle vertex)
            by_y = sy0 + int(sh_s * 0.78)   # Ground level Y
            cy_y = sy0 + int(sh_s * 0.20)   # Tower Top / Point C (top vertex)

            # 1. Vertical Neon-Green Guide Lines + Numbered Green Badges `1`, `2`, `3` (8MXN6QjPJqc 0:07)
            guide_xs = [ax_x, (ax_x + bx_x) // 2, bx_x]
            for g_i, gx_pos in enumerate(guide_xs):
                g_prog = _ease_out_cubic((u - (0.03 + g_i * 0.05)) / 0.14)
                if g_prog > 0.01:
                    gy_end = int(sy0 + 22 + (sy1 - sy0 - 44) * g_prog)
                    draw.line([(gx_pos, sy0 + 22), (gx_pos, gy_end)], fill=(16, 185, 129, 95), width=2)
                    # Rounded green number badge `1`, `2`, `3`
                    nb_r = 20
                    nb_y = sy0 + 44
                    draw.rounded_rectangle(
                        [gx_pos - nb_r, nb_y - nb_r, gx_pos + nb_r, nb_y + nb_r],
                        radius=10,
                        fill=(16, 185, 129, 255),
                        outline=(255, 255, 255, 240),
                        width=2,
                    )
                    num_s = str(g_i + 1)
                    bb_n = draw.textbbox((0, 0), num_s, font=f_num_badge)
                    draw.text((gx_pos - (bb_n[2] - bb_n[0]) // 2, nb_y - (bb_n[3] - bb_n[1]) // 2 - bb_n[1]), num_s, font=f_num_badge, fill=(10, 16, 30, 255))

            # 2. Unfolding Neon Reference Circle around Observer Vertex A (8MXN6QjPJqc 0:11)
            circ_prog = _ease_out_cubic((u - 0.04) / 0.22)
            if circ_prog > 0.01:
                c_rad = 68 if not is_vertical else 56
                draw.arc(
                    [ax_x - c_rad, by_y - c_rad, ax_x + c_rad, by_y + c_rad],
                    start=-180,
                    end=int(-180 + 360 * circ_prog),
                    fill=(0, 229, 255, 165),
                    width=3,
                )

            # 3. PHASE 1 GEOMETRY: Cyan Horizontal Base Line (Adjacent = B) synced with Formula Portion 1!
            base_prog = _ease_out_cubic((u - 0.07) / 0.25)
            if base_prog > 0.01:
                cur_x = int(ax_x + (bx_x - ax_x) * base_prog)
                w_base = 9 if active_part == 0 else 6
                if active_part == 0:
                    draw.line([(ax_x, by_y), (cur_x, by_y)], fill=(0, 229, 255, 95), width=18)
                draw.line([(ax_x, by_y), (cur_x, by_y)], fill=(0, 229, 255, 255), width=w_base)
                draw.ellipse([ax_x - 9, by_y - 9, ax_x + 9, by_y + 9], fill=(0, 229, 255, 255), outline=(255, 255, 255, 255), width=2)
                draw.ellipse([cur_x - 9, by_y - 9, cur_x + 9, by_y + 9], fill=(0, 229, 255, 255), outline=(255, 255, 255, 255), width=2)

                base_m = int(round(40 * base_prog))
                b_lbl = f"BASE (B) = {base_m} m" if sid == 3 else f"BASE (ADJACENT = B)"
                mid_bx = (ax_x + cur_x) // 2
                draw.rounded_rectangle([mid_bx - 135, by_y + 18, mid_bx + 135, by_y + 56], radius=10, fill=(8, 47, 73, 245), outline=(0, 229, 255, 255), width=2)
                draw.text((mid_bx - 118, by_y + 23), b_lbl, font=f_stage_lbl, fill=(186, 230, 253, 255))

                # Connect Active Portion 1 Card to Base Line with glowing dotted connector
                if active_part == 0 and not is_vertical:
                    _draw_dashed_line(draw, portion_centers[0], (mid_bx, by_y), fill=(0, 229, 255, 195), width=3)

            # 4. Playful `?` Curiosity Badge in Hook (u = 0.16..0.38) before Height finishes locking!
            if 0.14 <= u <= 0.42:
                q_x = bx_x - 68
                q_y = (by_y + cy_y) // 2
                draw.rounded_rectangle([q_x - 42, q_y - 46, q_x + 42, q_y + 46], radius=18, fill=(255, 214, 0, 255), outline=(255, 255, 255, 255), width=3)
                bb_q = draw.textbbox((0, 0), "?", font=f_qmark)
                draw.text((q_x - (bb_q[2] - bb_q[0]) // 2, q_y - (bb_q[3] - bb_q[1]) // 2 - bb_q[1]), "?", font=f_qmark, fill=(15, 23, 42, 255))

            # 5. PHASE 2 GEOMETRY: Yellow Vertical Height Line (Opposite = H) + 90° Right-Angle Square synced with Portion 2!
            h_prog = _ease_out_cubic((u - 0.35) / 0.25)
            if h_prog > 0.01:
                cur_y = int(by_y - (by_y - cy_y) * h_prog)
                w_h = 9 if active_part == 1 else 6
                if active_part == 1:
                    draw.line([(bx_x, by_y), (bx_x, cur_y)], fill=(255, 214, 0, 95), width=18)
                draw.line([(bx_x, by_y), (bx_x, cur_y)], fill=(255, 214, 0, 255), width=w_h)
                draw.ellipse([bx_x - 9, cur_y - 9, bx_x + 9, cur_y + 9], fill=(255, 214, 0, 255), outline=(255, 255, 255, 255), width=2)

                # 90-degree perpendicular square marker at B
                sq = 28
                draw.line([(bx_x - sq, by_y), (bx_x - sq, by_y - sq), (bx_x, by_y - sq)], fill=(255, 214, 0, 255), width=3)
                draw.text((bx_x - sq - 48, by_y - sq - 12), "90°", font=f_p_lbl, fill=(255, 214, 0, 255))

                mid_hy = (by_y + cur_y) // 2
                h_lbl = "HEIGHT (H = 20√3m)" if sid == 3 else "HEIGHT (OPPOSITE = H)"
                draw.rounded_rectangle([bx_x - 265, mid_hy - 22, bx_x - 16, mid_hy + 22], radius=10, fill=(66, 32, 6, 245), outline=(255, 214, 0, 255), width=2)
                draw.text((bx_x - 252, mid_hy - 14), h_lbl, font=f_stage_lbl, fill=(254, 240, 138, 255))

                if active_part == 1 and not is_vertical:
                    _draw_dashed_line(draw, portion_centers[1], (bx_x - 140, mid_hy), fill=(255, 214, 0, 195), width=3)

            # 6. Red Laser Hypotenuse Sight-Line + Alternate Z-Rule Top Horizontal Ray
            ray_prog = _ease_out_cubic((u - 0.42) / 0.22)
            if ray_prog > 0.01:
                # Top horizontal eye-level depression line for Z-rule
                z_end_x = int(bx_x - (bx_x - ax_x) * ray_prog)
                _draw_dashed_line(draw, (bx_x, cy_y), (z_end_x, cy_y), fill=(16, 185, 129, 210), width=3)

                # Red Laser Hypotenuse from C (top) to A (observer)
                hx_cur = int(bx_x - (bx_x - ax_x) * ray_prog)
                hy_cur = int(cy_y + (by_y - cy_y) * ray_prog)
                draw.line([(bx_x, cy_y), (hx_cur, hy_cur)], fill=(255, 59, 92, 95), width=16)
                draw.line([(bx_x, cy_y), (hx_cur, hy_cur)], fill=(255, 59, 92, 255), width=6)

            # 7. PHASE 3 GEOMETRY: Metallic Compass Scratching Angle Arc θ + Red `*` Markers synced with Portion 3!
            arc_prog = _ease_out_cubic((u - 0.58) / 0.18)
            if arc_prog > 0.01:
                cur_deg = int(round(target_angle * arc_prog))
                arc_r = 112 if not is_vertical else 92
                slope_deg = math.degrees(math.atan2(by_y - cy_y, bx_x - ax_x))
                sweep_deg = slope_deg * arc_prog

                # Glowing emerald/gold angle sector arc at A
                draw.arc(
                    [ax_x - arc_r, by_y - arc_r, ax_x + arc_r, by_y + arc_r],
                    start=-sweep_deg,
                    end=0,
                    fill=(16, 185, 129, 255),
                    width=7,
                )
                # Alternate Z-angle depression arc at C (top)
                draw.arc(
                    [bx_x - 86, cy_y - 86, bx_x + 86, cy_y + 86],
                    start=180 - sweep_deg,
                    end=180,
                    fill=(255, 214, 0, 235),
                    width=5,
                )

                # Metallic Compass Arms + Red `*` Intersection Markers (8MXN6QjPJqc 1:35)
                tip_rad = math.radians(-sweep_deg)
                tip_x = int(ax_x + arc_r * math.cos(tip_rad))
                tip_y = int(by_y + arc_r * math.sin(tip_rad))
                hinge_x = ax_x + int(arc_r * 0.48)
                hinge_y = by_y - int(arc_r * 0.95)
                draw.line([(hinge_x, hinge_y), (ax_x, by_y)], fill=(203, 213, 225, 255), width=5)
                draw.line([(hinge_x, hinge_y), (tip_x, tip_y)], fill=(248, 250, 252, 255), width=5)
                draw.ellipse([hinge_x - 8, hinge_y - 8, hinge_x + 8, hinge_y + 8], fill=(255, 214, 0, 255), outline=(15, 23, 42, 255), width=2)

                # Red `*` intersection markers on arc endpoints
                draw.text((tip_x - 10, tip_y - 18), "*", font=f_big_ang, fill=(255, 59, 92, 255))
                draw.text((ax_x + arc_r - 10, by_y - 18), "*", font=f_big_ang, fill=(255, 59, 92, 255))

                # Big Angle Counter Badge (`θ = 45°` / `60°`)
                ang_txt = f"θ = {cur_deg}°"
                ab_x = ax_x + arc_r + 22
                ab_y = by_y - 74
                draw.rounded_rectangle([ab_x, ab_y, ab_x + 178, ab_y + 56], radius=14, fill=(6, 78, 59, 250), outline=(16, 185, 129, 255), width=3)
                draw.text((ab_x + 22, ab_y + 8), ang_txt, font=f_big_ang, fill=(255, 255, 255, 255))

                if active_part == 2 and not is_vertical:
                    _draw_dashed_line(draw, portion_centers[2], (ab_x + 89, ab_y), fill=(16, 185, 129, 205), width=3)

            # 8. SCENE 2 & 3 EXTRA: Expanding Concentric Neon Ratio Waves + 5-Sec Climax Boss Timer!
            if sid == 2 and u >= 0.48:
                # Show the 3 classic angle rays (30°, 45°, 60°) simultaneously as reference waves
                for r_idx, (lbl_d, r_col) in enumerate([("30° (1/√3)", (0, 229, 255, 175)), ("45° (1)", (255, 214, 0, 195)), ("60° (√3)", (16, 185, 129, 215))]):
                    px_peg = ax_x + int((bx_x - ax_x) * (0.18 * r_idx))
                    draw.line([(px_peg, by_y), (bx_x, cy_y)], fill=r_col, width=3)
                    draw.ellipse([px_peg - 6, by_y - 6, px_peg + 6, by_y + 6], fill=r_col)

            if sid == 3 and u >= 0.50:
                # Second inner 60° walk milestone pin at midpoint M + Concentric Neon Waves + 5.0s Boss Timer Ring!
                mx_x = (ax_x + bx_x) // 2
                draw.line([(mx_x, by_y), (bx_x, cy_y)], fill=(16, 185, 129, 255), width=6)
                draw.ellipse([mx_x - 9, by_y - 9, mx_x + 9, by_y + 9], fill=(255, 214, 0, 255), outline=(255, 255, 255, 255), width=2)
                draw.rounded_rectangle([mx_x - 68, by_y - 52, mx_x + 68, by_y - 16], radius=8, fill=(6, 78, 59, 245), outline=(16, 185, 129, 255), width=2)
                draw.text((mx_x - 54, by_y - 46), "60° (x=20m)", font=f_p_lbl, fill=(255, 255, 255, 255))

                # Expanding concentric neon wave rings around tower top C (8MXN6QjPJqc 1:06)
                wave_u = (u - 0.50) / 0.50
                for w_i in range(3):
                    wr = int(28 + ((wave_u * 120 + w_i * 38) % 120))
                    wa = int(210 * (1.0 - (wr / 150.0)))
                    draw.ellipse([bx_x - wr, cy_y - wr, bx_x + wr, cy_y + wr], outline=(16, 185, 129, max(20, wa)), width=3)

                # 5.0-Second Circular Boss Countdown Ring in top-left of Stage
                cd_prog = _clamp01((u - 0.54) / 0.34)
                rem_sec = max(0.0, 5.0 * (1.0 - cd_prog))
                ring_cx, ring_cy, ring_r = sx0 + 118, sy0 + 132, 62
                draw.ellipse([ring_cx - ring_r, ring_cy - ring_r, ring_cx + ring_r, ring_cy + ring_r], fill=(15, 23, 42, 245), outline=(51, 65, 85, 255), width=6)
                ring_col = (16, 185, 129, 255) if rem_sec <= 0.1 else (255, 214, 0, 255)
                draw.arc(
                    [ring_cx - ring_r, ring_cy - ring_r, ring_cx + ring_r, ring_cy + ring_r],
                    start=-90,
                    end=int(-90 + 360 * (1.0 - cd_prog)),
                    fill=ring_col,
                    width=8,
                )
                cd_str = "DONE!" if rem_sec <= 0.1 else f"{rem_sec:0.1f}s"
                bb_cd = draw.textbbox((0, 0), cd_str, font=f_stage_lbl)
                draw.text((ring_cx - (bb_cd[2] - bb_cd[0]) // 2, ring_cy - (bb_cd[3] - bb_cd[1]) // 2 - bb_cd[1]), cd_str, font=f_stage_lbl, fill=(255, 255, 255, 255))

            # 9. SCENE 4 FINALE (u = 0.68..1.00): ANIMATED YOUTUBE SUBSCRIBE + BELL + FREE PDF CTA CARD!
            if sid == 4 and u >= 0.68:
                cta_u = _ease_out_cubic((u - 0.68) / 0.14)
                clicked = u >= 0.78
                cx_card = (sx0 + sx1) // 2
                cy_card = (sy0 + sy1) // 2
                cw_card = min(sw_s - 60, 820)
                ch_card = 320 if not is_vertical else 340
                y_slide = int((1.0 - cta_u) * 80)

                x0_c = cx_card - cw_card // 2
                y0_c = cy_card - ch_card // 2 + y_slide
                x1_c = x0_c + cw_card
                y1_c = y0_c + ch_card

                draw.rounded_rectangle([x0_c + 8, y0_c + 10, x1_c + 8, y1_c + 10], radius=28, fill=(0, 0, 0, 185))
                draw.rounded_rectangle([x0_c, y0_c, x1_c, y1_c], radius=28, fill=(15, 23, 42, 252), outline=(255, 214, 0, 255), width=5)

                hdr_cta = "JOIN @TOPPERLAB FOR EVERY CHAPTER IN 6 MINS!"
                bb_hc = draw.textbbox((0, 0), hdr_cta, font=f_cta_sub)
                draw.text((cx_card - (bb_hc[2] - bb_hc[0]) // 2, y0_c + 26), hdr_cta, font=f_cta_sub, fill=(255, 214, 0, 255))

                # Subscribe Button (Morphs from Red `SUBSCRIBE` -> Emerald `SUBSCRIBED` at u = 0.78!)
                btn_w, btn_h = 356, 82
                btn_x0 = cx_card - btn_w // 2 - 64
                btn_y0 = y0_c + 88
                btn_x1 = btn_x0 + btn_w
                btn_y1 = btn_y0 + btn_h
                ic_cx = btn_x0 + 46
                ic_cy = (btn_y0 + btn_y1) // 2

                if not clicked:
                    draw.rounded_rectangle([btn_x0, btn_y0, btn_x1, btn_y1], radius=20, fill=(220, 38, 38, 255), outline=(255, 255, 255, 255), width=3)
                    # Vector Play Triangle icon
                    draw.polygon([(ic_cx - 10, ic_cy - 14), (ic_cx - 10, ic_cy + 14), (ic_cx + 14, ic_cy)], fill=(255, 255, 255, 255))
                    sub_lbl = "SUBSCRIBE"
                else:
                    draw.rounded_rectangle([btn_x0, btn_y0, btn_x1, btn_y1], radius=20, fill=(16, 185, 129, 255), outline=(255, 255, 255, 255), width=4)
                    # Vector Checkmark icon
                    draw.line([(ic_cx - 12, ic_cy + 2), (ic_cx - 3, ic_cy + 11), (ic_cx + 14, ic_cy - 10)], fill=(255, 255, 255, 255), width=5)
                    sub_lbl = "SUBSCRIBED"
                bb_sb = draw.textbbox((0, 0), sub_lbl, font=f_cta_big)
                draw.text((btn_x0 + 76 + (btn_w - 92 - (bb_sb[2] - bb_sb[0])) // 2, btn_y0 + (btn_h - (bb_sb[3] - bb_sb[1])) // 2 - bb_sb[1]), sub_lbl, font=f_cta_big, fill=(255, 255, 255, 255))

                # Notification Bell Button + Expanding Sonic Rings when clicked!
                bell_cx = btn_x1 + 68
                bell_cy = (btn_y0 + btn_y1) // 2
                draw.rounded_rectangle([bell_cx - 46, bell_cy - 41, bell_cx + 46, bell_cy + 41], radius=20, fill=(255, 214, 0, 255) if clicked else (30, 41, 59, 255), outline=(255, 255, 255, 255), width=3)
                bell_txt = "BELL"
                bb_bl = draw.textbbox((0, 0), bell_txt, font=f_stage_lbl)
                draw.text((bell_cx - (bb_bl[2] - bb_bl[0]) // 2, bell_cy - (bb_bl[3] - bb_bl[1]) // 2 - bb_bl[1]), bell_txt, font=f_stage_lbl, fill=(15, 23, 42, 255) if clicked else (255, 214, 0, 255))

                if clicked:
                    ring_u = (u - 0.78) / 0.22
                    for r_k in range(2):
                        rr = int(48 + ((ring_u * 65 + r_k * 28) % 65))
                        draw.ellipse([bell_cx - rr, bell_cy - rr, bell_cx + rr, bell_cy + rr], outline=(255, 214, 0, 190), width=3)

                # Animated Cursor Arrow gliding to click the Subscribe button
                cur_prog = _clamp01((u - 0.69) / 0.09)
                ptr_x = int((btn_x1 + 120) - 180 * cur_prog)
                ptr_y = int((btn_y1 + 90) - 110 * cur_prog)
                draw.polygon([(ptr_x, ptr_y), (ptr_x + 28, ptr_y + 14), (ptr_x + 16, ptr_y + 20), (ptr_x + 24, ptr_y + 36), (ptr_x + 15, ptr_y + 40), (ptr_x + 8, ptr_y + 24), (ptr_x, ptr_y + 32)], fill=(255, 255, 255, 255), outline=(15, 23, 42, 255))

                # Bottom Pill inside CTA Card: Free 1-Page Formula PDF + Like
                pdf_txt = "LIKE + FREE 1-PAGE FORMULA SHEET IN DESCRIPTION!"
                draw.rounded_rectangle([x0_c + 28, y1_c - 78, x1_c - 28, y1_c - 22], radius=14, fill=(8, 47, 73, 255), outline=(0, 229, 255, 255), width=2)
                bb_pf = draw.textbbox((0, 0), pdf_txt, font=f_stage_lbl)
                draw.text((cx_card - (bb_pf[2] - bb_pf[0]) // 2, y1_c - 64), pdf_txt, font=f_stage_lbl, fill=(186, 230, 253, 255))

            proc.stdin.write(frame.tobytes())

        proc.stdin.close()
        proc.wait(timeout=180)
    except Exception:
        try:
            if proc.stdin and not proc.stdin.closed:
                proc.stdin.close()
        except Exception:
            pass
        try:
            proc.kill()
        except Exception:
            pass
        raise

    return target_mp4


def render_faceless_scene_media(
    scene: Dict[str, Any],
    project_dir: Path,
    voice_preset: Dict[str, Any],
    visual_theme_prompt: str,
    force_live_image: bool = False,
    custom_motion_mp4: Path | None = None,
    class_badge_text: str = "CLASS 10 • MATHEMATICS",
    bgm_enabled: bool = True,
    auto_veo_broll: bool = True,
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

    # Ensure formula_parts and act_badge are populated on the scene dict
    scene["act_badge"] = scene.get("act_badge") or ACT_BADGE_LABELS.get(sid, f"ACT {sid}: CONCEPT")
    scene["formula_parts"] = _parse_formula_into_three_portions(
        scene.get("formula_badge", ""),
        scene.get("headline", ""),
        scene.get("formula_parts"),
    )

    f_in = round(dur_sec * 0.07, 2)
    f_out = round(dur_sec * 0.65, 2)
    h_in = round(dur_sec * 0.66, 2)
    h_out = round(dur_sec - 0.25, 2)

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

    saved_motion = scenes_dir / f"scene_{sid:02d}_custom_motion.mp4"
    if custom_motion_mp4 and Path(custom_motion_mp4).exists():
        if Path(custom_motion_mp4).resolve() != saved_motion.resolve():
            shutil.copyfile(custom_motion_mp4, saved_motion)
    elif auto_veo_broll and not saved_motion.exists() and (has_vertex_adc() or get_gemini_api_key()):
        veo_p = scene.get("google_flow_veo_prompt") or scene.get("image_3d_prompt") or scene.get("headline", "")
        generate_veo_clip_via_api(
            veo_prompt=veo_p,
            output_mp4=saved_motion,
            aspect_ratio="16:9",
            duration_seconds=4,
        )

    has_live_broll = saved_motion.exists() and saved_motion.stat().st_size > 1000
    scene["motion_source"] = (
        "Google Flow / Veo 3.1 Live B-Roll + Animated Geometry, Compass Arcs & Formula Highlighting + ASMR BGM"
        if has_live_broll
        else "Animated Geometry, Compass Arcs & Formula Portion Highlighting + 3D B-Roll + ASMR BGM"
    )

    _render_animated_geometry_and_formula_scene_mp4(
        scene=scene,
        target_mp4=mp4_16x9,
        wav_master=wav_master,
        dur_sec=dur_sec,
        src_img_path=img_16x9,
        saved_motion_mp4=saved_motion if has_live_broll else None,
        class_badge_text=class_badge_text,
        is_vertical=False,
    )
    _render_animated_geometry_and_formula_scene_mp4(
        scene=scene,
        target_mp4=mp4_9x16,
        wav_master=wav_master,
        dur_sec=dur_sec,
        src_img_path=img_9x16,
        saved_motion_mp4=saved_motion if has_live_broll else None,
        class_badge_text=class_badge_text,
        is_vertical=True,
    )

    # Remove bulky intermediate uncompressed WAVs once muxed into AAC MP4s
    for tmp_f in (wav_voice, wav_master):
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
    auto_veo_broll: bool = True,
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
            auto_veo_broll=auto_veo_broll,
        )

    renders = stitch_master_videos(project_dir, scenes, short_max_scenes=short_max_scenes)
    draft_state = {
        **blueprint,
        "class_badge_text": class_badge_text,
        "bgm_enabled": bgm_enabled,
        "auto_veo_broll": auto_veo_broll,
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
    auto_veo_broll: bool = False,
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
        target["formula_parts"] = _parse_formula_into_three_portions(target["formula_badge"], target.get("headline", ""))
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
        auto_veo_broll=auto_veo_broll,
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
