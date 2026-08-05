from fastapi.testclient import TestClient

from dicomflow.api.app import create_app
from dicomflow.api.captcha import set_verify_transport
from dicomflow.api.deps import get_job_service
from dicomflow.core.config import get_settings


def _clear_caches():
    get_settings.cache_clear()
    get_job_service.cache_clear()


def test_docs_disabled_by_default(tmp_path, monkeypatch):
    monkeypatch.setenv("DICOMFLOW_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("DICOMFLOW_ENABLE_DOCS", "false")
    # Empty strings override project .env (do not delenv)
    monkeypatch.setenv("DICOMFLOW_ACCESS_TOKEN", "")
    monkeypatch.setenv("DICOMFLOW_CAPTCHA_ENABLED", "false")
    _clear_caches()
    client = TestClient(create_app())
    assert client.get("/docs").status_code in (404, 405)
    assert client.get("/openapi.json").status_code in (404, 405)
    assert client.get("/health").status_code == 200
    _clear_caches()


def test_access_token_protects_api(tmp_path, monkeypatch):
    monkeypatch.setenv("DICOMFLOW_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("DICOMFLOW_ACCESS_TOKEN", "secret-token-xyz")
    monkeypatch.setenv("DICOMFLOW_ENABLE_DOCS", "false")
    monkeypatch.setenv("DICOMFLOW_CAPTCHA_ENABLED", "false")
    _clear_caches()
    client = TestClient(create_app())

    # health / bootstrap open
    assert client.get("/health").status_code == 200
    b = client.get("/api/v1/bootstrap")
    assert b.status_code == 200
    assert b.json()["auth_required"] is True
    assert b.json()["captcha_enabled"] is False

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

    _clear_caches()


def test_reject_bad_extension(tmp_path, monkeypatch):
    monkeypatch.setenv("DICOMFLOW_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("DICOMFLOW_ACCESS_TOKEN", "")
    monkeypatch.setenv("DICOMFLOW_CAPTCHA_ENABLED", "false")
    _clear_caches()
    client = TestClient(create_app())
    r = client.post(
        "/api/v1/uploads",
        files={"file": ("evil.exe", b"MZ...", "application/octet-stream")},
    )
    assert r.status_code == 400
    _clear_caches()


def test_captcha_off_by_default(tmp_path, monkeypatch):
    monkeypatch.setenv("DICOMFLOW_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("DICOMFLOW_ACCESS_TOKEN", "")
    monkeypatch.setenv("DICOMFLOW_CAPTCHA_ENABLED", "false")
    monkeypatch.setenv("DICOMFLOW_TURNSTILE_SITE_KEY", "")
    monkeypatch.setenv("TURNSTILE_SECRET", "")
    _clear_caches()
    client = TestClient(create_app())
    b = client.get("/api/v1/bootstrap").json()
    assert b["captcha_enabled"] is False
    assert b["captcha_site_key"] is None
    # upload without captcha token succeeds (extension ok)
    r = client.post(
        "/api/v1/uploads",
        files={"file": ("study.zip", b"PK\x03\x04fake", "application/zip")},
    )
    assert r.status_code == 201
    _clear_caches()


def test_captcha_enabled_requires_token(tmp_path, monkeypatch):
    monkeypatch.setenv("DICOMFLOW_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("DICOMFLOW_ACCESS_TOKEN", "")
    monkeypatch.setenv("DICOMFLOW_CAPTCHA_ENABLED", "true")
    monkeypatch.setenv("DICOMFLOW_TURNSTILE_SITE_KEY", "site-public")
    monkeypatch.setenv("DICOMFLOW_TURNSTILE_SECRET_KEY", "")
    monkeypatch.setenv("TURNSTILE_SECRET", "secret-private")
    _clear_caches()
    client = TestClient(create_app())

    b = client.get("/api/v1/bootstrap").json()
    assert b["captcha_enabled"] is True
    assert b["captcha_site_key"] == "site-public"

    r = client.post(
        "/api/v1/uploads",
        files={"file": ("study.zip", b"PK\x03\x04fake", "application/zip")},
    )
    assert r.status_code == 400
    assert r.json()["code"] == "CAPTCHA_REQUIRED"
    _clear_caches()


def test_captcha_enabled_verifies_token(tmp_path, monkeypatch):
    monkeypatch.setenv("DICOMFLOW_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("DICOMFLOW_ACCESS_TOKEN", "")
    monkeypatch.setenv("DICOMFLOW_CAPTCHA_ENABLED", "true")
    monkeypatch.setenv("DICOMFLOW_TURNSTILE_SITE_KEY", "site-public")
    monkeypatch.setenv("DICOMFLOW_TURNSTILE_SECRET_KEY", "")
    monkeypatch.setenv("TURNSTILE_SECRET", "secret-private")
    _clear_caches()

    calls: list[dict] = []

    def fake_transport(url: str, fields: dict[str, str]) -> dict:
        calls.append(fields)
        assert fields.get("secret") == "secret-private"
        assert "response" in fields
        if fields.get("response") == "good-token":
            return {"success": True}
        return {"success": False, "error-codes": ["invalid-input-response"]}

    set_verify_transport(fake_transport)
    try:
        client = TestClient(create_app())

        bad = client.post(
            "/api/v1/uploads",
            files={"file": ("study.zip", b"PK\x03\x04fake", "application/zip")},
            data={"cf-turnstile-response": "bad-token"},
        )
        assert bad.status_code == 400
        assert bad.json()["code"] == "CAPTCHA_FAILED"

        ok = client.post(
            "/api/v1/uploads",
            files={"file": ("study.zip", b"PK\x03\x04fake", "application/zip")},
            data={"cf-turnstile-response": "good-token"},
        )
        assert ok.status_code == 201
        assert "upload_id" in ok.json()
        assert any(c.get("response") == "good-token" for c in calls)
        # remoteip included when available from client
        assert any("remoteip" in c for c in calls)
    finally:
        set_verify_transport(None)
        _clear_caches()


def test_captcha_enabled_without_keys_rejects(tmp_path, monkeypatch):
    monkeypatch.setenv("DICOMFLOW_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("DICOMFLOW_ACCESS_TOKEN", "")
    monkeypatch.setenv("DICOMFLOW_CAPTCHA_ENABLED", "true")
    monkeypatch.setenv("DICOMFLOW_TURNSTILE_SITE_KEY", "")
    monkeypatch.setenv("DICOMFLOW_TURNSTILE_SECRET_KEY", "")
    monkeypatch.setenv("TURNSTILE_SECRET", "")
    _clear_caches()
    client = TestClient(create_app())
    # Not fully configured → bootstrap reports off
    b = client.get("/api/v1/bootstrap").json()
    assert b["captcha_enabled"] is False
    # Server still enforces when CAPTCHA_ENABLED without keys (fail closed)
    r = client.post(
        "/api/v1/uploads",
        files={"file": ("study.zip", b"PK\x03\x04fake", "application/zip")},
        data={"cf-turnstile-response": "anything"},
    )
    assert r.status_code == 503
    assert r.json()["code"] == "CAPTCHA_MISCONFIGURED"
    _clear_caches()
