from __future__ import annotations

import shutil
from pathlib import Path
from typing import BinaryIO

from dicomflow.core.config import Settings
from dicomflow.core.exceptions import ChunkUploadError, UploadTooLargeError


class LocalFilesystemStorage:
    """Local disk layout under data/{uploads,work,outputs}/."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.settings.ensure_dirs()

    def upload_dir(self, upload_id: str) -> Path:
        return self.settings.uploads_dir / upload_id

    def chunks_dir(self, upload_id: str) -> Path:
        return self.upload_dir(upload_id) / "chunks"

    def prepare_chunk_upload(self, upload_id: str) -> Path:
        """Create upload + chunks directories for a multi-part session."""
        root = self.upload_dir(upload_id)
        root.mkdir(parents=True, exist_ok=True)
        parts = self.chunks_dir(upload_id)
        parts.mkdir(parents=True, exist_ok=True)
        return parts

    def chunk_path(self, upload_id: str, index: int) -> Path:
        return self.chunks_dir(upload_id) / f"{index:05d}.part"

    def write_chunk(
        self,
        upload_id: str,
        index: int,
        stream: BinaryIO,
        *,
        max_chunk_bytes: int,
    ) -> int:
        """
        Write one part to disk. Returns bytes written.
        Rejects parts larger than max_chunk_bytes.
        """
        if index < 0:
            raise ChunkUploadError("无效的分片序号")
        dest_dir = self.chunks_dir(upload_id)
        if not dest_dir.is_dir():
            raise ChunkUploadError("上传会话不存在或已过期")
        dest = self.chunk_path(upload_id, index)
        written = 0
        buf_size = 1024 * 1024
        tmp = dest.with_suffix(".part.tmp")
        try:
            with tmp.open("wb") as f:
                while True:
                    chunk = stream.read(buf_size)
                    if not chunk:
                        break
                    written += len(chunk)
                    if written > max_chunk_bytes:
                        raise ChunkUploadError(
                            "分片过大",
                            detail=f"max_chunk_bytes={max_chunk_bytes}",
                        )
                    f.write(chunk)
            tmp.replace(dest)
        except Exception:
            tmp.unlink(missing_ok=True)
            raise
        return written

    def assemble_chunks(
        self,
        upload_id: str,
        filename: str,
        *,
        total_chunks: int,
        expected_size: int,
        max_bytes: int | None = None,
    ) -> Path:
        """Concatenate parts into the final file; remove the chunks/ dir."""
        safe = Path(filename).name or "upload.bin"
        dest_dir = self.upload_dir(upload_id)
        if not dest_dir.is_dir():
            raise ChunkUploadError("上传会话不存在或已过期")
        dest = dest_dir / safe
        limit = max_bytes if max_bytes is not None else self.settings.max_upload_bytes
        if expected_size > limit:
            raise UploadTooLargeError(
                "上传文件超过大小限制",
                detail=f"max_bytes={limit}",
            )
        written = 0
        try:
            with dest.open("wb") as out:
                for i in range(total_chunks):
                    part = self.chunk_path(upload_id, i)
                    if not part.is_file():
                        raise ChunkUploadError(
                            f"缺少分片 {i}",
                            detail=f"chunk_index={i}",
                        )
                    with part.open("rb") as inp:
                        while True:
                            buf = inp.read(1024 * 1024)
                            if not buf:
                                break
                            written += len(buf)
                            if written > limit:
                                raise UploadTooLargeError(
                                    "上传文件超过大小限制",
                                    detail=f"max_bytes={limit}",
                                )
                            out.write(buf)
            if written != expected_size:
                dest.unlink(missing_ok=True)
                raise ChunkUploadError(
                    "分片合并后大小与声明不一致",
                    detail=f"expected={expected_size} actual={written}",
                )
        except Exception:
            if dest.exists():
                dest.unlink(missing_ok=True)
            raise
        # Drop part files after successful assemble
        chunks = self.chunks_dir(upload_id)
        if chunks.exists():
            shutil.rmtree(chunks, ignore_errors=True)
        return dest

    def save_upload(
        self,
        upload_id: str,
        filename: str,
        stream: BinaryIO,
        *,
        max_bytes: int | None = None,
    ) -> Path:
        dest_dir = self.upload_dir(upload_id)
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
