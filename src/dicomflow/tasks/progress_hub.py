"""In-process pub/sub for job progress (SSE / future WebSocket)."""

from __future__ import annotations

import queue
import threading
from collections import defaultdict
from typing import Any


class ProgressHub:
    """
    Thread-safe fan-out of job status snapshots.

    Workers (thread pool) call publish(); SSE handlers subscribe() with a Queue
    and wait without polling SQLite on a tight loop.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._subs: dict[str, list[queue.Queue]] = defaultdict(list)

    def subscribe(self, job_id: str, *, maxsize: int = 32) -> queue.Queue:
        q: queue.Queue = queue.Queue(maxsize=maxsize)
        with self._lock:
            self._subs[job_id].append(q)
        return q

    def unsubscribe(self, job_id: str, q: queue.Queue) -> None:
        with self._lock:
            lst = self._subs.get(job_id)
            if not lst:
                return
            try:
                lst.remove(q)
            except ValueError:
                pass
            if not lst:
                self._subs.pop(job_id, None)

    def publish(self, job_id: str, payload: dict[str, Any]) -> None:
        with self._lock:
            subscribers = list(self._subs.get(job_id, ()))
        for q in subscribers:
            try:
                # Drop oldest if full so slow clients do not block workers
                if q.full():
                    try:
                        q.get_nowait()
                    except queue.Empty:
                        pass
                q.put_nowait(payload)
            except queue.Full:
                pass


# Process-wide hub (single-worker InProcessQueue design)
progress_hub = ProgressHub()
