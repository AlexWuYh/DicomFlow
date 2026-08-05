from __future__ import annotations

import mimetypes
import logging
import uuid
from datetime import datetime
from pathlib import Path

from dicomflow.core.config import Settings, get_settings
from dicomflow.core.exceptions import DicomFlowError
from dicomflow.core.models import (
    ConvertParams,
    JobError,
    JobPhase,
    JobRecord,
    JobResult,
    JobStatus,
    OutputArtifact,
    ProgressInfo,
    UploadRecord,
)
from dicomflow.core.timeutil import as_utc, to_iso, utc_now
from dicomflow.engine.pipeline import ProgressEvent, convert_dicom_package
from dicomflow.storage.base import StoragePort
from dicomflow.tasks.base import QueuePort
from dicomflow.tasks.store import JobStore

logger = logging.getLogger(__name__)

PREVIEW_EXTS = {".mp4", ".gif", ".webm"}


def _guess_type(name: str) -> str:
    return mimetypes.guess_type(name)[0] or "application/octet-stream"


class JobService:
    """Orchestrates uploads + jobs with SQLite-backed metadata."""

    def __init__(
        self,
        storage: StoragePort,
        queue: QueuePort,
        settings: Settings | None = None,
        store: JobStore | None = None,
    ):
        self.storage = storage
        self.queue = queue
        self.settings = settings or get_settings()
        if store is not None:
            self.store = store
        else:
            db_path = self.settings.data_dir / "dicomflow.db"
            self.store = JobStore(db_path)
        # After restart, mark interrupted in-flight jobs
        n = self.store.fail_stale_running()
        if n:
            logger.warning("Marked %s interrupted job(s) as FAILED after restart", n)

    # ── Upload ──────────────────────────────────────────────

    def create_upload(
        self,
        upload_stream,
        filename: str,
        *,
        max_bytes: int | None = None,
    ) -> UploadRecord:
        upload_id = uuid.uuid4().hex
        path = self.storage.save_upload(
            upload_id,
            filename,
            upload_stream,
            max_bytes=max_bytes if max_bytes is not None else self.settings.max_upload_bytes,
        )
        rec = UploadRecord(
            upload_id=upload_id,
            filename=filename,
            size_bytes=path.stat().st_size,
            path=str(path),
            created_at=utc_now(),
        )
        self.store.save_upload(rec)
        return rec

    def get_upload(self, upload_id: str) -> UploadRecord | None:
        return self.store.get_upload(upload_id)

    def purge_older_than(self, cutoff: datetime) -> tuple[int, int]:
        """
        Drop persisted upload/job records older than cutoff.
        Returns (uploads_removed, jobs_removed). Disk cleanup is separate.
        """
        cutoff_iso = to_iso(as_utc(cutoff))
        uploads_removed = self.store.delete_uploads_before(cutoff_iso)
        jobs_removed = self.store.delete_jobs_before(cutoff_iso)
        return uploads_removed, jobs_removed

    # ── Jobs ────────────────────────────────────────────────

    def start_job(self, upload_id: str, params: ConvertParams) -> JobRecord:
        upload = self.get_upload(upload_id)
        if not upload:
            raise KeyError("upload not found")
        upload_path = Path(upload.path)
        if not upload_path.is_file():
            raise FileNotFoundError("upload file missing on disk")

        now = utc_now()
        job_id = uuid.uuid4().hex
        record = JobRecord(
            job_id=job_id,
            upload_id=upload_id,
            status=JobStatus.PENDING,
            params=params,
            source_name=upload.filename,
            progress=ProgressInfo(phase=JobPhase.PENDING, percent=0, message="排队中"),
            created_at=now,
            updated_at=now,
        )
        self.store.save_job(record)

        def runner() -> None:
            self._run(job_id, upload_path)

        self.queue.enqueue(job_id, runner)
        return record

    def get(self, job_id: str) -> JobRecord | None:
        return self.store.get_job(job_id)

    def _update(self, job_id: str, **kwargs) -> None:
        rec = self.store.get_job(job_id)
        if rec is None:
            logger.warning("update skipped; job missing: %s", job_id)
            return
        data = rec.model_dump()
        data.update(kwargs)
        data["updated_at"] = utc_now()
        self.store.save_job(JobRecord.model_validate(data))

    def _on_progress(self, job_id: str, event: ProgressEvent) -> None:
        phase = (
            JobPhase(event.phase)
            if event.phase in JobPhase.__members__
            else JobPhase.CONVERTING
        )
        if event.phase == "SUCCEEDED":
            phase = JobPhase.SUCCEEDED
        status = (
            JobStatus.SUCCEEDED if phase == JobPhase.SUCCEEDED else JobStatus.RUNNING
        )
        self._update(
            job_id,
            status=status,
            progress=ProgressInfo(
                phase=phase,
                percent=event.percent,
                message=event.message,
                series_index=event.series_index,
                series_total=event.series_total,
                frame_index=event.frame_index,
                frame_total=event.frame_total,
            ),
        )

    def _build_artifacts(
        self,
        out_dir: Path,
        primary: Path,
        series_outputs: list[Path],
        series_names: list[str],
    ) -> list[OutputArtifact]:
        artifacts: list[OutputArtifact] = []
        seen: set[str] = set()

        def add(path: Path, kind: str) -> None:
            if not path.exists():
                return
            name = path.name
            if name in seen:
                return
            seen.add(name)
            ext = path.suffix.lower()
            artifacts.append(
                OutputArtifact(
                    name=name,
                    kind=kind,
                    size_bytes=path.stat().st_size,
                    content_type=_guess_type(name),
                    previewable=ext in PREVIEW_EXTS,
                )
            )

        for p in series_outputs:
            target = out_dir / p.name if p.parent != out_dir else p
            if target.exists():
                add(target, "series")
            elif p.exists():
                add(p, "series")

        if primary.suffix.lower() == ".zip":
            add(primary, "zip")
        elif "merged" in primary.name:
            add(primary, "merged")
        else:
            add(primary, "series")

        for p in sorted(out_dir.iterdir()):
            if p.is_file() and p.suffix.lower() in PREVIEW_EXTS:
                kind = "merged" if "merged" in p.name else "series"
                add(p, kind)

        return artifacts

    def _run(self, job_id: str, upload_path: Path) -> None:
        self._update(
            job_id,
            status=JobStatus.RUNNING,
            progress=ProgressInfo(
                phase=JobPhase.EXTRACTING, percent=1, message="开始处理"
            ),
        )
        try:
            rec = self.get(job_id)
            assert rec is not None
            work_dir = self.storage.job_work_dir(job_id)
            out_dir = self.storage.job_output_dir(job_id)

            result = convert_dicom_package(
                upload_path,
                out_dir,
                params=rec.params,
                work_dir=work_dir,
                progress_callback=lambda e: self._on_progress(job_id, e),
                max_extract_files=self.settings.max_extract_files,
                max_extract_bytes=self.settings.max_extract_bytes,
                max_ratio=self.settings.max_compression_ratio,
            )
            primary = result.output_files[0]
            published = self.storage.publish_output(job_id, primary)

            for sp in result.series_outputs:
                if sp.exists():
                    self.storage.publish_output(job_id, sp)

            artifacts = self._build_artifacts(
                out_dir,
                published,
                result.series_outputs,
                result.series_names,
            )
            self._update(
                job_id,
                status=JobStatus.SUCCEEDED,
                progress=ProgressInfo(
                    phase=JobPhase.SUCCEEDED, percent=100, message="完成"
                ),
                result=JobResult(
                    download_name=published.name,
                    content_type=_guess_type(published.name),
                    size_bytes=published.stat().st_size,
                    outputs=artifacts,
                ),
            )
        except DicomFlowError as exc:
            self._update(
                job_id,
                status=JobStatus.FAILED,
                progress=ProgressInfo(
                    phase=JobPhase.FAILED, percent=0, message=exc.message
                ),
                error=JobError(code=exc.code, message=exc.message, detail=exc.detail),
            )
        except Exception as exc:  # noqa: BLE001
            self._update(
                job_id,
                status=JobStatus.FAILED,
                progress=ProgressInfo(
                    phase=JobPhase.FAILED, percent=0, message="内部错误"
                ),
                error=JobError(code="INTERNAL", message=str(exc)),
            )

    def resolve_download(self, job_id: str) -> Path | None:
        rec = self.get(job_id)
        if not rec or rec.status != JobStatus.SUCCEEDED or not rec.result:
            return None
        return self.storage.resolve_output_file(job_id, rec.result.download_name)

    def resolve_file(self, job_id: str, name: str) -> Path | None:
        rec = self.get(job_id)
        if not rec or rec.status != JobStatus.SUCCEEDED:
            return None
        return self.storage.resolve_output_file(job_id, name)
