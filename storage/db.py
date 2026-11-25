"""
OMNI STUDIO — SQLite Persistence Layer (`storage/db.py`)
========================================================
Manages durable state across reruns and background workers:
1. `projects`: Master project records (topic, niche, language, current_step, status, JSON snapshots for Agents 1-4).
2. `generation_queue`: Per-scene/asset async job queue (voiceover, video_clip, motion_graphic, thumbnail, assembly, upload) with real-time progress %, logs, and artifact paths.
3. `oauth_tokens`: Local encrypted/JSON storage for YouTube Data API v3 OAuth 2.0 credentials & refresh tokens.
4. `publish_records`: Direct YouTube upload history, video IDs, scheduled timestamps, playlist IDs, and Studio links.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import tempfile
import threading
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

logger = logging.getLogger("omni_studio.db")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class OmniDatabase:
    """Thread-safe SQLite database wrapper with WAL mode for concurrent Streamlit + Worker access."""

    def __init__(self, db_path: Optional[str | Path] = None) -> None:
        resolved = Path(db_path or os.getenv("OMNI_DB_PATH", "storage/omni_studio.db"))
        resolved.parent.mkdir(parents=True, exist_ok=True)
        self.db_path = resolved
        self._lock = threading.RLock()
        try:
            self._init_schema()
        except sqlite3.OperationalError as exc:
            # If deployed container mount is readonly, transparently fall back to writable temp DB
            if "readonly" in str(exc).lower() and db_path is None:
                fallback_p = Path(tempfile.gettempdir()) / "omni_studio.db"
                logger.warning("SQLite path '%s' is readonly (%s); switching to writable '%s'.", self.db_path, exc, fallback_p)
                self.db_path = fallback_p
                self._init_schema()
            else:
                raise

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            conn = sqlite3.connect(str(self.db_path), timeout=30.0, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA busy_timeout = 30000;")
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA foreign_keys=ON;")
            try:
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS projects (
                    id TEXT PRIMARY KEY,
                    topic TEXT NOT NULL,
                    niche TEXT NOT NULL,
                    language_tone TEXT NOT NULL,
                    target_minutes REAL DEFAULT 6.0,
                    target_channel_id TEXT DEFAULT '',
                    target_channel_title TEXT DEFAULT '',
                    target_playlist_id TEXT DEFAULT '',
                    target_playlist_title TEXT DEFAULT '',
                    current_step INTEGER DEFAULT 1,
                    status TEXT DEFAULT 'draft',
                    agent1_json TEXT,
                    agent2_json TEXT,
                    agent3_json TEXT,
                    agent4_json TEXT,
                    youtube_video_id TEXT,
                    youtube_url TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS generation_queue (
                    job_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    job_type TEXT NOT NULL,
                    scene_index INTEGER DEFAULT 0,
                    label TEXT NOT NULL,
                    status TEXT DEFAULT 'queued',
                    progress_pct INTEGER DEFAULT 0,
                    message TEXT DEFAULT '',
                    output_path TEXT,
                    error_text TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_queue_project
                    ON generation_queue(project_id, job_type, scene_index);

                CREATE TABLE IF NOT EXISTS oauth_tokens (
                    provider TEXT PRIMARY KEY,
                    account_email TEXT,
                    channel_id TEXT,
                    channel_title TEXT,
                    token_json TEXT NOT NULL,
                    scopes TEXT,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS publish_records (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    video_id TEXT,
                    studio_url TEXT,
                    watch_url TEXT,
                    title TEXT,
                    privacy_status TEXT,
                    scheduled_publish_at TEXT,
                    playlist_id TEXT,
                    upload_progress_pct INTEGER DEFAULT 0,
                    status TEXT DEFAULT 'pending',
                    error_text TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
                );
                """
            )
            # Safe, race-proof, retryable idempotent migration for existing SQLite databases
            existing_cols = {r["name"] for r in conn.execute("PRAGMA table_info(projects)").fetchall()}
            for col_name in ("target_channel_id", "target_channel_title", "target_playlist_id", "target_playlist_title"):
                if col_name in existing_cols:
                    continue
                for attempt in range(6):
                    try:
                        conn.execute(f"ALTER TABLE projects ADD COLUMN {col_name} TEXT DEFAULT ''")
                        existing_cols.add(col_name)
                        break
                    except sqlite3.OperationalError as op_err:
                        err_low = str(op_err).lower()
                        if "duplicate column" in err_low:
                            existing_cols.add(col_name)
                            break
                        if ("locked" in err_low or "busy" in err_low) and attempt < 5:
                            time.sleep(0.25 * (attempt + 1))
                            continue
                        raise

    # ------------------------------------------------------------------
    # Projects CRUD
    # ------------------------------------------------------------------
    def create_project(
        self,
        topic: str,
        niche: str,
        language_tone: str,
        target_minutes: float = 6.0,
        project_id: Optional[str] = None,
        target_channel_id: str = "",
        target_channel_title: str = "",
        target_playlist_id: str = "",
        target_playlist_title: str = "",
    ) -> str:
        pid = project_id or f"omni_{uuid.uuid4().hex[:10]}"
        now = _utc_now()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO projects (
                    id, topic, niche, language_tone, target_minutes,
                    target_channel_id, target_channel_title, target_playlist_id, target_playlist_title,
                    current_step, status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 'step1_active', ?, ?)
                """,
                (
                    pid,
                    topic.strip(),
                    niche.strip(),
                    language_tone.strip(),
                    float(target_minutes),
                    (target_channel_id or "").strip(),
                    (target_channel_title or "").strip(),
                    (target_playlist_id or "").strip(),
                    (target_playlist_title or "").strip(),
                    now,
                    now,
                ),
            )
        return pid

    def get_project(self, project_id: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
            if not row:
                return None
            data = dict(row)
            for col in ("agent1_json", "agent2_json", "agent3_json", "agent4_json"):
                if data.get(col):
                    try:
                        data[col.replace("_json", "_data")] = json.loads(data[col])
                    except Exception:
                        data[col.replace("_json", "_data")] = None
                else:
                    data[col.replace("_json", "_data")] = None
            return data

    def list_projects(self, limit: int = 25) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, topic, niche, language_tone, target_minutes,
                       current_step, status, youtube_url, created_at, updated_at
                FROM projects
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
            return [dict(r) for r in rows]

    def update_project_stage(
        self,
        project_id: str,
        *,
        current_step: Optional[int] = None,
        status: Optional[str] = None,
        agent1_data: Optional[Dict[str, Any]] = None,
        agent2_data: Optional[Dict[str, Any]] = None,
        agent3_data: Optional[Dict[str, Any]] = None,
        agent4_data: Optional[Dict[str, Any]] = None,
        youtube_video_id: Optional[str] = None,
        youtube_url: Optional[str] = None,
        target_channel_id: Optional[str] = None,
        target_channel_title: Optional[str] = None,
        target_playlist_id: Optional[str] = None,
        target_playlist_title: Optional[str] = None,
    ) -> None:
        fields: List[str] = ["updated_at = ?"]
        values: List[Any] = [_utc_now()]

        if current_step is not None:
            fields.append("current_step = ?")
            values.append(int(current_step))
        if status is not None:
            fields.append("status = ?")
            values.append(status)
        if agent1_data is not None:
            fields.append("agent1_json = ?")
            values.append(json.dumps(agent1_data, ensure_ascii=False))
        if agent2_data is not None:
            fields.append("agent2_json = ?")
            values.append(json.dumps(agent2_data, ensure_ascii=False))
        if agent3_data is not None:
            fields.append("agent3_json = ?")
            values.append(json.dumps(agent3_data, ensure_ascii=False))
        if agent4_data is not None:
            fields.append("agent4_json = ?")
            values.append(json.dumps(agent4_data, ensure_ascii=False))
        if youtube_video_id is not None:
            fields.append("youtube_video_id = ?")
            values.append(youtube_video_id)
        if youtube_url is not None:
            fields.append("youtube_url = ?")
            values.append(youtube_url)
        if target_channel_id is not None:
            fields.append("target_channel_id = ?")
            values.append(target_channel_id)
        if target_channel_title is not None:
            fields.append("target_channel_title = ?")
            values.append(target_channel_title)
        if target_playlist_id is not None:
            fields.append("target_playlist_id = ?")
            values.append(target_playlist_id)
        if target_playlist_title is not None:
            fields.append("target_playlist_title = ?")
            values.append(target_playlist_title)

        values.append(project_id)
        with self._connect() as conn:
            conn.execute(f"UPDATE projects SET {', '.join(fields)} WHERE id = ?", values)

    # ------------------------------------------------------------------
    # Generation Queue CRUD (Async Worker Telemetry)
    # ------------------------------------------------------------------
    def clear_project_jobs(self, project_id: str, job_type: Optional[str] = None) -> None:
        with self._connect() as conn:
            if job_type:
                conn.execute(
                    "DELETE FROM generation_queue WHERE project_id = ? AND job_type = ?",
                    (project_id, job_type),
                )
            else:
                conn.execute("DELETE FROM generation_queue WHERE project_id = ?", (project_id,))

    def upsert_job(
        self,
        *,
        job_id: str,
        project_id: str,
        job_type: str,
        label: str,
        scene_index: int = 0,
        status: str = "queued",
        progress_pct: int = 0,
        message: str = "",
        output_path: Optional[str] = None,
        error_text: Optional[str] = None,
    ) -> str:
        now = _utc_now()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO generation_queue (
                    job_id, project_id, job_type, scene_index, label,
                    status, progress_pct, message, output_path, error_text,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(job_id) DO UPDATE SET
                    status = excluded.status,
                    progress_pct = excluded.progress_pct,
                    message = excluded.message,
                    output_path = COALESCE(excluded.output_path, generation_queue.output_path),
                    error_text = excluded.error_text,
                    updated_at = excluded.updated_at
                """,
                (
                    job_id,
                    project_id,
                    job_type,
                    int(scene_index),
                    label,
                    status,
                    int(max(0, min(100, progress_pct))),
                    message,
                    output_path,
                    error_text,
                    now,
                    now,
                ),
            )
        return job_id

    def get_project_jobs(self, project_id: str, job_type: Optional[str] = None) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            if job_type:
                rows = conn.execute(
                    """
                    SELECT * FROM generation_queue
                    WHERE project_id = ? AND job_type = ?
                    ORDER BY scene_index ASC, created_at ASC
                    """,
                    (project_id, job_type),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT * FROM generation_queue
                    WHERE project_id = ?
                    ORDER BY created_at ASC, scene_index ASC
                    """,
                    (project_id,),
                ).fetchall()
            return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # OAuth Token Persistence
    # ------------------------------------------------------------------
    def save_oauth_token(
        self,
        provider: str,
        token_dict: Dict[str, Any],
        *,
        account_email: str = "",
        channel_id: str = "",
        channel_title: str = "",
        scopes: Optional[List[str]] = None,
    ) -> None:
        now = _utc_now()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO oauth_tokens (
                    provider, account_email, channel_id, channel_title,
                    token_json, scopes, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(provider) DO UPDATE SET
                    account_email = excluded.account_email,
                    channel_id = excluded.channel_id,
                    channel_title = excluded.channel_title,
                    token_json = excluded.token_json,
                    scopes = excluded.scopes,
                    updated_at = excluded.updated_at
                """,
                (
                    provider,
                    account_email,
                    channel_id,
                    channel_title,
                    json.dumps(token_dict, ensure_ascii=False),
                    ",".join(scopes or []),
                    now,
                ),
            )

    def get_oauth_token(self, provider: str = "youtube") -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM oauth_tokens WHERE provider = ?", (provider,)).fetchone()
            if not row:
                return None
            record = dict(row)
            try:
                record["token_dict"] = json.loads(record["token_json"])
            except Exception:
                record["token_dict"] = {}
            return record

    def delete_oauth_token(self, provider: str = "youtube") -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM oauth_tokens WHERE provider = ?", (provider,))

    def list_youtube_channels(self) -> List[Dict[str, Any]]:
        """Lists ALL unique connected YouTube channels stored in SQLite (`youtube` or `youtube:<channel_id>`)."""
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM oauth_tokens
                WHERE provider = 'youtube' OR provider LIKE 'youtube:%'
                ORDER BY
                    CASE WHEN channel_id LIKE 'UC%' THEN 0 ELSE 1 END ASC,
                    updated_at DESC
                """
            ).fetchall()
            out: List[Dict[str, Any]] = []
            seen_ids = set()
            seen_refresh = set()
            seen_titles = set()
            for r in rows:
                rec = dict(r)
                try:
                    rec["token_dict"] = json.loads(rec["token_json"])
                except Exception:
                    rec["token_dict"] = {}
                cid = (rec.get("channel_id") or rec["token_dict"].get("connected_channel_id") or "").strip()
                ref_tok = (rec["token_dict"].get("refresh_token") or "").strip()
                title_norm = (rec.get("channel_title") or rec["token_dict"].get("connected_channel_title") or "").strip().lower()
                if cid and cid in seen_ids:
                    continue
                if ref_tok and ref_tok in seen_refresh:
                    continue
                if title_norm and not cid.startswith("UC") and title_norm in seen_titles:
                    continue
                if cid:
                    seen_ids.add(cid)
                if ref_tok:
                    seen_refresh.add(ref_tok)
                if title_norm:
                    seen_titles.add(title_norm)
                rec["resolved_channel_id"] = cid or rec["provider"]
                out.append(rec)
            return out

    def deduplicate_youtube_channels(self) -> int:
        """
        Physically purges redundant duplicate YouTube channel rows from SQLite (same channel_id,
        same refresh_token, or legacy placeholder rows duplicating a real `UC...` channel).
        Returns the number of duplicate rows removed.
        """
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT provider, channel_id, channel_title, token_json, updated_at
                FROM oauth_tokens
                WHERE provider = 'youtube' OR provider LIKE 'youtube:%'
                ORDER BY
                    CASE WHEN channel_id LIKE 'UC%' THEN 0 ELSE 1 END ASC,
                    CASE WHEN provider LIKE 'youtube:UC%' THEN 0 ELSE 1 END ASC,
                    updated_at DESC
                """
            ).fetchall()
            keep_providers = set()
            seen_ids = set()
            seen_refresh = set()
            seen_titles = set()
            to_delete: List[str] = []
            for r in rows:
                prov = r["provider"]
                try:
                    td = json.loads(r["token_json"])
                except Exception:
                    td = {}
                cid = (r["channel_id"] or td.get("connected_channel_id") or "").strip()
                ref_tok = (td.get("refresh_token") or "").strip()
                title_norm = (r["channel_title"] or td.get("connected_channel_title") or "").strip().lower()

                is_dup = False
                if cid and cid in seen_ids:
                    is_dup = True
                elif ref_tok and ref_tok in seen_refresh:
                    is_dup = True
                elif title_norm and not cid.startswith("UC") and title_norm in seen_titles:
                    is_dup = True

                if is_dup:
                    to_delete.append(prov)
                else:
                    keep_providers.add(prov)
                    if cid:
                        seen_ids.add(cid)
                    if ref_tok:
                        seen_refresh.add(ref_tok)
                    if title_norm:
                        seen_titles.add(title_norm)

            for prov in to_delete:
                conn.execute("DELETE FROM oauth_tokens WHERE provider = ?", (prov,))
            return len(to_delete)

    def get_youtube_channel(self, channel_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Fetches a specific connected YouTube channel by `channel_id` (or first connected channel if omitted)."""
        channels = self.list_youtube_channels()
        if not channels:
            return None
        if not channel_id:
            return channels[0]
        target = channel_id.strip()
        for ch in channels:
            if ch.get("channel_id") == target or ch.get("provider") == f"youtube:{target}" or ch.get("provider") == target:
                return ch
        return None

    def delete_youtube_channel(self, channel_id: str) -> None:
        target = (channel_id or "").strip()
        if not target:
            return
        with self._connect() as conn:
            conn.execute(
                "DELETE FROM oauth_tokens WHERE channel_id = ? OR provider = ? OR provider = ?",
                (target, f"youtube:{target}", target),
            )

    # ------------------------------------------------------------------
    # Publish Records CRUD
    # ------------------------------------------------------------------
    def upsert_publish_record(
        self,
        *,
        record_id: str,
        project_id: str,
        title: str,
        privacy_status: str,
        scheduled_publish_at: Optional[str] = None,
        playlist_id: Optional[str] = None,
        video_id: Optional[str] = None,
        studio_url: Optional[str] = None,
        watch_url: Optional[str] = None,
        upload_progress_pct: int = 0,
        status: str = "uploading",
        error_text: Optional[str] = None,
    ) -> str:
        now = _utc_now()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO publish_records (
                    id, project_id, video_id, studio_url, watch_url,
                    title, privacy_status, scheduled_publish_at, playlist_id,
                    upload_progress_pct, status, error_text, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    video_id = COALESCE(excluded.video_id, publish_records.video_id),
                    studio_url = COALESCE(excluded.studio_url, publish_records.studio_url),
                    watch_url = COALESCE(excluded.watch_url, publish_records.watch_url),
                    upload_progress_pct = excluded.upload_progress_pct,
                    status = excluded.status,
                    error_text = excluded.error_text,
                    updated_at = excluded.updated_at
                """,
                (
                    record_id,
                    project_id,
                    video_id,
                    studio_url,
                    watch_url,
                    title,
                    privacy_status,
                    scheduled_publish_at,
                    playlist_id,
                    int(max(0, min(100, upload_progress_pct))),
                    status,
                    error_text,
                    now,
                    now,
                ),
            )
        return record_id

    def get_publish_records(self, project_id: Optional[str] = None, limit: int = 20) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            if project_id:
                rows = conn.execute(
                    "SELECT * FROM publish_records WHERE project_id = ? ORDER BY updated_at DESC LIMIT ?",
                    (project_id, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM publish_records ORDER BY updated_at DESC LIMIT ?",
                    (limit,),
                ).fetchall()
            return [dict(r) for r in rows]


_DB_SINGLETON: Optional[OmniDatabase] = None
_DB_SINGLETON_LOCK = threading.Lock()


def get_db() -> OmniDatabase:
    global _DB_SINGLETON
    if _DB_SINGLETON is None:
        with _DB_SINGLETON_LOCK:
            if _DB_SINGLETON is None:
                _DB_SINGLETON = OmniDatabase()
    return _DB_SINGLETON
