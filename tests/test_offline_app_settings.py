"""Offline app mode forces local-only, no auth/captcha."""

from dicomflow.core.config import get_settings


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
