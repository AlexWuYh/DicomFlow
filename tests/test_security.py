from fastapi.testclient import TestClient

from dicomflow.api.app import create_app
from dicomflow.api.deps import get_job_service
from dicomflow.core.config import get_settings


def test_docs_disabled_by_default(tmp_path, monkeypatch):
    monkeypatch.setenv("DICOMFLOW_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("DICOMFLOW_ENABLE_DOCS", "false")
    monkeypatch.delenv("DICOMFLOW_ACCESS_TOKEN", raising=False)
    get_settings.cache_clear()
    get_job_service.cache_clear()
    client = TestClient(create_app())
    assert client.get("/docs").status_code in (404, 405)
    assert client.get("/openapi.json").status_code in (404, 405)
    assert client.get("/health").status_code == 200
    get_settings.cache_clear()
    get_job_service.cache_clear()


def test_access_token_protects_api(tmp_path, monkeypatch):
    monkeypatch.setenv("DICOMFLOW_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("DICOMFLOW_ACCESS_TOKEN", "secret-token-xyz")
    monkeypatch.setenv("DICOMFLOW_ENABLE_DOCS", "false")
    get_settings.cache_clear()
    get_job_service.cache_clear()
    client = TestClient(create_app())

    # health / bootstrap open
    assert client.get("/health").status_code == 200
    b = client.get("/api/v1/bootstrap")
    assert b.status_code == 200
    assert b.json()["auth_required"] is True

    # jobs without token
    r = client.post("/api/v1/jobs", json={"upload_id": "abc", "format": "mp4"})
    assert r.status_code == 401
    assert r.json()["code"] == "AUTH_REQUIRED"

    # with token still 400/404 but not 401
    r2 = client.post(
        "/api/v1/jobs",
        json={"upload_id": "notarealid", "format": "mp4"},
        headers={"X-DicomFlow-Token": "secret-token-xyz"},
    )
    assert r2.status_code != 401

    get_settings.cache_clear()
    get_job_service.cache_clear()


def test_reject_bad_extension(tmp_path, monkeypatch):
    monkeypatch.setenv("DICOMFLOW_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.delenv("DICOMFLOW_ACCESS_TOKEN", raising=False)
    get_settings.cache_clear()
    get_job_service.cache_clear()
    client = TestClient(create_app())
    r = client.post(
        "/api/v1/uploads",
        files={"file": ("evil.exe", b"MZ...", "application/octet-stream")},
    )
    assert r.status_code == 400
    get_settings.cache_clear()
    get_job_service.cache_clear()
