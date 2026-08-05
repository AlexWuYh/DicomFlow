from datetime import timedelta
from pathlib import Path

from dicomflow.core.models import ConvertParams, JobPhase, JobRecord, JobStatus, ProgressInfo, UploadRecord
from dicomflow.core.timeutil import utc_now
from dicomflow.tasks.store import JobStore


def test_sqlite_persist_upload_and_job(tmp_path: Path):
    store = JobStore(tmp_path / "t.db")
    now = utc_now()
    up = UploadRecord(
        upload_id="u1",
        filename="a.zip",
        size_bytes=10,
        path=str(tmp_path / "a.zip"),
        created_at=now,
    )
    store.save_upload(up)
    assert store.get_upload("u1") is not None
    assert store.get_upload("u1").filename == "a.zip"

    job = JobRecord(
        job_id="j1",
        upload_id="u1",
        status=JobStatus.PENDING,
        params=ConvertParams(),
        progress=ProgressInfo(phase=JobPhase.PENDING, percent=0, message="q"),
        created_at=now,
        updated_at=now,
    )
    store.save_job(job)
    loaded = store.get_job("j1")
    assert loaded is not None
    assert loaded.status == JobStatus.PENDING
    assert loaded.params.format.value == "mp4"

    # update
    loaded.status = JobStatus.RUNNING
    loaded.progress = ProgressInfo(phase=JobPhase.CONVERTING, percent=50, message="go")
    loaded.updated_at = utc_now()
    store.save_job(loaded)
    again = store.get_job("j1")
    assert again.status == JobStatus.RUNNING
    assert again.progress.percent == 50

    # fail stale
    n = store.fail_stale_running()
    assert n == 1
    assert store.get_job("j1").status == JobStatus.FAILED

    # purge
    old = utc_now() - timedelta(hours=48)
    store.save_upload(
        UploadRecord(
            upload_id="old",
            filename="o.zip",
            size_bytes=1,
            path="/x",
            created_at=old,
        )
    )
    cutoff = (utc_now() - timedelta(hours=24)).isoformat()
    # to_iso used in store; ensure comparable
    from dicomflow.core.timeutil import to_iso

    assert store.delete_uploads_before(to_iso(utc_now() - timedelta(hours=24))) >= 1
    assert store.get_upload("old") is None
    store.close()
