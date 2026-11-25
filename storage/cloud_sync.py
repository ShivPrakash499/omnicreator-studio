"""
OMNI STUDIO — Automatic Google Cloud Storage Project Persistence (`storage/cloud_sync.py`)
==========================================================================================
Persists every project workspace (metadata, SEO plan, 36-scene scripts, thumbnails, and final
rendered videos) to the user's private Google Cloud Storage bucket (`omni-studio-<gcp-project>`)
using existing Vertex AI ADC credentials — so projects NEVER disappear when Streamlit Cloud
reboots ephemeral containers!

Zero extra pip dependencies: uses standard-library streaming HTTP + `google.auth` already loaded.
Low-RAM design: streams uploads/downloads in 1 MB chunks so 100+ MB MP4 files use <2 MB RAM.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from google.auth.transport.requests import Request as GoogleAuthRequest

logger = logging.getLogger("omni_studio.cloud_sync")

_BUCKET_READY_CACHE: Dict[str, bool] = {}
_SYNC_LOCK = threading.Lock()
_RESTORED_FLAG = False


def _get_gcs_auth() -> Tuple[Optional[str], str, str]:
    """Returns `(bearer_token, gcp_project_id, bucket_name)` or `(None, '', '')`."""
    if os.getenv("OMNI_DISABLE_CLOUD_SYNC", "").strip().lower() in ("1", "true", "yes"):
        return None, "", ""
    try:
        from backend.config import get_vertex_adc_credentials

        creds, gcp_proj = get_vertex_adc_credentials()
        if creds is None or not gcp_proj:
            return None, "", ""
        if not creds.valid or creds.expired or not getattr(creds, "token", None):
            creds.refresh(GoogleAuthRequest())
        token = getattr(creds, "token", None)
        if not token:
            return None, "", ""
        bucket = os.getenv("OMNI_GCS_BUCKET", "").strip() or f"omni-studio-{gcp_proj}"
        return str(token), str(gcp_proj), bucket
    except Exception as exc:
        logger.debug("GCS auth unavailable (%s)", exc)
        return None, "", ""


def is_cloud_sync_enabled() -> bool:
    tok, _, _ = _get_gcs_auth()
    return bool(tok)


def _ensure_bucket(token: str, gcp_proj: str, bucket: str) -> bool:
    if _BUCKET_READY_CACHE.get(bucket):
        return True
    try:
        req = urllib.request.Request(
            f"https://storage.googleapis.com/storage/v1/b/{urllib.parse.quote(bucket, safe='')}",
            headers={"Authorization": f"Bearer {token}"},
        )
        with urllib.request.urlopen(req, timeout=12):
            _BUCKET_READY_CACHE[bucket] = True
            return True
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            try:
                body = json.dumps(
                    {"name": bucket, "location": "ASIA-SOUTH1", "storageClass": "STANDARD"}
                ).encode("utf-8")
                req_c = urllib.request.Request(
                    f"https://storage.googleapis.com/storage/v1/b?project={urllib.parse.quote(gcp_proj, safe='')}",
                    data=body,
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Content-Type": "application/json",
                    },
                    method="POST",
                )
                with urllib.request.urlopen(req_c, timeout=15):
                    _BUCKET_READY_CACHE[bucket] = True
                    return True
            except Exception as c_exc:
                logger.debug("Could not create GCS bucket %s: %s", bucket, c_exc)
    except Exception as exc:
        logger.debug("GCS bucket probe skipped: %s", exc)
    return False


def _upload_bytes_to_gcs(object_name: str, data: bytes, content_type: str = "application/json") -> bool:
    token, gcp_proj, bucket = _get_gcs_auth()
    if not token or not _ensure_bucket(token, gcp_proj, bucket):
        return False
    try:
        url = (
            f"https://storage.googleapis.com/upload/storage/v1/b/"
            f"{urllib.parse.quote(bucket, safe='')}/o?uploadType=media&name="
            f"{urllib.parse.quote(object_name, safe='')}"
        )
        req = urllib.request.Request(
            url,
            data=data,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": content_type,
                "Content-Length": str(len(data)),
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30):
            return True
    except Exception as exc:
        logger.debug("GCS upload failed for %s: %s", object_name, exc)
        return False


def _upload_file_resumable_to_gcs(local_path: Path, object_name: str, content_type: str = "application/octet-stream") -> bool:
    """Streams a local file to GCS in 2 MB chunks (low-RAM safe for 100+ MB MP4 videos!)."""
    if not local_path.exists() or not local_path.is_file():
        return False
    size = local_path.stat().st_size
    if size <= 0:
        return False
    if size <= 4 * 1024 * 1024:
        return _upload_bytes_to_gcs(object_name, local_path.read_bytes(), content_type=content_type)

    token, gcp_proj, bucket = _get_gcs_auth()
    if not token or not _ensure_bucket(token, gcp_proj, bucket):
        return False
    try:
        init_url = (
            f"https://storage.googleapis.com/upload/storage/v1/b/"
            f"{urllib.parse.quote(bucket, safe='')}/o?uploadType=resumable&name="
            f"{urllib.parse.quote(object_name, safe='')}"
        )
        init_req = urllib.request.Request(
            init_url,
            data=b"{}",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json; charset=UTF-8",
                "X-Upload-Content-Type": content_type,
                "X-Upload-Content-Length": str(size),
            },
            method="POST",
        )
        with urllib.request.urlopen(init_req, timeout=20) as init_resp:
            session_uri = init_resp.headers.get("Location")
        if not session_uri:
            return False

        chunk_size = 2 * 1024 * 1024  # 2 MB aligned to 256 KB
        offset = 0
        with open(local_path, "rb") as fp:
            while offset < size:
                chunk = fp.read(chunk_size)
                if not chunk:
                    break
                end_byte = offset + len(chunk) - 1
                put_req = urllib.request.Request(
                    session_uri,
                    data=chunk,
                    headers={
                        "Content-Length": str(len(chunk)),
                        "Content-Range": f"bytes {offset}-{end_byte}/{size}",
                    },
                    method="PUT",
                )
                try:
                    with urllib.request.urlopen(put_req, timeout=60):
                        pass
                except urllib.error.HTTPError as he:
                    if he.code != 308:  # 308 = Resume Incomplete (expected for intermediate chunks)
                        raise
                offset += len(chunk)
        return True
    except Exception as exc:
        logger.debug("GCS resumable upload failed for %s: %s", object_name, exc)
        return False


def _download_file_from_gcs(object_name: str, dest_path: Path) -> bool:
    """Streams a GCS object down to `dest_path` in 512 KB chunks."""
    token, gcp_proj, bucket = _get_gcs_auth()
    if not token or not _ensure_bucket(token, gcp_proj, bucket):
        return False
    try:
        url = (
            f"https://storage.googleapis.com/storage/v1/b/"
            f"{urllib.parse.quote(bucket, safe='')}/o/"
            f"{urllib.parse.quote(object_name, safe='')}?alt=media"
        )
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = dest_path.with_suffix(dest_path.suffix + ".gcs_part")
        with urllib.request.urlopen(req, timeout=90) as resp, open(tmp_path, "wb") as out_f:
            while True:
                buf = resp.read(524288)
                if not buf:
                    break
                out_f.write(buf)
        tmp_path.replace(dest_path)
        return True
    except Exception as exc:
        logger.debug("GCS download skipped for %s: %s", object_name, exc)
        return False


def sync_project_record_async(project_record: Optional[Dict[str, Any]]) -> None:
    """Non-blocking background backup of a single project's full SQLite record to GCS."""
    if not project_record or not project_record.get("id"):
        return
    # Skip temporary unit-test project IDs
    pid = str(project_record["id"])
    if pid.startswith(("test_", "stitch_verify_")):
        return

    payload = json.dumps(project_record, ensure_ascii=False).encode("utf-8")

    def _bg() -> None:
        _upload_bytes_to_gcs(f"projects/{pid}/project.json", payload, content_type="application/json")

    threading.Thread(target=_bg, daemon=True, name=f"gcs_sync_{pid[:12]}").start()


def upload_project_renders_to_gcs(project_id: str, agent3_dict: Dict[str, Any]) -> int:
    """Uploads final deliverable media (1080p MP4, 9:16 Shorts, thumbnail, subtitles) to GCS."""
    if not project_id or project_id.startswith(("test_", "stitch_verify_")):
        return 0
    uploaded = 0
    targets = [
        ("thumbnail_16x9_path", "thumbnail_16x9.png", "image/png"),
        ("video_16x9_path", "OMNI_FINAL_16x9_1080p.mp4", "video/mp4"),
        ("video_9x16_shorts_path", "OMNI_SHORTS_9x16.mp4", "video/mp4"),
        ("ass_subtitles_16x9_path", "subtitles_16x9.ass", "text/plain"),
    ]
    for key, fname, ctype in targets:
        p_str = agent3_dict.get(key)
        if not p_str:
            continue
        p = Path(p_str)
        if p.exists() and p.is_file():
            if _upload_file_resumable_to_gcs(p, f"projects/{project_id}/renders/{fname}", content_type=ctype):
                uploaded += 1
    return uploaded


def ensure_project_renders_local(project_id: str, agent3_dict: Optional[Dict[str, Any]]) -> None:
    """Restores final rendered deliverables from GCS onto local container disk if missing after a reboot."""
    if not project_id or not agent3_dict:
        return
    targets = [
        ("thumbnail_16x9_path", "thumbnail_16x9.png"),
        ("video_16x9_path", "OMNI_FINAL_16x9_1080p.mp4"),
        ("video_9x16_shorts_path", "OMNI_SHORTS_9x16.mp4"),
        ("ass_subtitles_16x9_path", "subtitles_16x9.ass"),
    ]
    for key, fname in targets:
        p_str = agent3_dict.get(key)
        if not p_str:
            continue
        p = Path(p_str)
        if not p.exists() or p.stat().st_size < 1024:
            _download_file_from_gcs(f"projects/{project_id}/renders/{fname}", p)


def restore_projects_from_gcs_once(db: Any, *, force: bool = False) -> int:
    """
    On fresh container startup (e.g., Streamlit Cloud reboot), fetches all backed-up
    `projects/*/project.json` workspaces from GCS and hydrates local SQLite automatically!
    """
    global _RESTORED_FLAG
    with _SYNC_LOCK:
        if _RESTORED_FLAG and not force:
            return 0
        _RESTORED_FLAG = True

    token, gcp_proj, bucket = _get_gcs_auth()
    if not token or not _ensure_bucket(token, gcp_proj, bucket):
        return 0

    restored = 0
    try:
        list_url = (
            f"https://storage.googleapis.com/storage/v1/b/"
            f"{urllib.parse.quote(bucket, safe='')}/o?prefix=projects/&maxResults=200"
        )
        req = urllib.request.Request(list_url, headers={"Authorization": f"Bearer {token}"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            items: List[Dict[str, Any]] = json.loads(resp.read().decode("utf-8")).get("items", []) or []

        for item in items:
            name = str(item.get("name") or "")
            if not name.endswith("/project.json"):
                continue
            try:
                obj_url = (
                    f"https://storage.googleapis.com/storage/v1/b/"
                    f"{urllib.parse.quote(bucket, safe='')}/o/"
                    f"{urllib.parse.quote(name, safe='')}?alt=media"
                )
                req_o = urllib.request.Request(obj_url, headers={"Authorization": f"Bearer {token}"})
                with urllib.request.urlopen(req_o, timeout=15) as r_o:
                    rec = json.loads(r_o.read().decode("utf-8"))
                if isinstance(rec, dict) and rec.get("id") and rec.get("topic"):
                    if db.upsert_project_from_cloud(rec):
                        restored += 1
            except Exception as item_exc:
                logger.debug("Skipped restoring GCS project %s: %s", name, item_exc)
    except Exception as exc:
        logger.debug("GCS project restore skipped: %s", exc)
    return restored
