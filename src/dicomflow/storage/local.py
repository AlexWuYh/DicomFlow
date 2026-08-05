from __future__ import annotations

import shutil
from pathlib import Path
from typing import BinaryIO

from dicomflow.core.config import Settings
from dicomflow.core.exceptions import UploadTooLargeError


class LocalFilesystemStorage:
    """Local disk layout under data/{uploads,work,outputs}/."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.settings.ensure_dirs()

    def save_upload(
        self,
        upload_id: str,
        filename: str,
        stream: BinaryIO,
        *,
        max_bytes: int | None = None,
    ) -> Path:
        dest_dir = self.settings.uploads_dir / upload_id
        dest_dir.mkdir(parents=True, exist_ok=True)
        # filename must already be sanitized by caller
        safe = Path(filename).name or "upload.bin"
        dest = dest_dir / safe
        limit = max_bytes if max_bytes is not None else self.settings.max_upload_bytes
        written = 0
        chunk_size = 1024 * 1024
        try:
            with dest.open("wb") as f:
                while True:
                    chunk = stream.read(chunk_size)
                    if not chunk:
                        break
                    written += len(chunk)
                    if written > limit:
                        raise UploadTooLargeError(
                            "上传文件超过大小限制",
                            detail=f"max_bytes={limit}",
                        )
                    f.write(chunk)
        except UploadTooLargeError:
            if dest.exists():
                dest.unlink(missing_ok=True)
            if dest_dir.exists():
                shutil.rmtree(dest_dir, ignore_errors=True)
            raise
        except Exception:
            if dest.exists():
                dest.unlink(missing_ok=True)
            raise
        return dest

    def job_work_dir(self, job_id: str) -> Path:
        path = self.settings.work_dir / job_id
        path.mkdir(parents=True, exist_ok=True)
        return path

    def job_output_dir(self, job_id: str) -> Path:
        path = self.settings.outputs_dir / job_id
        path.mkdir(parents=True, exist_ok=True)
        return path

    def publish_output(self, job_id: str, local_path: Path) -> Path:
        out_dir = self.job_output_dir(job_id)
        target = out_dir / local_path.name
        if local_path.resolve() != target.resolve():
            shutil.copy2(local_path, target)
        return target

    def resolve_output_file(self, job_id: str, name: str) -> Path | None:
        """Safe resolve of a single output file by basename."""
        safe = Path(name).name
        if not safe or safe in {".", ".."}:
            return None
        # Reject path separators even if Path.name would strip
        if "/" in name or "\\" in name or ".." in name:
            return None
        path = (self.job_output_dir(job_id) / safe).resolve()
        root = self.job_output_dir(job_id).resolve()
        try:
            path.relative_to(root)
        except ValueError:
            return None
        return path if path.is_file() else None

    def delete_job(self, job_id: str) -> None:
        for root in (
            self.settings.work_dir / job_id,
            self.settings.outputs_dir / job_id,
        ):
            if root.exists():
                shutil.rmtree(root, ignore_errors=True)

    def delete_upload(self, upload_id: str) -> None:
        root = self.settings.uploads_dir / upload_id
        if root.exists():
            shutil.rmtree(root, ignore_errors=True)
