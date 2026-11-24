"""
Agent 4: Direct YouTube Publisher Agent (`backend/agent4_youtube_publisher.py`)
===============================================================================
Handles secure OAuth 2.0 authentication (`https://www.googleapis.com/auth/youtube.upload`),
stores refresh tokens durably inside SQLite (`storage/omni_studio.db`), and uploads videos
directly to YouTube using a 4MB chunked resumable upload engine (`MediaFileUpload` with
`chunksize=4*1024*1024, resumable=True` or resilient pure-REST 4MB chunked fallback if
`google-api-python-client` is not installed).

Features:
- Auto-hydrates existing local `config/credentials/youtube_oauth_token.json` into SQLite.
- Supports interactive OAuth 2.0 authorization URL + code exchange right inside Streamlit.
- Exponential backoff & network-drop retry tolerance during 4MB chunked upload.
- Streams real-time upload percentage (0–100%) to SQLite `publish_records` & `generation_queue`.
- Automatically attaches the High-CTR generated thumbnail, writes exact scene-range chapters
  into the description, applies privacy/scheduling (`publishAt`), routes into chosen playlist,
  marks the SQLite project `"Published"`, and returns the Watch URL + YouTube Studio link!
"""

from __future__ import annotations

import json
import logging
import os
import time
import urllib.parse
import uuid
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import requests
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

from backend.config import OmniStudioConfig
from backend.schemas import Agent4Output
from storage.db import OmniDatabase, get_db

logger = logging.getLogger("omni_studio.agent4")

YOUTUBE_SCOPES: List[str] = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",
    "https://www.googleapis.com/auth/youtube.readonly",
]
CHUNK_SIZE_BYTES: int = 4 * 1024 * 1024  # 4MB resumable chunks


# ==============================================================================
# 1. OAUTH 2.0 TOKEN STORAGE & CHANNEL CONNECTION (SQLITE-BACKED)
# ==============================================================================
def hydrate_local_token_into_sqlite(
    config: Optional[OmniStudioConfig] = None,
    db: Optional[OmniDatabase] = None,
) -> Optional[Dict[str, Any]]:
    """
    Checks SQLite `oauth_tokens` first; if empty, imports existing `YOUTUBE_TOKEN_FILE`
    (e.g. `config/credentials/youtube_oauth_token.json`) so connected channels work immediately.
    """
    cfg = config or OmniStudioConfig()
    database = db or get_db()
    existing = database.get_oauth_token("youtube")
    if existing and existing.get("token_dict"):
        return existing

    # 1. Hydrate from Streamlit Cloud Secrets (`YOUTUBE_OAUTH_TOKEN_JSON`) or env var
    raw_secret: Optional[Dict[str, Any]] = None
    try:
        import streamlit as st
        if hasattr(st, "secrets") and "YOUTUBE_OAUTH_TOKEN_JSON" in st.secrets:
            val = st.secrets["YOUTUBE_OAUTH_TOKEN_JSON"]
            raw_secret = json.loads(val) if isinstance(val, str) else dict(val)
    except Exception:
        pass
    if raw_secret is None and os.getenv("YOUTUBE_OAUTH_TOKEN_JSON", "").strip():
        try:
            raw_secret = json.loads(os.getenv("YOUTUBE_OAUTH_TOKEN_JSON", "").strip())
        except Exception:
            pass

    if raw_secret and (raw_secret.get("refresh_token") or raw_secret.get("access_token") or raw_secret.get("token")):
        try:
            creds = _credentials_from_token_dict(raw_secret)
            ch_info = fetch_authenticated_channel_info(creds) if creds else {}
            database.save_oauth_token(
                "youtube",
                raw_secret,
                account_email=ch_info.get("email", ""),
                channel_id=ch_info.get("channel_id") or raw_secret.get("connected_channel_id", ""),
                channel_title=ch_info.get("channel_title") or raw_secret.get("connected_channel_title", "Connected YouTube Channel"),
                scopes=raw_secret.get("scopes", YOUTUBE_SCOPES),
            )
            return database.get_oauth_token("youtube")
        except Exception as exc:
            logger.warning("Could not hydrate YOUTUBE_OAUTH_TOKEN_JSON secret: %s", exc)

    # 2. Hydrate from local token file (`config/credentials/youtube_oauth_token.json`)
    token_file = cfg.youtube_token_file
    if token_file.exists():
        try:
            raw = json.loads(token_file.read_text(encoding="utf-8"))
            creds = _credentials_from_token_dict(raw)
            ch_info = fetch_authenticated_channel_info(creds) if creds else {}
            database.save_oauth_token(
                "youtube",
                raw,
                account_email=ch_info.get("email", ""),
                channel_id=ch_info.get("channel_id", ""),
                channel_title=ch_info.get("channel_title", "Connected YouTube Channel"),
                scopes=raw.get("scopes", YOUTUBE_SCOPES),
            )
            return database.get_oauth_token("youtube")
        except Exception as exc:
            logger.warning("Could not hydrate local YouTube token file: %s", exc)
    return None


def _credentials_from_token_dict(token_dict: Dict[str, Any]) -> Optional[Credentials]:
    try:
        creds = Credentials(
            token=token_dict.get("token") or token_dict.get("access_token"),
            refresh_token=token_dict.get("refresh_token"),
            token_uri=token_dict.get("token_uri", "https://oauth2.googleapis.com/token"),
            client_id=token_dict.get("client_id"),
            client_secret=token_dict.get("client_secret"),
            scopes=token_dict.get("scopes") or YOUTUBE_SCOPES,
        )
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
        elif not creds.token and creds.refresh_token:
            creds.refresh(Request())
        return creds
    except Exception as exc:
        logger.warning("Failed refreshing OAuth credentials: %s", exc)
        return None


def get_valid_youtube_credentials(
    config: Optional[OmniStudioConfig] = None,
    db: Optional[OmniDatabase] = None,
) -> Tuple[Optional[Credentials], Optional[Dict[str, Any]]]:
    cfg = config or OmniStudioConfig()
    database = db or get_db()
    record = hydrate_local_token_into_sqlite(cfg, database)
    if not record or not record.get("token_dict"):
        return None, None
    creds = _credentials_from_token_dict(record["token_dict"])
    if creds is None:
        return None, record
    # Persist refreshed access token back into SQLite
    updated_dict = {
        "token": creds.token,
        "refresh_token": creds.refresh_token or record["token_dict"].get("refresh_token"),
        "token_uri": creds.token_uri,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "scopes": list(creds.scopes or YOUTUBE_SCOPES),
    }
    database.save_oauth_token(
        "youtube",
        updated_dict,
        account_email=record.get("account_email", ""),
        channel_id=record.get("channel_id", ""),
        channel_title=record.get("channel_title", ""),
        scopes=updated_dict["scopes"],
    )
    return creds, database.get_oauth_token("youtube")


def build_youtube_oauth_url(
    client_secrets_path: Path,
    redirect_uri: str = "http://localhost:8501",
) -> Tuple[Optional[str], str]:
    """Generates a Google OAuth 2.0 consent URL for `youtube.upload`."""
    if not client_secrets_path.exists():
        return None, f"Client secrets JSON not found at `{client_secrets_path}`."
    try:
        raw = json.loads(client_secrets_path.read_text(encoding="utf-8"))
        cfg_block = raw.get("web") or raw.get("installed") or {}
        client_id = cfg_block.get("client_id", "")
        auth_uri = cfg_block.get("auth_uri", "https://accounts.google.com/o/oauth2/auth")
        if not client_id:
            return None, "Invalid client_secret.json (missing client_id)."
        params = {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": " ".join(YOUTUBE_SCOPES),
            "access_type": "offline",
            "prompt": "consent",
        }
        return f"{auth_uri}?{urllib.parse.urlencode(params)}", "OK"
    except Exception as exc:
        return None, str(exc)


def exchange_oauth_code_and_store(
    auth_code: str,
    client_secrets_path: Path,
    redirect_uri: str = "http://localhost:8501",
    db: Optional[OmniDatabase] = None,
) -> Tuple[bool, str]:
    """Exchanges an OAuth 2.0 authorization code for tokens and saves refresh_token into SQLite."""
    database = db or get_db()
    if not client_secrets_path.exists():
        return False, f"Missing `{client_secrets_path}`."
    try:
        raw = json.loads(client_secrets_path.read_text(encoding="utf-8"))
        cfg_block = raw.get("web") or raw.get("installed") or {}
        token_uri = cfg_block.get("token_uri", "https://oauth2.googleapis.com/token")
        resp = requests.post(
            token_uri,
            data={
                "code": auth_code.strip(),
                "client_id": cfg_block["client_id"],
                "client_secret": cfg_block["client_secret"],
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            },
            timeout=15.0,
        )
        if resp.status_code != 200:
            return False, f"Token exchange failed ({resp.status_code}): {resp.text[:250]}"
        tok = resp.json()
        token_dict = {
            "token": tok.get("access_token"),
            "refresh_token": tok.get("refresh_token"),
            "token_uri": token_uri,
            "client_id": cfg_block["client_id"],
            "client_secret": cfg_block["client_secret"],
            "scopes": YOUTUBE_SCOPES,
        }
        creds = _credentials_from_token_dict(token_dict)
        info = fetch_authenticated_channel_info(creds) if creds else {}
        database.save_oauth_token(
            "youtube",
            token_dict,
            channel_id=info.get("channel_id", ""),
            channel_title=info.get("channel_title", "Connected YouTube Channel"),
            scopes=YOUTUBE_SCOPES,
        )
        return True, f"Connected to YouTube channel: {info.get('channel_title', 'Authorized')} ✅"
    except Exception as exc:
        return False, str(exc)


def fetch_authenticated_channel_info(creds: Credentials) -> Dict[str, str]:
    try:
        resp = requests.get(
            "https://www.googleapis.com/youtube/v3/channels",
            params={"part": "snippet,statistics", "mine": "true"},
            headers={"Authorization": f"Bearer {creds.token}"},
            timeout=10.0,
        )
        if resp.status_code == 200:
            items = resp.json().get("items", [])
            if items:
                ch = items[0]
                return {
                    "channel_id": ch.get("id", ""),
                    "channel_title": ch.get("snippet", {}).get("title", ""),
                    "subscribers": ch.get("statistics", {}).get("subscriberCount", "0"),
                }
    except Exception as exc:
        logger.debug("Channel lookup failed: %s", exc)
    return {}


def list_user_youtube_playlists(
    config: Optional[OmniStudioConfig] = None,
    db: Optional[OmniDatabase] = None,
) -> List[Dict[str, str]]:
    """Lists authenticated user's YouTube playlists for playlist routing in Step 4."""
    creds, _ = get_valid_youtube_credentials(config, db)
    if not creds:
        return []
    try:
        resp = requests.get(
            "https://www.googleapis.com/youtube/v3/playlists",
            params={"part": "snippet", "mine": "true", "maxResults": 30},
            headers={"Authorization": f"Bearer {creds.token}"},
            timeout=10.0,
        )
        if resp.status_code == 200:
            return [
                {"id": item["id"], "title": item.get("snippet", {}).get("title", item["id"])}
                for item in resp.json().get("items", [])
            ]
    except Exception as exc:
        logger.debug("Playlist list skipped: %s", exc)
    return []


# ==============================================================================
# 2. 4MB CHUNKED RESUMABLE UPLOAD ENGINE WITH EXPONENTIAL BACKOFF
# ==============================================================================
def _attach_thumbnail(creds: Credentials, video_id: str, thumbnail_path: Path) -> bool:
    if not thumbnail_path.exists():
        return False
    try:
        mime = "image/png" if thumbnail_path.suffix.lower() == ".png" else "image/jpeg"
        resp = requests.post(
            "https://www.googleapis.com/upload/youtube/v3/thumbnails/set",
            params={"videoId": video_id, "uploadType": "media"},
            headers={
                "Authorization": f"Bearer {creds.token}",
                "Content-Type": mime,
            },
            data=thumbnail_path.read_bytes(),
            timeout=30.0,
        )
        return resp.status_code in (200, 201)
    except Exception as exc:
        logger.warning("Thumbnail attachment warning for %s: %s", video_id, exc)
        return False


def _add_video_to_playlist(creds: Credentials, video_id: str, playlist_id: str) -> bool:
    if not playlist_id or playlist_id == "NONE":
        return False
    try:
        resp = requests.post(
            "https://www.googleapis.com/youtube/v3/playlistItems",
            params={"part": "snippet"},
            headers={
                "Authorization": f"Bearer {creds.token}",
                "Content-Type": "application/json",
            },
            json={
                "snippet": {
                    "playlistId": playlist_id,
                    "resourceId": {"kind": "youtube#video", "videoId": video_id},
                }
            },
            timeout=15.0,
        )
        return resp.status_code in (200, 201)
    except Exception as exc:
        logger.warning("Playlist routing skipped: %s", exc)
        return False


def _resumable_upload_via_googleapiclient(
    creds: Credentials,
    video_path: Path,
    body: Dict[str, Any],
    progress_cb: Callable[[int, str], None],
) -> Optional[str]:
    """
    Uses `googleapiclient.http.MediaFileUpload(..., chunksize=4*1024*1024, resumable=True)`
    targeting `videos.insert` with exponential backoff on retriable HTTP/network drops.
    """
    try:
        from googleapiclient.discovery import build  # type: ignore
        from googleapiclient.errors import HttpError  # type: ignore
        from googleapiclient.http import MediaFileUpload  # type: ignore

        youtube = build("youtube", "v3", credentials=creds, cache_discovery=False)
        media = MediaFileUpload(
            str(video_path),
            mimetype="video/mp4",
            chunksize=CHUNK_SIZE_BYTES,
            resumable=True,
        )
        request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

        response = None
        retry = 0
        max_retries = 6
        while response is None:
            try:
                status, response = request.next_chunk()
                if status:
                    pct = int(status.progress() * 100)
                    progress_cb(min(95, pct), f"Uploading 4MB resumable chunks... ({pct}%)")
            except HttpError as he:
                if he.resp.status in (500, 502, 503, 504, 429) and retry < max_retries:
                    retry += 1
                    wait = min(32.0, 2.0 ** retry)
                    progress_cb(min(90, 10 * retry), f"Transient HTTP {he.resp.status}; backing off {wait:.0f}s...")
                    time.sleep(wait)
                else:
                    raise
            except (OSError, ConnectionError, TimeoutError) as net_err:
                if retry < max_retries:
                    retry += 1
                    wait = min(32.0, 2.0 ** retry)
                    progress_cb(min(90, 10 * retry), f"Network drop ({net_err}); resuming in {wait:.0f}s...")
                    time.sleep(wait)
                else:
                    raise

        if response and response.get("id"):
            return str(response["id"])
    except ImportError:
        return None
    return None


def _resumable_upload_via_rest_chunks(
    creds: Credentials,
    video_path: Path,
    body: Dict[str, Any],
    progress_cb: Callable[[int, str], None],
) -> str:
    """
    Pure-REST YouTube Data API v3 4MB chunked resumable upload fallback with exponential backoff
    (guarantees resumable uploads work even if `google-api-python-client` is not installed).
    """
    file_size = video_path.stat().st_size
    init_resp = requests.post(
        "https://www.googleapis.com/upload/youtube/v3/videos",
        params={"uploadType": "resumable", "part": "snippet,status"},
        headers={
            "Authorization": f"Bearer {creds.token}",
            "Content-Type": "application/json; charset=UTF-8",
            "X-Upload-Content-Length": str(file_size),
            "X-Upload-Content-Type": "video/mp4",
        },
        json=body,
        timeout=30.0,
    )
    if init_resp.status_code not in (200, 201):
        raise RuntimeError(f"Resumable upload init failed ({init_resp.status_code}): {init_resp.text[:300]}")

    upload_url = init_resp.headers.get("Location")
    if not upload_url:
        raise RuntimeError("Missing resumable upload Location header from YouTube API.")

    offset = 0
    max_retries = 6
    with open(video_path, "rb") as fp:
        while offset < file_size:
            fp.seek(offset)
            chunk = fp.read(CHUNK_SIZE_BYTES)
            end_byte = offset + len(chunk) - 1
            headers = {
                "Authorization": f"Bearer {creds.token}",
                "Content-Length": str(len(chunk)),
                "Content-Type": "video/mp4",
                "Content-Range": f"bytes {offset}-{end_byte}/{file_size}",
            }
            for attempt in range(1, max_retries + 1):
                try:
                    resp = requests.put(upload_url, headers=headers, data=chunk, timeout=120.0)
                    if resp.status_code in (200, 201):
                        progress_cb(96, "Video upload finalized! Attaching metadata...")
                        return str(resp.json()["id"])
                    if resp.status_code == 308:
                        range_hdr = resp.headers.get("Range", "")
                        if "-" in range_hdr:
                            offset = int(range_hdr.split("-")[1]) + 1
                        else:
                            offset = end_byte + 1
                        pct = int((offset / float(file_size)) * 95)
                        progress_cb(pct, f"Uploading 4MB resumable chunks... ({pct}%)")
                        break
                    if resp.status_code in (429, 500, 502, 503, 504) and attempt < max_retries:
                        wait = min(32.0, 2.0 ** attempt)
                        progress_cb(int((offset / float(file_size)) * 95), f"HTTP {resp.status_code}; retrying in {wait:.0f}s...")
                        time.sleep(wait)
                        continue
                    raise RuntimeError(f"Chunk upload failed ({resp.status_code}): {resp.text[:250]}")
                except (requests.RequestException, OSError) as net_exc:
                    if attempt < max_retries:
                        wait = min(32.0, 2.0 ** attempt)
                        time.sleep(wait)
                        continue
                    raise RuntimeError(f"Resumable upload aborted after retries: {net_exc}") from net_exc

    raise RuntimeError("Upload finished without receiving YouTube video ID.")


def run_agent4_youtube_publish(
    project_id: str,
    *,
    video_path: Path,
    thumbnail_path: Optional[Path],
    title: str,
    description: str,
    exact_chapters_text: str,
    tags: List[str],
    privacy_status: str = "private",
    scheduled_publish_at_iso: Optional[str] = None,
    playlist_id: Optional[str] = None,
    category_id: str = "27",
    config: Optional[OmniStudioConfig] = None,
    db: Optional[OmniDatabase] = None,
) -> Agent4Output:
    """
    Executes Agent 4 (Direct YouTube Publisher Agent):
    - Uploads video using 4MB chunked resumable upload with backoff.
    - Writes exact scene timestamp chapters into description.
    - Attaches thumbnail & adds to playlist.
    - Updates SQLite `publish_records` and marks project `"Published"`.
    """
    cfg = config or OmniStudioConfig()
    database = db or get_db()
    record_id = f"pub_{uuid.uuid4().hex[:10]}"

    if not video_path.exists():
        raise FileNotFoundError(f"Video file not found: {video_path}")

    creds, _ = get_valid_youtube_credentials(cfg, database)
    if creds is None:
        raise RuntimeError(
            "YouTube OAuth 2.0 is not connected. Complete OAuth authentication in Step 4 before uploading."
        )

    # Ensure exact scene-based chapters are embedded in the description
    final_desc = description.strip()
    if exact_chapters_text.strip() and "00:00" not in final_desc:
        final_desc = f"{final_desc}\n\n⏱️ CHAPTERS:\n{exact_chapters_text.strip()}"

    # YouTube requires privacyStatus='private' when `publishAt` scheduling is specified
    effective_privacy = "private" if scheduled_publish_at_iso else privacy_status.lower()
    status_block: Dict[str, Any] = {
        "privacyStatus": effective_privacy,
        "selfDeclaredMadeForKids": False,
    }
    if scheduled_publish_at_iso:
        status_block["publishAt"] = scheduled_publish_at_iso

    body: Dict[str, Any] = {
        "snippet": {
            "title": title[:100],
            "description": final_desc[:4950],
            "tags": [t.strip() for t in tags if t.strip()][:35],
            "categoryId": category_id,
        },
        "status": status_block,
    }

    def _on_progress(pct: int, msg: str) -> None:
        database.upsert_publish_record(
            record_id=record_id,
            project_id=project_id,
            title=title[:100],
            privacy_status=effective_privacy,
            scheduled_publish_at=scheduled_publish_at_iso,
            playlist_id=playlist_id,
            upload_progress_pct=pct,
            status="uploading",
        )
        database.upsert_job(
            job_id=f"{project_id}_yt_upload",
            project_id=project_id,
            job_type="youtube_upload",
            label=f"YouTube Resumable Upload: {title[:36]}",
            status="running",
            progress_pct=pct,
            message=msg,
        )

    _on_progress(2, "Initializing 4MB chunked resumable upload to YouTube...")
    video_id = _resumable_upload_via_googleapiclient(creds, video_path, body, _on_progress)
    if not video_id:
        video_id = _resumable_upload_via_rest_chunks(creds, video_path, body, _on_progress)

    thumb_ok = False
    if thumbnail_path and thumbnail_path.exists():
        _on_progress(97, "Attaching High-CTR Thumbnail...")
        thumb_ok = _attach_thumbnail(creds, video_id, thumbnail_path)

    if playlist_id and playlist_id != "NONE":
        _on_progress(99, "Routing video into selected playlist...")
        _add_video_to_playlist(creds, video_id, playlist_id)

    watch_url = f"https://www.youtube.com/watch?v={video_id}"
    studio_url = f"https://studio.youtube.com/video/{video_id}/edit"

    database.upsert_publish_record(
        record_id=record_id,
        project_id=project_id,
        title=title[:100],
        privacy_status=effective_privacy,
        scheduled_publish_at=scheduled_publish_at_iso,
        playlist_id=playlist_id,
        video_id=video_id,
        studio_url=studio_url,
        watch_url=watch_url,
        upload_progress_pct=100,
        status="Published",
    )
    database.upsert_job(
        job_id=f"{project_id}_yt_upload",
        project_id=project_id,
        job_type="youtube_upload",
        label=f"YouTube Resumable Upload: {title[:36]}",
        status="completed",
        progress_pct=100,
        message=f"Completed ✅ Video ID: {video_id}",
        output_path=studio_url,
    )

    out = Agent4Output(
        record_id=record_id,
        video_id=video_id,
        watch_url=watch_url,
        studio_url=studio_url,
        title=title[:100],
        privacy_status=effective_privacy,
        scheduled_publish_at=scheduled_publish_at_iso,
        playlist_id=playlist_id,
        thumbnail_attached=thumb_ok,
        status="Published",
        note="Uploaded via 4MB chunked resumable upload with chapters & thumbnail." if thumb_ok else "Uploaded via 4MB chunked resumable upload (custom thumbnail requires verified YouTube channel).",
    )
    database.update_project_stage(
        project_id,
        current_step=4,
        status="Published",
        agent4_data=out.model_dump(),
        youtube_video_id=video_id,
        youtube_url=studio_url,
    )
    return out
