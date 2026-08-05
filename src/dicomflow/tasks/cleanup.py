from __future__ import annotations

import logging
import shutil
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dicomflow.core.config import Settings
from dicomflow.tasks.job_service import JobService

logger = logging.getLogger(__name__)


@dataclass
class CleanupStats:
    removed_dirs: int = 0
    removed_jobs: int = 0
    removed_uploads: int = 0
    errors: int = 0


def _dir_mtime(path: Path) -> float:
    """Newest mtime among path and its children (fallback: path mtime)."""
    try:
        newest = path.stat().st_mtime
    except OSError:
        return 0.0
    try:
        for child in path.rglob("*"):
            try:
                newest = max(newest, child.stat().st_mtime)
            except OSError:
                continue
    except OSError:
        pass
    return newest


def cleanup_expired_dirs(
    root: Path,
    *,
    max_age: timedelta,
    now: float | None = None,
) -> tuple[int, int]:
    """
    Remove immediate subdirectories of root older than max_age.
    Returns (removed_count, error_count).
    """
    if not root.is_dir():
        return 0, 0
    cutoff = (now if now is not None else time.time()) - max_age.total_seconds()
    removed = 0
    errors = 0
    try:
        children = list(root.iterdir())
    except OSError as exc:
        logger.warning("Cannot list %s: %s", root, exc)
        return 0, 1

    for child in children:
        if not child.is_dir():
            # stray files at top level
            try:
                if child.is_file() and child.stat().st_mtime < cutoff:
                    child.unlink(missing_ok=True)
                    removed += 1
            except OSError:
                errors += 1
            continue
        try:
            if _dir_mtime(child) < cutoff:
                shutil.rmtree(child, ignore_errors=False)
                removed += 1
                logger.info("Cleaned expired path: %s", child)
        except OSError as exc:
            errors += 1
            logger.warning("Failed to remove %s: %s", child, exc)
    return removed, errors


def run_cleanup(settings: Settings, job_service: JobService | None = None) -> CleanupStats:
    """Purge disk artifacts and in-memory records older than job_ttl_hours."""
    stats = CleanupStats()
    ttl = max(1, int(settings.job_ttl_hours))
    max_age = timedelta(hours=ttl)
    now = time.time()

    for root in (settings.uploads_dir, settings.work_dir, settings.outputs_dir):
        removed, errors = cleanup_expired_dirs(root, max_age=max_age, now=now)
        stats.removed_dirs += removed
        stats.errors += errors

    if job_service is not None:
        cutoff = datetime.now(timezone.utc) - max_age
        ju, jj = job_service.purge_older_than(cutoff)
        stats.removed_uploads += ju
        stats.removed_jobs += jj

    if stats.removed_dirs or stats.removed_jobs or stats.removed_uploads:
        logger.info(
            "Cleanup done: dirs=%s uploads_meta=%s jobs_meta=%s errors=%s ttl_h=%s",
            stats.removed_dirs,
            stats.removed_uploads,
            stats.removed_jobs,
            stats.errors,
            ttl,
        )
    return stats


class CleanupScheduler:
    """Background daemon that runs cleanup on an interval."""

    def __init__(
        self,
        settings: Settings,
        job_service: JobService,
        *,
        interval_seconds: float | None = None,
    ):
        self.settings = settings
        self.job_service = job_service
        self.interval_seconds = interval_seconds
        if self.interval_seconds is None:
            self.interval_seconds = float(
                max(60, int(getattr(settings, "cleanup_interval_seconds", 900)))
            )
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._loop,
            name="dicomflow-cleanup",
            daemon=True,
        )
        self._thread.start()
        logger.info(
            "Cleanup scheduler started (ttl=%sh interval=%ss)",
            self.settings.job_ttl_hours,
            int(self.interval_seconds),
        )

    def stop(self, timeout: float = 2.0) -> None:
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout)

    def _loop(self) -> None:
        # Run once shortly after boot so restarts also reclaim disk
        self._safe_run()
        while not self._stop.wait(self.interval_seconds):
            self._safe_run()

    def _safe_run(self) -> None:
        try:
            run_cleanup(self.settings, self.job_service)
        except Exception:  # noqa: BLE001
            logger.exception("Cleanup cycle failed")
