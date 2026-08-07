"""Chunked upload API + assembly."""

from __future__ import annotations

from fastapi.testclient import TestClient

from dicomflow.api.app import create_app
from dicomflow.api.deps import get_job_service
from dicomflow.core.config import get_settings


def _clear():
    get_settings.cache_clear()
    get_job_service.cache_clear()


def test_chunked_disabled_returns_403(tmp_path, monkeypatch):
    monkeypatch.setenv("DICOMFLOW_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("DICOMFLOW_CHUNKED_UPLOAD_ENABLED", "false")
    _clear()
    client = TestClient(create_app())
    r = client.post(
        "/api/v1/uploads/init",
        json={"filename": "a.zip", "size_bytes": 100},
    )
    assert r.status_code == 403
    assert r.json()["code"] == "CHUNK_UPLOAD_DISABLED"
    b = client.get("/api/v1/bootstrap")
    assert b.json()["chunked_upload_enabled"] is False
    _clear()


def test_chunked_happy_path(tmp_path, monkeypatch):
    monkeypatch.setenv("DICOMFLOW_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("DICOMFLOW_CHUNKED_UPLOAD_ENABLED", "true")
    monkeypatch.setenv("DICOMFLOW_CHUNK_SIZE_MB", "1")
    monkeypatch.setenv("DICOMFLOW_ACCESS_TOKEN", "")
    monkeypatch.setenv("DICOMFLOW_CAPTCHA_ENABLED", "false")
    _clear()
    client = TestClient(create_app())

    chunk = 1024 * 1024  # 1 MB
    boot = client.get("/api/v1/bootstrap")
    assert boot.status_code == 200
    assert boot.json()["chunked_upload_enabled"] is True
    assert boot.json()["chunk_size_mb"] == 1
    assert boot.json()["chunk_size_bytes"] == chunk

    payload = b"A" * chunk + b"B" * chunk  # 2 full chunks
    init = client.post(
        "/api/v1/uploads/init",
        json={"filename": "study.zip", "size_bytes": len(payload)},
    )
    assert init.status_code == 201, init.text
    session = init.json()
    assert session["total_chunks"] == 2
    assert session["chunk_size_bytes"] == chunk
    upload_id = session["upload_id"]

    for i in range(2):
        part = payload[i * chunk : (i + 1) * chunk]
        r = client.put(
            f"/api/v1/uploads/{upload_id}/chunks/{i}",
            content=part,
            headers={"Content-Type": "application/octet-stream"},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["received_chunks"] == i + 1
        assert body["total_chunks"] == 2

    done = client.post(f"/api/v1/uploads/{upload_id}/complete")
    assert done.status_code == 201, done.text
    out = done.json()
    assert out["upload_id"] == upload_id
    assert out["filename"] == "study.zip"
    assert out["size_bytes"] == len(payload)

    # Idempotent complete
    done2 = client.post(f"/api/v1/uploads/{upload_id}/complete")
    assert done2.status_code == 201
    assert done2.json()["upload_id"] == upload_id

    # Assembled file on disk
    data_dir = tmp_path / "data" / "uploads" / upload_id / "study.zip"
    assert data_dir.is_file()
    assert data_dir.read_bytes() == payload
    _clear()


def test_chunked_missing_part_rejected(tmp_path, monkeypatch):
    monkeypatch.setenv("DICOMFLOW_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("DICOMFLOW_CHUNKED_UPLOAD_ENABLED", "true")
    monkeypatch.setenv("DICOMFLOW_CHUNK_SIZE_MB", "1")
    _clear()
    client = TestClient(create_app())
    chunk = 1024 * 1024
    payload = b"0" * (chunk * 2)  # 2 chunks
    init = client.post(
        "/api/v1/uploads/init",
        json={"filename": "x.rar", "size_bytes": len(payload)},
    )
    upload_id = init.json()["upload_id"]
    client.put(
        f"/api/v1/uploads/{upload_id}/chunks/0",
        content=payload[:chunk],
        headers={"Content-Type": "application/octet-stream"},
    )
    # skip chunk 1
    done = client.post(f"/api/v1/uploads/{upload_id}/complete")
    assert done.status_code == 400
    assert "分片" in done.json()["detail"]
    _clear()


def test_chunked_rejects_oversize(tmp_path, monkeypatch):
    monkeypatch.setenv("DICOMFLOW_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("DICOMFLOW_CHUNKED_UPLOAD_ENABLED", "true")
    monkeypatch.setenv("DICOMFLOW_MAX_UPLOAD_BYTES", "100")
    _clear()
    client = TestClient(create_app())
    r = client.post(
        "/api/v1/uploads/init",
        json={"filename": "big.zip", "size_bytes": 101},
    )
    assert r.status_code == 413
    _clear()


def test_chunked_wrong_extension(tmp_path, monkeypatch):
    monkeypatch.setenv("DICOMFLOW_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("DICOMFLOW_CHUNKED_UPLOAD_ENABLED", "true")
    _clear()
    client = TestClient(create_app())
    r = client.post(
        "/api/v1/uploads/init",
        json={"filename": "evil.exe", "size_bytes": 10},
    )
    assert r.status_code == 400
    _clear()


def test_single_shot_still_works_when_chunked_on(tmp_path, monkeypatch):
    monkeypatch.setenv("DICOMFLOW_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("DICOMFLOW_CHUNKED_UPLOAD_ENABLED", "true")
    _clear()
    client = TestClient(create_app())
    r = client.post(
        "/api/v1/uploads",
        files={"file": ("s.zip", b"PK\x03\x04tiny", "application/zip")},
    )
    assert r.status_code == 201
    assert "upload_id" in r.json()
    _clear()
