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
from datetime import datetime, timedelta, timezone
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
# 1. MULTI-CHANNEL OAUTH 2.0 TOKEN STORAGE & CHANNEL CONNECTION (SQLITE-BACKED)
# ==============================================================================
def _save_channel_token_record(
    database: OmniDatabase,
    raw_token: Dict[str, Any],
    *,
    fallback_title: str = "Connected YouTube Channel",
) -> Optional[Dict[str, Any]]:
    """
    Normalizes, enriches via `channels.list(mine=true)`, and stores a YouTube channel token
    under `provider = youtube:<channel_id>` so UNLIMITED channels coexist cleanly in SQLite.
    """
    if not isinstance(raw_token, dict):
        return None
    if not (raw_token.get("refresh_token") or raw_token.get("access_token") or raw_token.get("token")):
        return None

    token_copy = dict(raw_token)
    if token_copy.get("access_token") and not token_copy.get("token"):
        token_copy["token"] = token_copy["access_token"]

    creds = _credentials_from_token_dict(token_copy)
    ch_info = fetch_authenticated_channel_info(creds) if creds else {}

    ch_id = (ch_info.get("channel_id") or token_copy.get("connected_channel_id") or "").strip()
    ch_title = (ch_info.get("channel_title") or token_copy.get("connected_channel_title") or fallback_title).strip()
    custom_url = (ch_info.get("custom_url") or token_copy.get("connected_custom_url") or "").strip()

    if creds is not None:
        token_copy["token"] = creds.token
        token_copy["access_token"] = creds.token
        if creds.refresh_token:
            token_copy["refresh_token"] = creds.refresh_token
    if ch_id:
        token_copy["connected_channel_id"] = ch_id
    if ch_title:
        token_copy["connected_channel_title"] = ch_title
    if custom_url:
        token_copy["connected_custom_url"] = custom_url

    provider_key = f"youtube:{ch_id}" if ch_id else f"youtube:ch_{uuid.uuid4().hex[:8]}"
    database.save_oauth_token(
        provider_key,
        token_copy,
        account_email=custom_url or ch_info.get("email", ""),
        channel_id=ch_id or provider_key.split(":", 1)[1],
        channel_title=ch_title,
        scopes=list(token_copy.get("scopes") or YOUTUBE_SCOPES),
    )
    return database.get_oauth_token(provider_key)


def hydrate_all_youtube_channels(
    config: Optional[OmniStudioConfig] = None,
    db: Optional[OmniDatabase] = None,
) -> List[Dict[str, Any]]:
    """
    Hydrates ALL configured YouTube channels into SQLite without overwriting existing channels:
    1. Migrates any legacy single `provider='youtube'` SQLite record into `youtube:<channel_id>`.
    2. Loads `YOUTUBE_OAUTH_TOKEN_JSON`, `YOUTUBE_CHANNELS_JSON` (list/dict), AND any
       `YOUTUBE_OAUTH_TOKEN_*` secret from Streamlit Cloud Secrets or environment variables.
    3. Loads all local `config/credentials/youtube_oauth_token*.json` files.
    """
    cfg = config or OmniStudioConfig()
    database = db or get_db()

    # 1. Migrate legacy single 'youtube' row into namespaced 'youtube:<channel_id>' & purge duplicates
    legacy = database.get_oauth_token("youtube")
    if legacy and legacy.get("token_dict"):
        _save_channel_token_record(
            database,
            legacy["token_dict"],
            fallback_title=legacy.get("channel_title") or "Connected YouTube Channel",
        )
        database.delete_oauth_token("youtube")
    database.deduplicate_youtube_channels()

    cur_chs = database.list_youtube_channels()
    existing_ids = {
        (ch.get("channel_id") or "").strip()
        for ch in cur_chs
        if (ch.get("channel_id") or "").strip()
    }
    existing_refresh_tokens = {
        ((ch.get("token_dict") or {}).get("refresh_token") or "").strip()
        for ch in cur_chs
        if ((ch.get("token_dict") or {}).get("refresh_token") or "").strip()
    }

    def _ingest_maybe_multi(raw_obj: Any, source_label: str) -> None:
        items: List[Dict[str, Any]] = []
        if isinstance(raw_obj, str):
            txt = raw_obj.strip()
            if not txt:
                return
            try:
                raw_obj = json.loads(txt)
            except Exception:
                return
        if isinstance(raw_obj, list):
            items = [x for x in raw_obj if isinstance(x, dict)]
        elif isinstance(raw_obj, dict):
            if any(k in raw_obj for k in ("refresh_token", "access_token", "token")):
                items = [raw_obj]
            else:
                # Dict mapping label -> token_dict
                for lbl, val in raw_obj.items():
                    if isinstance(val, dict) and any(k in val for k in ("refresh_token", "access_token", "token")):
                        v_copy = dict(val)
                        v_copy.setdefault("connected_channel_title", str(lbl))
                        items.append(v_copy)

        for tok in items:
            known_cid = (tok.get("connected_channel_id") or "").strip()
            known_ref = (tok.get("refresh_token") or "").strip()
            if (known_cid and known_cid in existing_ids) or (known_ref and known_ref in existing_refresh_tokens):
                continue
            saved = _save_channel_token_record(database, tok, fallback_title=source_label)
            if saved:
                if saved.get("channel_id"):
                    existing_ids.add(saved["channel_id"])
                sref = ((saved.get("token_dict") or {}).get("refresh_token") or "").strip()
                if sref:
                    existing_refresh_tokens.add(sref)

    # 2. Collect secrets from Streamlit Cloud Secrets + Environment variables
    secret_sources: Dict[str, Any] = {}
    try:
        import streamlit as st
        if hasattr(st, "secrets"):
            for k in st.secrets.keys():
                ks = str(k)
                if ks == "YOUTUBE_CHANNELS_JSON" or ks.startswith("YOUTUBE_OAUTH_TOKEN"):
                    secret_sources[ks] = st.secrets[ks]
    except Exception:
        pass
    for k, v in os.environ.items():
        if (k == "YOUTUBE_CHANNELS_JSON" or k.startswith("YOUTUBE_OAUTH_TOKEN")) and k not in secret_sources:
            secret_sources[k] = v

    for skey, sval in secret_sources.items():
        _ingest_maybe_multi(sval, skey)

    # 3. Collect local token JSON files (`youtube_oauth_token*.json`)
    token_candidates: List[Path] = []
    if cfg.youtube_token_file.exists():
        token_candidates.append(cfg.youtube_token_file)
    cred_dir = cfg.youtube_token_file.parent
    if cred_dir.exists():
        for fp in sorted(cred_dir.glob("youtube_oauth_token*.json")):
            if fp not in token_candidates:
                token_candidates.append(fp)

    for tf in token_candidates:
        try:
            _ingest_maybe_multi(tf.read_text(encoding="utf-8"), tf.stem)
        except Exception as exc:
            logger.warning("Could not hydrate local YouTube token file %s: %s", tf, exc)

    database.deduplicate_youtube_channels()
    return database.list_youtube_channels()


def list_connected_youtube_channels(
    config: Optional[OmniStudioConfig] = None,
    db: Optional[OmniDatabase] = None,
) -> List[Dict[str, Any]]:
    """Returns all connected YouTube channels (hydrating from Secrets / local files automatically)."""
    return hydrate_all_youtube_channels(config, db)


def hydrate_local_token_into_sqlite(
    config: Optional[OmniStudioConfig] = None,
    db: Optional[OmniDatabase] = None,
    channel_id: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Backward-compatible helper returning the requested (or default first) connected YouTube channel."""
    cfg = config or OmniStudioConfig()
    database = db or get_db()
    hydrate_all_youtube_channels(cfg, database)
    return database.get_youtube_channel(channel_id)


def _parse_utc_naive_expiry(raw_val: Any) -> Optional[datetime]:
    """Parses ISO-8601 `expiry` / `expires_at` strings into naive UTC datetime for `google.oauth2.credentials.Credentials`."""
    if not raw_val:
        return None
    if isinstance(raw_val, datetime):
        return raw_val.astimezone(timezone.utc).replace(tzinfo=None) if raw_val.tzinfo else raw_val
    try:
        s = str(raw_val).strip()
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is not None:
            dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt
    except Exception:
        return None


def _credentials_from_token_dict(
    token_dict: Dict[str, Any],
    *,
    force_refresh: bool = False,
) -> Optional[Credentials]:
    try:
        expiry_dt = _parse_utc_naive_expiry(token_dict.get("expiry") or token_dict.get("expires_at"))
        creds = Credentials(
            token=token_dict.get("token") or token_dict.get("access_token"),
            refresh_token=token_dict.get("refresh_token"),
            token_uri=token_dict.get("token_uri", "https://oauth2.googleapis.com/token"),
            client_id=token_dict.get("client_id"),
            client_secret=token_dict.get("client_secret"),
            scopes=token_dict.get("scopes") or YOUTUBE_SCOPES,
            expiry=expiry_dt,
        )
        # CRITICAL: If expiry is missing OR within 2 minutes of expiring (or force_refresh=True),
        # ALWAYS refresh via `refresh_token`! Otherwise google-auth treats expiry=None as never expired -> HTTP 401!
        now_utc_naive = datetime.now(timezone.utc).replace(tzinfo=None)
        needs_refresh = (
            force_refresh
            or not creds.token
            or creds.expired
            or expiry_dt is None
            or (expiry_dt - now_utc_naive) < timedelta(minutes=2)
        )
        if needs_refresh:
            if creds.refresh_token:
                creds.refresh(Request())
            else:
                return None
        return creds
    except Exception as exc:
        logger.warning("Failed refreshing OAuth credentials: %s", exc)
        return None


def get_valid_youtube_credentials(
    config: Optional[OmniStudioConfig] = None,
    db: Optional[OmniDatabase] = None,
    channel_id: Optional[str] = None,
    *,
    force_refresh: bool = False,
) -> Tuple[Optional[Credentials], Optional[Dict[str, Any]]]:
    """Fetches & refreshes OAuth credentials for the specified `channel_id` (or first connected channel)."""
    cfg = config or OmniStudioConfig()
    database = db or get_db()
    record = hydrate_local_token_into_sqlite(cfg, database, channel_id=channel_id)
    if not record or not record.get("token_dict"):
        return None, None
    creds = _credentials_from_token_dict(record["token_dict"], force_refresh=force_refresh)
    if creds is None:
        return None, record
    # Persist refreshed access token + exact expiry back into SQLite under the EXACT same channel key!
    updated_dict = dict(record["token_dict"])
    expiry_iso = (
        creds.expiry.replace(tzinfo=timezone.utc).isoformat()
        if isinstance(creds.expiry, datetime)
        else (datetime.now(timezone.utc) + timedelta(minutes=50)).isoformat()
    )
    updated_dict.update(
        {
            "token": creds.token,
            "access_token": creds.token,
            "expiry": expiry_iso,
            "expires_at": expiry_iso,
            "refresh_token": creds.refresh_token or record["token_dict"].get("refresh_token"),
            "token_uri": creds.token_uri,
            "client_id": creds.client_id,
            "client_secret": creds.client_secret,
            "scopes": list(creds.scopes or YOUTUBE_SCOPES),
        }
    )
    provider_key = record.get("provider") or f"youtube:{record.get('channel_id', 'default')}"
    database.save_oauth_token(
        provider_key,
        updated_dict,
        account_email=record.get("account_email", ""),
        channel_id=record.get("channel_id", ""),
        channel_title=record.get("channel_title", ""),
        scopes=updated_dict["scopes"],
    )
    return creds, database.get_oauth_token(provider_key)


def resolve_oauth_client_config(
    client_secrets_path: Optional[Path] = None,
    *,
    config: Optional[OmniStudioConfig] = None,
    db: Optional[OmniDatabase] = None,
) -> Tuple[Optional[Dict[str, str]], str]:
    """
    Resolves Google OAuth Client `(client_id, client_secret, auth_uri, token_uri)` seamlessly from:
    1. Local `client_secret.json`
    2. `YOUTUBE_CLIENT_SECRETS_JSON` Streamlit Secret / env var
    3. Any already-connected YouTube channel token (so adding Channel #2, #3, #4 works on Streamlit Cloud
       with ZERO extra `client_secret.json` setup!).
    """
    cfg = config or OmniStudioConfig()
    database = db or get_db()
    sec_path = client_secrets_path or cfg.youtube_client_secrets

    if sec_path and sec_path.exists():
        try:
            raw = json.loads(sec_path.read_text(encoding="utf-8"))
            blk = raw.get("web") or raw.get("installed") or raw
            if blk.get("client_id") and blk.get("client_secret"):
                return {
                    "client_id": blk["client_id"],
                    "client_secret": blk["client_secret"],
                    "auth_uri": blk.get("auth_uri", "https://accounts.google.com/o/oauth2/auth"),
                    "token_uri": blk.get("token_uri", "https://oauth2.googleapis.com/token"),
                }, "local_client_secret"
        except Exception:
            pass

    # Check Streamlit Secrets / env var `YOUTUBE_CLIENT_SECRETS_JSON`
    raw_sec_str = os.getenv("YOUTUBE_CLIENT_SECRETS_JSON", "").strip()
    if not raw_sec_str:
        try:
            import streamlit as st
            if hasattr(st, "secrets") and "YOUTUBE_CLIENT_SECRETS_JSON" in st.secrets:
                val = st.secrets["YOUTUBE_CLIENT_SECRETS_JSON"]
                raw_sec_str = val if isinstance(val, str) else json.dumps(dict(val))
        except Exception:
            pass
    if raw_sec_str:
        try:
            raw = json.loads(raw_sec_str)
            blk = raw.get("web") or raw.get("installed") or raw
            if blk.get("client_id") and blk.get("client_secret"):
                return {
                    "client_id": blk["client_id"],
                    "client_secret": blk["client_secret"],
                    "auth_uri": blk.get("auth_uri", "https://accounts.google.com/o/oauth2/auth"),
                    "token_uri": blk.get("token_uri", "https://oauth2.googleapis.com/token"),
                }, "secret_client_json"
        except Exception:
            pass

    # Reuse OAuth client_id + client_secret directly from any connected YouTube channel token!
    for ch in hydrate_all_youtube_channels(cfg, database):
        td = ch.get("token_dict") or {}
        if td.get("client_id") and td.get("client_secret"):
            return {
                "client_id": td["client_id"],
                "client_secret": td["client_secret"],
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": td.get("token_uri", "https://oauth2.googleapis.com/token"),
            }, "reused_connected_oauth_app"

    return None, "No Google OAuth Client credentials found (place `client_secret.json` or connect a token first)."


def extract_oauth_code_from_input(raw_input: str) -> str:
    """Accepts EITHER a raw OAuth authorization code OR a full redirected URL (`http://.../?code=4/0A...`)."""
    txt = (raw_input or "").strip()
    if not txt:
        return ""
    if "code=" in txt:
        parsed = urllib.parse.urlparse(txt)
        qs = urllib.parse.parse_qs(parsed.query)
        if qs.get("code"):
            return qs["code"][0].strip()
        # Handle fragments or raw query strings without scheme
        qs2 = urllib.parse.parse_qs(txt.split("?", 1)[-1])
        if qs2.get("code"):
            return qs2["code"][0].strip()
    return txt


def build_youtube_oauth_url(
    client_secrets_path: Optional[Path] = None,
    redirect_uri: str = "http://localhost:8501",
    *,
    config: Optional[OmniStudioConfig] = None,
    db: Optional[OmniDatabase] = None,
) -> Tuple[Optional[str], str]:
    """
    Generates a Google OAuth 2.0 consent URL with `prompt=consent select_account` so Google ALWAYS
    displays the Google Account + Brand Account / YouTube Channel Picker (for connecting any channel!).
    """
    oauth_cfg, src_msg = resolve_oauth_client_config(client_secrets_path, config=config, db=db)
    if not oauth_cfg:
        return None, src_msg
    params = {
        "client_id": oauth_cfg["client_id"],
        "redirect_uri": redirect_uri.strip(),
        "response_type": "code",
        "scope": " ".join(YOUTUBE_SCOPES),
        "access_type": "offline",
        "prompt": "consent select_account",
        "state": redirect_uri.strip(),
    }
    return f"{oauth_cfg['auth_uri']}?{urllib.parse.urlencode(params)}", "OK"


def format_channel_streamlit_secret_toml(channel_record: Dict[str, Any]) -> str:
    """Formats a strictly valid ASCII-key Streamlit Cloud Secrets TOML block to persist a channel forever."""
    import re as _re
    title = (channel_record.get("channel_title") or "NEW_CHANNEL").upper()
    slug = _re.sub(r"[^A-Z0-9]+", "_", title).strip("_")[:24] or "CHANNEL"
    secret_key = f"YOUTUBE_OAUTH_TOKEN_{slug}"
    tok_json = json.dumps(channel_record.get("token_dict") or {}, indent=2, ensure_ascii=False)
    return f"{secret_key} = '''\n{tok_json}\n'''"


def exchange_oauth_code_and_store(
    auth_code_or_url: str,
    client_secrets_path: Optional[Path] = None,
    redirect_uri: str = "http://localhost:8501",
    db: Optional[OmniDatabase] = None,
    config: Optional[OmniStudioConfig] = None,
) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
    """
    Exchanges an OAuth 2.0 authorization code (or full redirect URL) for refresh tokens and stores
    the new channel alongside existing channels in SQLite (NEVER overwriting other connected channels!).
    """
    database = db or get_db()
    oauth_cfg, src_msg = resolve_oauth_client_config(client_secrets_path, config=config, db=database)
    if not oauth_cfg:
        return False, src_msg, None

    clean_code = extract_oauth_code_from_input(auth_code_or_url)
    if not clean_code:
        return False, "Paste the authorization code or redirected browser URL first.", None

    try:
        resp = requests.post(
            oauth_cfg["token_uri"],
            data={
                "code": clean_code,
                "client_id": oauth_cfg["client_id"],
                "client_secret": oauth_cfg["client_secret"],
                "redirect_uri": redirect_uri.strip(),
                "grant_type": "authorization_code",
            },
            timeout=15.0,
        )
        if resp.status_code != 200:
            return False, f"Token exchange failed ({resp.status_code}): {resp.text[:260]}", None
        tok = resp.json()
        token_dict = {
            "token": tok.get("access_token"),
            "access_token": tok.get("access_token"),
            "refresh_token": tok.get("refresh_token"),
            "token_uri": oauth_cfg["token_uri"],
            "client_id": oauth_cfg["client_id"],
            "client_secret": oauth_cfg["client_secret"],
            "scopes": YOUTUBE_SCOPES,
        }
        saved = _save_channel_token_record(database, token_dict, fallback_title="Connected YouTube Channel")
        if not saved:
            return False, "Token received but could not save channel record.", None
        ch_name = saved.get("channel_title") or "Authorized Channel"
        ch_id = saved.get("channel_id") or ""
        return True, f"Connected YouTube channel: **{ch_name}** (`{ch_id}`) ✅", saved
    except Exception as exc:
        return False, str(exc), None


def import_youtube_token_json(
    raw_json_text: str,
    *,
    db: Optional[OmniDatabase] = None,
) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
    """Imports a pasted or uploaded YouTube OAuth token JSON into SQLite alongside existing channels."""
    database = db or get_db()
    try:
        parsed = json.loads(raw_json_text)
        if isinstance(parsed, list):
            last_saved = None
            cnt = 0
            for item in parsed:
                sv = _save_channel_token_record(database, item)
                if sv:
                    last_saved = sv
                    cnt += 1
            if cnt > 0:
                return True, f"Imported {cnt} YouTube channel(s) ✅", last_saved
            return False, "JSON list did not contain valid YouTube OAuth tokens.", None
        saved = _save_channel_token_record(database, parsed)
        if not saved:
            return False, "JSON is missing `refresh_token` or `access_token`.", None
        return True, f"Connected channel **{saved.get('channel_title')}** (`{saved.get('channel_id')}`) ✅", saved
    except Exception as exc:
        return False, f"Invalid token JSON: {exc}", None


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
                snip = ch.get("snippet", {})
                return {
                    "channel_id": ch.get("id", ""),
                    "channel_title": snip.get("title", ""),
                    "custom_url": snip.get("customUrl", ""),
                    "subscribers": ch.get("statistics", {}).get("subscriberCount", "0"),
                }
    except Exception as exc:
        logger.debug("Channel lookup failed: %s", exc)
    return {}


def list_user_youtube_playlists(
    config: Optional[OmniStudioConfig] = None,
    db: Optional[OmniDatabase] = None,
    channel_id: Optional[str] = None,
) -> List[Dict[str, str]]:
    """
    Lists ALL playlists (paginated up to 150) belonging to the selected YouTube channel:
    1. Primary (OAuth 2.0): fetches Public + Unlisted + Private playlists via `mine=true`
       (auto-refreshes token on HTTP 401 and also checks `channelId` if `mine=true` returns empty).
    2. Fallback (YouTube Data API v3 `YOUTUBE_API_KEY` or public `channelId` query): ensures all
       public playlists still appear immediately even if an OAuth refresh token needs re-auth!
    """
    cfg = config or OmniStudioConfig()
    database = db or get_db()
    creds, ch_rec = get_valid_youtube_credentials(cfg, database, channel_id=channel_id)
    resolved_cid = (channel_id or (ch_rec or {}).get("channel_id") or "").strip()

    def _fetch_paginated(params_base: Dict[str, Any], headers: Optional[Dict[str, str]] = None) -> Tuple[int, List[Dict[str, str]]]:
        collected: List[Dict[str, str]] = []
        seen_pids = set()
        page_token: Optional[str] = None
        last_status = 200
        for _ in range(4):  # up to 200 playlists
            p = dict(params_base)
            p["maxResults"] = 50
            if page_token:
                p["pageToken"] = page_token
            resp = requests.get(
                "https://www.googleapis.com/youtube/v3/playlists",
                params=p,
                headers=headers or {},
                timeout=10.0,
            )
            last_status = resp.status_code
            if resp.status_code != 200:
                return last_status, collected
            data = resp.json()
            for item in data.get("items", []):
                pid = item.get("id")
                if pid and pid not in seen_pids:
                    seen_pids.add(pid)
                    collected.append(
                        {"id": pid, "title": item.get("snippet", {}).get("title", pid)}
                    )
            page_token = data.get("nextPageToken")
            if not page_token:
                break
        return last_status, collected

    # 1. Authenticated OAuth fetch (`mine=true` returns ALL public + unlisted + private playlists!)
    if creds is not None:
        try:
            status, items = _fetch_paginated({"part": "snippet", "mine": "true"}, {"Authorization": f"Bearer {creds.token}"})
            if status == 401:
                creds2, _ = get_valid_youtube_credentials(cfg, database, channel_id=resolved_cid or None, force_refresh=True)
                if creds2 is not None:
                    creds = creds2
                    status, items = _fetch_paginated({"part": "snippet", "mine": "true"}, {"Authorization": f"Bearer {creds.token}"})
            if items:
                return items
            # If mine=true returned empty, try explicit channelId with OAuth token
            if resolved_cid.startswith("UC"):
                _, items_cid = _fetch_paginated({"part": "snippet", "channelId": resolved_cid}, {"Authorization": f"Bearer {creds.token}"})
                if items_cid:
                    return items_cid
        except Exception as exc:
            logger.debug("OAuth playlist list skipped: %s", exc)

    # 2. Public YouTube Data API v3 fallback (`YOUTUBE_API_KEY`) so public playlists always appear cleanly
    if resolved_cid.startswith("UC") and cfg.youtube_api_key:
        try:
            _, pub_items = _fetch_paginated({"part": "snippet", "channelId": resolved_cid, "key": cfg.youtube_api_key})
            if pub_items:
                return pub_items
        except Exception as exc:
            logger.debug("Public API playlist fallback skipped: %s", exc)

    return []


def create_youtube_playlist(
    title: str,
    *,
    description: str = "",
    privacy_status: str = "public",
    channel_id: Optional[str] = None,
    config: Optional[OmniStudioConfig] = None,
    db: Optional[OmniDatabase] = None,
) -> Tuple[Optional[Dict[str, str]], str]:
    """Creates a brand-new YouTube playlist directly on the selected channel."""
    clean_title = (title or "").strip()
    if not clean_title:
        return None, "Enter a playlist title first."
    creds, ch_rec = get_valid_youtube_credentials(config, db, channel_id=channel_id)
    if not creds:
        return None, "Selected YouTube channel is not authenticated."
    try:
        resp = requests.post(
            "https://www.googleapis.com/youtube/v3/playlists",
            params={"part": "snippet,status"},
            headers={
                "Authorization": f"Bearer {creds.token}",
                "Content-Type": "application/json",
            },
            json={
                "snippet": {"title": clean_title[:150], "description": description[:500]},
                "status": {"privacyStatus": privacy_status},
            },
            timeout=15.0,
        )
        if resp.status_code in (200, 201):
            item = resp.json()
            pl = {"id": item["id"], "title": item.get("snippet", {}).get("title", clean_title)}
            ch_name = (ch_rec or {}).get("channel_title", "channel")
            return pl, f"Created playlist **{pl['title']}** on {ch_name} ✅"
        return None, f"Playlist creation failed ({resp.status_code}): {resp.text[:220]}"
    except Exception as exc:
        return None, str(exc)


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
    channel_id: Optional[str] = None,
    category_id: str = "27",
    config: Optional[OmniStudioConfig] = None,
    db: Optional[OmniDatabase] = None,
) -> Agent4Output:
    """
    Executes Agent 4 (Direct YouTube Publisher Agent) targeting the exact selected `channel_id`:
    - Uploads video using 4MB chunked resumable upload with backoff.
    - Writes exact scene timestamp chapters into description.
    - Attaches thumbnail & adds to playlist on that channel.
    - Updates SQLite `publish_records` and marks project `"Published"`.
    """
    cfg = config or OmniStudioConfig()
    database = db or get_db()
    record_id = f"pub_{uuid.uuid4().hex[:10]}"

    if not video_path.exists():
        raise FileNotFoundError(f"Video file not found: {video_path}")

    creds, ch_rec = get_valid_youtube_credentials(cfg, database, channel_id=channel_id)
    if creds is None:
        raise RuntimeError(
            "Selected YouTube channel is not connected. Authorize it in Step 0 (Channel & Playlist) or Step 4 before uploading."
        )
    target_ch_name = (ch_rec or {}).get("channel_title") or "Connected YouTube Channel"

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
        note=(
            f"Uploaded to '{target_ch_name}' via 4MB chunked resumable upload with chapters & thumbnail."
            if thumb_ok
            else f"Uploaded to '{target_ch_name}' via 4MB chunked resumable upload (custom thumbnail requires verified YouTube channel)."
        ),
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
