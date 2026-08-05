from __future__ import annotations

from pathlib import Path
from typing import BinaryIO, Protocol


class StoragePort(Protocol):
    def save_upload(
        self,
        upload_id: str,
        filename: str,
        stream: BinaryIO,
        *,
        max_bytes: int | None = None,
    ) -> Path: ...

    def job_work_dir(self, job_id: str) -> Path: ...

    def job_output_dir(self, job_id: str) -> Path: ...

    def publish_output(self, job_id: str, local_path: Path) -> Path: ...

    def resolve_output_file(self, job_id: str, name: str) -> Path | None: ...

    def delete_job(self, job_id: str) -> None: ...
