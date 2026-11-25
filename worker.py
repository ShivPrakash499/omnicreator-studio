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
import os
import threading
import traceback
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Any, Callable, Dict, Optional

from backend.config import OmniStudioConfig
from storage.db import OmniDatabase, get_db

logger = logging.getLogger("omni_studio.worker")

DEFAULT_DAILY_COST_LIMIT_USD: float = float(os.getenv("OMNI_DAILY_COST_LIMIT_USD", "10.0") or "10.0")


class BudgetLimitExceededError(RuntimeError):
    """Raised when today's cumulative AI API spend would cross the user's hard daily cost limit."""

    def __init__(self, spent_usd: float, limit_usd: float, requested_usd: float = 0.0) -> None:
        self.spent_usd = round(float(spent_usd), 2)
        self.limit_usd = round(float(limit_usd), 2)
        self.requested_usd = round(float(requested_usd), 2)
        spent_inr = int(round(self.spent_usd * 85.5))
        limit_inr = int(round(self.limit_usd * 85.5))
        super().__init__(
            f"Daily Budget Guard paused generation: Today's AI spend (${self.spent_usd:.2f} / ≈ ₹{spent_inr:,}) "
            f"+ next step (${self.requested_usd:.2f}) exceeds your daily limit (${self.limit_usd:.2f} / ≈ ₹{limit_inr:,}). "
            f"All already-completed frames and clips are safely saved on disk. Increase your Daily Budget Limit in Studio if you want to continue."
        )


class BackgroundWorkerManager:
    """Singleton process-level background worker coordinator backed by SQLite telemetry & Daily Budget Throttle."""

    def __init__(
        self,
        max_workers: Optional[int] = None,
        db: Optional[OmniDatabase] = None,
        cost_limit_usd: Optional[float] = None,
    ) -> None:
        cfg = OmniStudioConfig()
        self.max_workers = max_workers or cfg.max_workers
        self.db = db or get_db()
        self._default_cost_limit_usd = float(cost_limit_usd) if cost_limit_usd is not None else DEFAULT_DAILY_COST_LIMIT_USD
        self._executor = ThreadPoolExecutor(max_workers=self.max_workers, thread_name_prefix="omni_worker")
        self._lock = threading.RLock()
        self._active_futures: Dict[str, Future[Any]] = {}

    # ------------------------------------------------------------------
    # Hard Daily Budget Throttle (`cost_limit`)
    # ------------------------------------------------------------------
    def get_daily_cost_limit_usd(self) -> float:
        raw = self.db.get_setting("daily_cost_limit_usd", "")
        if raw:
            try:
                val = float(raw)
                if val > 0:
                    return round(val, 2)
            except Exception:
                pass
        return round(self._default_cost_limit_usd, 2)

    def set_daily_cost_limit_usd(self, limit_usd: float) -> float:
        clamped = round(max(1.0, min(500.0, float(limit_usd))), 2)
        self.db.set_setting("daily_cost_limit_usd", f"{clamped:.2f}")
        return clamped

    def get_daily_budget_status(self, cost_limit_usd: Optional[float] = None) -> Dict[str, Any]:
        limit = round(float(cost_limit_usd), 2) if (cost_limit_usd is not None and cost_limit_usd > 0) else self.get_daily_cost_limit_usd()
        spent = round(self.db.get_daily_spend_usd(), 2)
        remaining = round(max(0.0, limit - spent), 2)
        pct = min(100, int(round((spent / max(0.01, limit)) * 100)))
        return {
            "spent_usd": spent,
            "limit_usd": limit,
            "remaining_usd": remaining,
            "pct_used": pct,
            "is_exceeded": spent >= limit,
            "breakdown": self.db.get_daily_spend_breakdown(),
        }

    def check_daily_budget(
        self,
        next_cost_usd: float = 0.0,
        *,
        cost_limit_usd: Optional[float] = None,
    ) -> float:
        """
        Enforces the hard daily spend cap BEFORE executing any paid AI API call.
        Raises `BudgetLimitExceededError` if today's spend + `next_cost_usd` crosses `cost_limit_usd`.
        Returns remaining daily budget (USD) if allowed.
        """
        with self._lock:
            limit = round(float(cost_limit_usd), 2) if (cost_limit_usd is not None and cost_limit_usd > 0) else self.get_daily_cost_limit_usd()
            spent = self.db.get_daily_spend_usd()
            req = max(0.0, float(next_cost_usd))
            if (req > 0.0 and (spent + req) > limit + 1e-6) or (req == 0.0 and spent >= limit):
                raise BudgetLimitExceededError(spent_usd=spent, limit_usd=limit, requested_usd=req)
            return round(max(0.0, limit - spent), 2)

    def record_api_spend(
        self,
        project_id: str,
        operation: str,
        estimated_usd: float,
        *,
        model: str = "",
    ) -> float:
        with self._lock:
            return self.db.record_api_spend(project_id, operation, estimated_usd, model=model)

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
        estimated_cost_usd: float = 0.0,
        cost_limit_usd: Optional[float] = None,
    ) -> bool:
        """
        Submits a background callable if not already running under `task_key`.
        Enforces the hard Daily Budget Throttle before launching paid tasks.
        Returns True if newly launched, False if already in progress.
        """
        kwargs = kwargs or {}
        with self._lock:
            existing = self._active_futures.get(task_key)
            if existing is not None and not existing.done():
                return False

            # Hard pre-flight budget check: refuse to launch new paid jobs if daily budget is already exhausted
            if float(estimated_cost_usd or 0.0) > 0.0:
                self.check_daily_budget(next_cost_usd=0.0, cost_limit_usd=cost_limit_usd)

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
