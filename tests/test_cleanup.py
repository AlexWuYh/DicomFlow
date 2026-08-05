import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dicomflow.core.config import Settings
from dicomflow.core.timeutil import utc_now
from dicomflow.storage.local import LocalFilesystemStorage
from dicomflow.tasks.cleanup import cleanup_expired_dirs, run_cleanup
from dicomflow.tasks.inprocess import InProcessQueue
from dicomflow.tasks.job_service import JobService
from dicomflow.tasks.store import JobStore
from dicomflow.core.models import ConvertParams, JobRecord, JobStatus, UploadRecord


def test_cleanup_expired_dirs(tmp_path: Path):
    root = tmp_path / "uploads"
    root.mkdir()
    old = root / "oldid"
    new = root / "newid"
    old.mkdir()
    new.mkdir()
    (old / "f.bin").write_bytes(b"x")
    (new / "f.bin").write_bytes(b"y")

    # Make old dir appear aged
    old_ts = time.time() - 48 * 3600
    for p in [old, old / "f.bin"]:
        import os

        os.utime(p, (old_ts, old_ts))

    removed, errors = cleanup_expired_dirs(root, max_age=timedelta(hours=24))
    assert errors == 0
    assert removed == 1
    assert not old.exists()
    assert new.exists()


def test_run_cleanup_purges_memory_and_disk(tmp_path: Path):
    settings = Settings(
        data_dir=tmp_path / "data",
        job_ttl_hours=24,
        cleanup_interval_seconds=60,
    )
    settings.ensure_dirs()
    storage = LocalFilesystemStorage(settings)
    store = JobStore(settings.data_dir / "dicomflow.db")
    service = JobService(
        storage=storage, queue=InProcessQueue(1), settings=settings, store=store
    )

    # Disk: old upload dir
    old_upload = settings.uploads_dir / "oldupload"
    old_upload.mkdir()
    (old_upload / "a.zip").write_bytes(b"zip")
    old_ts = time.time() - 30 * 3600
    import os

    for p in [old_upload, old_upload / "a.zip"]:
        os.utime(p, (old_ts, old_ts))

    # SQLite: old + fresh records
    old_dt = datetime.now(timezone.utc) - timedelta(hours=30)
    store.save_upload(
        UploadRecord(
            upload_id="oldupload",
            filename="a.zip",
            size_bytes=3,
            path=str(old_upload / "a.zip"),
            created_at=old_dt,
        )
    )
    store.save_job(
        JobRecord(
            job_id="oldjob",
            upload_id="oldupload",
            status=JobStatus.SUCCEEDED,
            params=ConvertParams(),
            created_at=old_dt,
            updated_at=old_dt,
        )
    )
    store.save_upload(
        UploadRecord(
            upload_id="fresh",
            filename="b.zip",
            size_bytes=1,
            path="/tmp/x",
            created_at=utc_now(),
        )
    )

    stats = run_cleanup(settings, service)
    assert stats.removed_dirs >= 1
    assert not old_upload.exists()
    assert store.get_upload("oldupload") is None
    assert store.get_job("oldjob") is None
    assert store.get_upload("fresh") is not None
