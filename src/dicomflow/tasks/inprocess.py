from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Callable


class InProcessQueue:
    """Simple background thread pool — default for local single-user use."""

    def __init__(self, max_workers: int = 1):
        self._pool = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="dicomflow")

    def enqueue(self, job_id: str, runner: Callable[[], None]) -> None:
        self._pool.submit(self._wrap, job_id, runner)

    @staticmethod
    def _wrap(job_id: str, runner: Callable[[], None]) -> None:
        try:
            runner()
        except Exception:  # noqa: BLE001
            # JobService should catch and record; this is last-resort log
            import logging

            logging.exception("Job %s failed in worker", job_id)

    def shutdown(self, wait: bool = False) -> None:
        self._pool.shutdown(wait=wait, cancel_futures=not wait)
