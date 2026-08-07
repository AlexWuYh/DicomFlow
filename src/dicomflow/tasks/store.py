from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path

from dicomflow.core.models import (
    ChunkSessionRecord,
    ConvertParams,
    JobError,
    JobPhase,
    JobRecord,
    JobResult,
    JobStatus,
    ProgressInfo,
    UploadRecord,
)
from dicomflow.core.timeutil import from_iso, to_iso, utc_now


class JobStore:
    """SQLite persistence for uploads + jobs (thread-safe)."""

    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(
            str(self.db_path),
            check_same_thread=False,
            isolation_level=None,  # autocommit; we use explicit transactions
        )
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def _init_schema(self) -> None:
        with self._lock:
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS uploads (
                    upload_id TEXT PRIMARY KEY,
                    filename TEXT NOT NULL,
                    size_bytes INTEGER NOT NULL,
                    path TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS chunk_sessions (
                    upload_id TEXT PRIMARY KEY,
                    filename TEXT NOT NULL,
                    size_bytes INTEGER NOT NULL,
                    total_chunks INTEGER NOT NULL,
                    chunk_size_bytes INTEGER NOT NULL,
                    received_json TEXT NOT NULL DEFAULT '[]',
                    created_at TEXT NOT NULL,
                    completed INTEGER NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS jobs (
                    job_id TEXT PRIMARY KEY,
                    upload_id TEXT,
                    status TEXT NOT NULL,
                    params_json TEXT NOT NULL,
                    progress_json TEXT NOT NULL,
                    result_json TEXT,
                    error_json TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    source_name TEXT,
                    meta_json TEXT NOT NULL DEFAULT '{}'
                );
                CREATE INDEX IF NOT EXISTS idx_jobs_created ON jobs(created_at);
                CREATE INDEX IF NOT EXISTS idx_uploads_created ON uploads(created_at);
                CREATE INDEX IF NOT EXISTS idx_chunk_sessions_created ON chunk_sessions(created_at);
                """
            )

    # ── Uploads ─────────────────────────────────────────────

    def save_upload(self, rec: UploadRecord) -> None:
        with self._lock:
            self._conn.execute(
                """
                INSERT OR REPLACE INTO uploads
                (upload_id, filename, size_bytes, path, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    rec.upload_id,
                    rec.filename,
                    rec.size_bytes,
                    rec.path,
                    to_iso(rec.created_at),
                ),
            )

    def get_upload(self, upload_id: str) -> UploadRecord | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM uploads WHERE upload_id = ?",
                (upload_id,),
            ).fetchone()
        if not row:
            return None
        return UploadRecord(
            upload_id=row["upload_id"],
            filename=row["filename"],
            size_bytes=row["size_bytes"],
            path=row["path"],
            created_at=from_iso(row["created_at"]),
        )

    def delete_uploads_before(self, cutoff_iso: str) -> int:
        with self._lock:
            cur = self._conn.execute(
                "DELETE FROM uploads WHERE created_at < ?",
                (cutoff_iso,),
            )
            return cur.rowcount or 0

    # ── Chunk sessions ──────────────────────────────────────

    def save_chunk_session(self, rec: ChunkSessionRecord) -> None:
        with self._lock:
            self._conn.execute(
                """
                INSERT OR REPLACE INTO chunk_sessions
                (upload_id, filename, size_bytes, total_chunks, chunk_size_bytes,
                 received_json, created_at, completed)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    rec.upload_id,
                    rec.filename,
                    rec.size_bytes,
                    rec.total_chunks,
                    rec.chunk_size_bytes,
                    json.dumps(sorted(set(rec.received_indexes)), ensure_ascii=False),
                    to_iso(rec.created_at),
                    1 if rec.completed else 0,
                ),
            )

    def get_chunk_session(self, upload_id: str) -> ChunkSessionRecord | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM chunk_sessions WHERE upload_id = ?",
                (upload_id,),
            ).fetchone()
        if not row:
            return None
        try:
            received = json.loads(row["received_json"] or "[]")
        except json.JSONDecodeError:
            received = []
        if not isinstance(received, list):
            received = []
        return ChunkSessionRecord(
            upload_id=row["upload_id"],
            filename=row["filename"],
            size_bytes=row["size_bytes"],
            total_chunks=row["total_chunks"],
            chunk_size_bytes=row["chunk_size_bytes"],
            received_indexes=[int(x) for x in received],
            created_at=from_iso(row["created_at"]),
            completed=bool(row["completed"]),
        )

    def delete_chunk_session(self, upload_id: str) -> None:
        with self._lock:
            self._conn.execute(
                "DELETE FROM chunk_sessions WHERE upload_id = ?",
                (upload_id,),
            )

    def delete_chunk_sessions_before(self, cutoff_iso: str) -> int:
        with self._lock:
            cur = self._conn.execute(
                "DELETE FROM chunk_sessions WHERE created_at < ?",
                (cutoff_iso,),
            )
            return cur.rowcount or 0

    # ── Jobs ────────────────────────────────────────────────

    def save_job(self, rec: JobRecord) -> None:
        with self._lock:
            self._conn.execute(
                """
                INSERT OR REPLACE INTO jobs
                (job_id, upload_id, status, params_json, progress_json,
                 result_json, error_json, created_at, updated_at, source_name, meta_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    rec.job_id,
                    rec.upload_id,
                    rec.status.value,
                    rec.params.model_dump_json(),
                    rec.progress.model_dump_json(),
                    rec.result.model_dump_json() if rec.result else None,
                    rec.error.model_dump_json() if rec.error else None,
                    to_iso(rec.created_at),
                    to_iso(rec.updated_at),
                    rec.source_name,
                    json.dumps(rec.meta or {}, ensure_ascii=False),
                ),
            )

    def get_job(self, job_id: str) -> JobRecord | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM jobs WHERE job_id = ?",
                (job_id,),
            ).fetchone()
        if not row:
            return None
        return self._row_to_job(row)

    def delete_jobs_before(self, cutoff_iso: str) -> int:
        with self._lock:
            cur = self._conn.execute(
                "DELETE FROM jobs WHERE created_at < ?",
                (cutoff_iso,),
            )
            return cur.rowcount or 0

    def fail_stale_running(self, message: str = "服务重启，任务中断") -> int:
        """Mark RUNNING/PENDING interrupted jobs as FAILED after process restart."""
        now = to_iso(utc_now())
        prog = ProgressInfo(
            phase=JobPhase.FAILED, percent=0, message=message
        ).model_dump_json()
        err = JobError(code="INTERRUPTED", message=message).model_dump_json()
        with self._lock:
            cur = self._conn.execute(
                """
                UPDATE jobs
                SET status = ?, progress_json = ?, error_json = ?, updated_at = ?
                WHERE status IN ('PENDING', 'RUNNING')
                """,
                (JobStatus.FAILED.value, prog, err, now),
            )
            return cur.rowcount or 0

    def _row_to_job(self, row: sqlite3.Row) -> JobRecord:
        return JobRecord(
            job_id=row["job_id"],
            upload_id=row["upload_id"],
            status=JobStatus(row["status"]),
            params=ConvertParams.model_validate_json(row["params_json"]),
            progress=ProgressInfo.model_validate_json(row["progress_json"]),
            result=(
                JobResult.model_validate_json(row["result_json"])
                if row["result_json"]
                else None
            ),
            error=(
                JobError.model_validate_json(row["error_json"])
                if row["error_json"]
                else None
            ),
            created_at=from_iso(row["created_at"]),
            updated_at=from_iso(row["updated_at"]),
            source_name=row["source_name"],
            meta=json.loads(row["meta_json"] or "{}"),
        )
