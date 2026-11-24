"""
OMNI STUDIO — Asynchronous Background Task Processor (`worker.py`)
==================================================================
Prevents Streamlit UI timeouts during heavy AI generation, FFmpeg rendering,
and chunked YouTube resumable uploads by executing long-running jobs on a
managed background ThreadPoolExecutor while persisting real-time progress and
logs into SQLite (`storage/omni_studio.db`).

Can be imported directly by `app.py` (embedded background thread manager) OR
executed standalone as a CLI worker diagnostic (`python worker.py --status`).
"""

from __future__ import annotations

import argparse
import logging
import threading
import traceback
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Any, Callable, Dict, Optional

from backend.config import OmniStudioConfig
from storage.db import OmniDatabase, get_db

logger = logging.getLogger("omni_studio.worker")


class BackgroundWorkerManager:
    """Singleton process-level background worker coordinator backed by SQLite telemetry."""

    def __init__(self, max_workers: Optional[int] = None, db: Optional[OmniDatabase] = None) -> None:
        cfg = OmniStudioConfig()
        self.max_workers = max_workers or cfg.max_workers
        self.db = db or get_db()
        self._executor = ThreadPoolExecutor(max_workers=self.max_workers, thread_name_prefix="omni_worker")
        self._lock = threading.RLock()
        self._active_futures: Dict[str, Future[Any]] = {}

    def is_running(self, task_key: str) -> bool:
        with self._lock:
            fut = self._active_futures.get(task_key)
            return bool(fut is not None and not fut.done())

    def get_task_error(self, task_key: str) -> Optional[str]:
        with self._lock:
            fut = self._active_futures.get(task_key)
            if fut is None or not fut.done():
                return None
            exc = fut.exception()
            return str(exc) if exc else None

    def submit_task(
        self,
        *,
        task_key: str,
        project_id: str,
        job_type: str,
        label: str,
        fn: Callable[..., Any],
        args: tuple = (),
        kwargs: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        Submits a background callable if not already running under `task_key`.
        Returns True if newly launched, False if already in progress.
        """
        kwargs = kwargs or {}
        with self._lock:
            existing = self._active_futures.get(task_key)
            if existing is not None and not existing.done():
                return False

            self.db.upsert_job(
                job_id=task_key,
                project_id=project_id,
                job_type=job_type,
                label=label,
                scene_index=0,
                status="running",
                progress_pct=2,
                message="Queued on background worker...",
            )

            def _wrapped() -> Any:
                try:
                    result = fn(*args, **kwargs)
                    self.db.upsert_job(
                        job_id=task_key,
                        project_id=project_id,
                        job_type=job_type,
                        label=label,
                        scene_index=0,
                        status="completed",
                        progress_pct=100,
                        message="Completed ✅",
                    )
                    return result
                except Exception as exc:
                    tb = traceback.format_exc()
                    logger.error("Background worker task '%s' failed: %s\n%s", task_key, exc, tb)
                    self.db.upsert_job(
                        job_id=task_key,
                        project_id=project_id,
                        job_type=job_type,
                        label=label,
                        scene_index=0,
                        status="failed",
                        progress_pct=0,
                        message=f"Failed: {exc}",
                        error_text=tb[-1500:],
                    )
                    raise

            self._active_futures[task_key] = self._executor.submit(_wrapped)
            return True


_WORKER_SINGLETON: Optional[BackgroundWorkerManager] = None
_WORKER_LOCK = threading.Lock()


def get_worker_manager() -> BackgroundWorkerManager:
    global _WORKER_SINGLETON
    with _WORKER_LOCK:
        if _WORKER_SINGLETON is None:
            _WORKER_SINGLETON = BackgroundWorkerManager()
        return _WORKER_SINGLETON


def _cli() -> None:
    parser = argparse.ArgumentParser(description="OMNI STUDIO Background Worker Telemetry CLI")
    parser.add_argument("--status", action="store_true", help="Print recent SQLite projects & job queue.")
    args = parser.parse_args()
    db = get_db()
    if args.status:
        projects = db.list_projects(limit=10)
        print(f"=== OMNI STUDIO SQLITE PROJECTS ({len(projects)}) ===")
        for p in projects:
            print(f"  [{p['id']}] Step {p['current_step']} | {p['status']} | {p['niche']} | {p['topic']}")
            jobs = db.get_project_jobs(p["id"])
            for j in jobs[:10]:
                print(f"     - {j['job_type']} | {j['label']} | {j['status']} ({j['progress_pct']}%) {j['message']}")


if __name__ == "__main__":
    _cli()
