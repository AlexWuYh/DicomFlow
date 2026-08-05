from __future__ import annotations

from functools import lru_cache

from dicomflow.core.config import Settings, get_settings
from dicomflow.storage.local import LocalFilesystemStorage
from dicomflow.tasks.inprocess import InProcessQueue
from dicomflow.tasks.job_service import JobService
from dicomflow.tasks.store import JobStore


@lru_cache
def get_job_service() -> JobService:
    settings = get_settings()
    settings.ensure_dirs()
    storage = LocalFilesystemStorage(settings)
    queue = InProcessQueue(max_workers=max(1, settings.workers))
    store = JobStore(settings.data_dir / "dicomflow.db")
    return JobService(storage=storage, queue=queue, settings=settings, store=store)


def get_app_settings() -> Settings:
    return get_settings()
