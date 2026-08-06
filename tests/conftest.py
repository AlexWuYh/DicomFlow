"""Isolate tests from developer .env (password / Turnstile keys)."""

from __future__ import annotations

import pytest

from dicomflow.api.captcha import set_verify_transport
from dicomflow.api.deps import get_job_service
from dicomflow.core.config import get_settings


@pytest.fixture(autouse=True)
def _isolate_runtime_env(monkeypatch, tmp_path):
    """
    Project `.env` is for local preview and must not leak into pytest.
    Empty strings override dotenv values and become None via Settings validators.
    """
    monkeypatch.setenv("DICOMFLOW_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("DICOMFLOW_ACCESS_TOKEN", "")
    monkeypatch.setenv("DICOMFLOW_CAPTCHA_ENABLED", "false")
    monkeypatch.setenv("DICOMFLOW_TURNSTILE_SITE_KEY", "")
    monkeypatch.setenv("DICOMFLOW_TURNSTILE_SECRET_KEY", "")
    monkeypatch.setenv("TURNSTILE_SECRET", "")
    monkeypatch.setenv("DICOMFLOW_ENABLE_DOCS", "false")
    # Prevent offline-app tests from leaking into auth/captcha suites
    monkeypatch.setenv("DICOMFLOW_OFFLINE_APP", "false")
    monkeypatch.setenv("DICOMFLOW_HOST", "127.0.0.1")
    set_verify_transport(None)
    get_settings.cache_clear()
    get_job_service.cache_clear()
    yield
    set_verify_transport(None)
    get_settings.cache_clear()
    get_job_service.cache_clear()
