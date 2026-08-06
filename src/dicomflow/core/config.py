from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Self

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _default_web_dir() -> Path:
    here = Path(__file__).resolve()
    candidate = here.parents[3] / "web"
    if candidate.is_dir():
        return candidate
    return here.parents[1] / "static"


def _read_env_file_value(name: str, path: Path = Path(".env")) -> str | None:
    """Read a single KEY=value from a dotenv file (no secret logging)."""
    if not path.is_file():
        return None
    try:
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            if key.strip() != name:
                continue
            val = val.strip().strip("'").strip('"')
            return val or None
    except OSError:
        return None
    return None


class Settings(BaseSettings):
    """Runtime settings. Defaults favour safe public exposure."""

    model_config = SettingsConfigDict(
        env_prefix="DICOMFLOW_",
        env_file=".env",
        extra="ignore",
    )

    data_dir: Path = Path("data")
    web_dir: Path = Field(default_factory=_default_web_dir)
    host: str = "127.0.0.1"
    port: int = 8765

    # Upload / extract limits
    max_upload_bytes: int = 1024 * 1024 * 1024  # 1 GiB default for public-ish safety
    max_extract_bytes: int = 4 * 1024 * 1024 * 1024  # 4 GiB
    max_extract_files: int = 100_000
    max_compression_ratio: float = 100.0
    allowed_upload_extensions: str = ".zip,.rar,.7z,.tar,.gz,.tgz"

    default_fps: int = 10
    # Auto-delete uploads/work/outputs (and in-memory job meta) after this many hours
    job_ttl_hours: int = 24
    # How often the background cleaner runs (seconds); min effective 60
    cleanup_interval_seconds: int = 900
    workers: int = 1

    # Security
    enable_docs: bool = False  # never expose Swagger unless explicitly enabled
    access_token: str | None = None  # if set, all /api/* (except health) require it
    rate_limit_rpm: int = 60  # requests per minute per IP
    rate_limit_uploads_per_hour: int = 20
    allowed_hosts: str = "*"  # comma-separated; use domain in production
    cors_origins: str = ""  # empty = no cross-origin; set explicit origins if needed
    # Only enable when a trusted reverse proxy sets X-Forwarded-For
    trust_x_forwarded_for: bool = False

    # Cloudflare Turnstile (optional human verification; independent of access_token)
    captcha_enabled: bool = False
    turnstile_site_key: str | None = None
    # Prefer unprefixed TURNSTILE_SECRET (Spin canonical); see resolve_turnstile_secret
    turnstile_secret_key: str | None = None

    # Offline desktop/mobile shell: no public bind, no password/captcha
    offline_app: bool = False

    @field_validator("access_token", "turnstile_site_key", "turnstile_secret_key", mode="before")
    @classmethod
    def empty_str_as_none(cls, v):  # noqa: ANN001
        if v is None:
            return None
        s = str(v).strip()
        return s or None

    @model_validator(mode="after")
    def resolve_secrets_and_offline_mode(self) -> Self:
        """
        Resolve Turnstile secret, then apply offline-app hard overrides.

        Secret resolution (never log the value):
        1. DICOMFLOW_TURNSTILE_SECRET_KEY (already on turnstile_secret_key)
        2. TURNSTILE_SECRET process env
        3. TURNSTILE_SECRET in .env file
        """
        if not self.turnstile_secret_key:
            secret = os.environ.get("TURNSTILE_SECRET")
            if not secret or not str(secret).strip():
                secret = _read_env_file_value("TURNSTILE_SECRET")
            if secret and str(secret).strip():
                self.turnstile_secret_key = str(secret).strip()

        # Offline desktop/mobile shell: local-only, no password/captcha
        if self.offline_app:
            self.host = "127.0.0.1"
            self.access_token = None
            self.captcha_enabled = False
            self.turnstile_site_key = None
            self.turnstile_secret_key = None
            self.enable_docs = False
            self.trust_x_forwarded_for = False
        return self

    @property
    def captcha_active(self) -> bool:
        """True only when captcha is switched on and both Turnstile keys are set."""
        return bool(
            self.captcha_enabled
            and self.turnstile_site_key
            and self.turnstile_secret_key
        )

    @property
    def uploads_dir(self) -> Path:
        return self.data_dir / "uploads"

    @property
    def work_dir(self) -> Path:
        return self.data_dir / "work"

    @property
    def outputs_dir(self) -> Path:
        return self.data_dir / "outputs"

    @property
    def allowed_extensions(self) -> set[str]:
        return {
            e.strip().lower() if e.strip().startswith(".") else f".{e.strip().lower()}"
            for e in self.allowed_upload_extensions.split(",")
            if e.strip()
        }

    @property
    def cors_origin_list(self) -> list[str]:
        if not self.cors_origins.strip():
            return []
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def allowed_host_list(self) -> list[str]:
        raw = self.allowed_hosts.strip()
        if not raw or raw == "*":
            return ["*"]
        return [h.strip() for h in raw.split(",") if h.strip()]

    def ensure_dirs(self) -> None:
        for path in (self.uploads_dir, self.work_dir, self.outputs_dir):
            path.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    return Settings()
