"""SSE job progress stream."""

from __future__ import annotations

import json
import threading
import time

from fastapi.testclient import TestClient

from dicomflow.api.app import create_app
from dicomflow.api.deps import get_job_service
from dicomflow.core.config import get_settings
from dicomflow.core.models import (
    JobPhase,
    JobRecord,
    JobStatus,
    ProgressInfo,
)
from dicomflow.core.timeutil import utc_now
from dicomflow.tasks.progress_hub import progress_hub


def _clear():
    get_settings.cache_clear()
    get_job_service.cache_clear()


def test_job_events_streams_terminal_immediately(tmp_path, monkeypatch):
    monkeypatch.setenv("DICOMFLOW_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("DICOMFLOW_ACCESS_TOKEN", "")
    _clear()
    client = TestClient(create_app())
    service = get_job_service()

    job_id = "a" * 32
    rec = JobRecord(
        job_id=job_id,
        status=JobStatus.SUCCEEDED,
        progress=ProgressInfo(phase=JobPhase.SUCCEEDED, percent=100, message="完成"),
        created_at=utc_now(),
        updated_at=utc_now(),
    )
    service.store.save_job(rec)

    with client.stream("GET", f"/api/v1/jobs/{job_id}/events") as resp:
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers.get("content-type", "")
        body = b"".join(resp.iter_bytes()).decode("utf-8", errors="replace")
    assert "event: status" in body
    assert "event: done" in body
    assert "SUCCEEDED" in body
    _clear()


def test_job_events_receives_publish(tmp_path, monkeypatch):
    monkeypatch.setenv("DICOMFLOW_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("DICOMFLOW_ACCESS_TOKEN", "")
    _clear()
    client = TestClient(create_app())
    service = get_job_service()

    job_id = "b" * 32
    rec = JobRecord(
        job_id=job_id,
        status=JobStatus.RUNNING,
        progress=ProgressInfo(phase=JobPhase.CONVERTING, percent=5, message="转换中"),
        created_at=utc_now(),
        updated_at=utc_now(),
    )
    service.store.save_job(rec)

    def push_later():
        time.sleep(0.3)
        progress_hub.publish(
            job_id,
            {
                "job_id": job_id,
                "status": "SUCCEEDED",
                "progress": {"phase": "SUCCEEDED", "percent": 100, "message": "完成"},
                "result": None,
                "error": None,
            },
        )

    threading.Thread(target=push_later, daemon=True).start()

    with client.stream("GET", f"/api/v1/jobs/{job_id}/events") as resp:
        assert resp.status_code == 200
        chunks = []
        for chunk in resp.iter_bytes():
            chunks.append(chunk)
            text = b"".join(chunks).decode("utf-8", errors="replace")
            if "event: done" in text or "SUCCEEDED" in text and text.count("event:") >= 2:
                break
        body = b"".join(chunks).decode("utf-8", errors="replace")

    assert "event: status" in body
    # At least one status with percent 5 and later 100 / done
    assert "完成" in body or "SUCCEEDED" in body
    _clear()


def test_bootstrap_progress_sse_flag(tmp_path, monkeypatch):
    monkeypatch.setenv("DICOMFLOW_DATA_DIR", str(tmp_path / "data"))
    _clear()
    client = TestClient(create_app())
    b = client.get("/api/v1/bootstrap")
    assert b.status_code == 200
    assert b.json().get("progress_sse") is True
    _clear()
