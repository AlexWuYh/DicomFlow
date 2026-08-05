from __future__ import annotations

from typing import Callable, Protocol


class QueuePort(Protocol):
    def enqueue(self, job_id: str, runner: Callable[[], None]) -> None: ...
