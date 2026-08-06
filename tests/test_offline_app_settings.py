"""Offline app mode forces local-only, no auth/captcha."""

from pathlib import Path

from fastapi.testclient import TestClient

from dicomflow.api.app import create_app
from dicomflow.api.deps import get_job_service
from dicomflow.core.config import _default_web_dir, get_settings
from dicomflow.desktop.app import _prepare_offline_env


def test_offline_app_disables_public_security(tmp_path, monkeypatch):
    monkeypatch.setenv("DICOMFLOW_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("DICOMFLOW_OFFLINE_APP", "true")
    monkeypatch.setenv("DICOMFLOW_ACCESS_TOKEN", "should-be-ignored")
    monkeypatch.setenv("DICOMFLOW_CAPTCHA_ENABLED", "true")
    monkeypatch.setenv("DICOMFLOW_TURNSTILE_SITE_KEY", "site")
    monkeypatch.setenv("TURNSTILE_SECRET", "secret")
    monkeypatch.setenv("DICOMFLOW_HOST", "0.0.0.0")
    get_settings.cache_clear()
    s = get_settings()
    assert s.offline_app is True
    assert s.host == "127.0.0.1"
    assert s.access_token is None
    assert s.captcha_enabled is False
    assert s.captcha_active is False
    assert s.enable_docs is False
    get_settings.cache_clear()


def test_offline_app_off_by_default(tmp_path, monkeypatch):
    monkeypatch.setenv("DICOMFLOW_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("DICOMFLOW_OFFLINE_APP", "false")
    monkeypatch.setenv("DICOMFLOW_ACCESS_TOKEN", "")
    monkeypatch.setenv("DICOMFLOW_CAPTCHA_ENABLED", "false")
    get_settings.cache_clear()
    s = get_settings()
    assert s.offline_app is False
    get_settings.cache_clear()


def test_prepare_offline_env_sets_data_and_port(tmp_path, monkeypatch):
    monkeypatch.delenv("DICOMFLOW_OFFLINE_APP", raising=False)
    data = tmp_path / "appdata"
    app_data, port = _prepare_offline_env(port=18765, data_dir=data)
    assert app_data == data.resolve()
    assert port == 18765
    assert Path(app_data).is_dir()
    assert monkeypatch is not None
    import os

    assert os.environ["DICOMFLOW_OFFLINE_APP"] == "true"
    assert os.environ["DICOMFLOW_HOST"] == "127.0.0.1"
    assert os.environ["DICOMFLOW_PORT"] == "18765"
    assert os.environ["DICOMFLOW_CAPTCHA_ENABLED"] == "false"


def test_bootstrap_reports_offline_app(tmp_path, monkeypatch):
    monkeypatch.setenv("DICOMFLOW_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("DICOMFLOW_OFFLINE_APP", "true")
    monkeypatch.setenv("DICOMFLOW_ACCESS_TOKEN", "x")
    monkeypatch.setenv("DICOMFLOW_CAPTCHA_ENABLED", "true")
    get_settings.cache_clear()
    get_job_service.cache_clear()
    client = TestClient(create_app())
    b = client.get("/api/v1/bootstrap").json()
    assert b["offline_app"] is True
    assert b["auth_required"] is False
    assert b["captcha_enabled"] is False
    get_settings.cache_clear()
    get_job_service.cache_clear()


def test_default_web_dir_exists_in_dev_tree():
    web = _default_web_dir()
    assert web.is_dir(), f"expected web dir, got {web}"
