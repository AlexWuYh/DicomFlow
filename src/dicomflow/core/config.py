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
    # Chunked upload (Cloudflare Tunnel / reverse-proxy body limits ~100 MiB)
    # Off by default; enable for public CF Zero Trust so large packages can pass.
    chunked_upload_enabled: bool = False
    # Per-part size in megabytes. Default 4: stays under CF Free ~100s proxy timeout on
    # typical home/office uplinks; raise (e.g. 8–16) only on fast LAN or Enterprise CF.
    chunk_size_mb: int = 4
    # Soft cap on number of parts (also bounded by max_upload_bytes / chunk_size)
    max_upload_chunks: int = 512

    default_fps: int = 10
    # Auto-delete uploads/work/outputs (and in-memory job meta) after this many hours
    job_ttl_hours: int = 24
    # How often the background cleaner runs (seconds); min effective 60
    cleanup_interval_seconds: int = 900
    workers: int = 1

    # Security
    enable_docs: bool = False  # never expose Swagger unless explicitly enabled
    access_token: str | None = None  # if set, all /api/* (except health) require it
    rate_limit_rpm: int = 120  # general API requests per minute per IP
    rate_limit_uploads_per_hour: int = 20
    # Chunk part PUTs use a higher RPM so multi-hundred-MB files are not blocked mid-stream
    rate_limit_chunk_rpm: int = 300
    # Job status polling (GET /jobs/{id}) — SPA polls every ~2s during convert
    rate_limit_job_poll_rpm: int = 180
    allowed_hosts: str = "*"  # comma-separated; use domain in production
    cors_origins: str = ""  # empty = no cross-origin; set explicit origins if needed
    # Only enable when a trusted reverse proxy sets X-Forwarded-For
    trust_x_forwarded_for: bool = False

    # Cloudflare Turnstile (optional human verification; independent of access_token)
    captcha_enabled: bool = False
    turnstile_site_key: str | None = None
    # Prefer unprefixed TURNSTILE_SECRET (Spin canonical); see resolve_turnstile_secret
    turnstile_secret_key: str | None = None

    @field_validator("access_token", "turnstile_site_key", "turnstile_secret_key", mode="before")
    @classmethod
    def empty_str_as_none(cls, v):  # noqa: ANN001
        if v is None:
            return None
        s = str(v).strip()
        return s or None

    @model_validator(mode="after")
    def resolve_turnstile_secret(self) -> Self:
        """
        Secret resolution order (never log the value):
        1. DICOMFLOW_TURNSTILE_SECRET_KEY (already on turnstile_secret_key)
        2. TURNSTILE_SECRET process env (canonical Spin / Cloudflare name)
        3. TURNSTILE_SECRET in .env file
        """
        if self.turnstile_secret_key:
            return self
        secret = os.environ.get("TURNSTILE_SECRET")
        if not secret or not str(secret).strip():
            secret = _read_env_file_value("TURNSTILE_SECRET")
        if secret and str(secret).strip():
            self.turnstile_secret_key = str(secret).strip()
        return self

    @field_validator("chunk_size_mb", mode="before")
    @classmethod
    def coerce_chunk_size_mb(cls, v):  # noqa: ANN001
        """Accept int/float/str; clamp to a practical range (1–90 MB)."""
        if v is None or v == "":
            return 4
        try:
            n = int(float(v))
        except (TypeError, ValueError):
            return 4
        # 1 MB min; 90 MB max stays under typical Cloudflare Free ~100 MB body limit
        return max(1, min(n, 90))

    @property
    def captcha_active(self) -> bool:
        """True only when captcha is switched on and both Turnstile keys are set."""
        return bool(
            self.captcha_enabled
            and self.turnstile_site_key
            and self.turnstile_secret_key
        )

    @property
    def chunk_size_bytes(self) -> int:
        """Resolved part size in bytes (from chunk_size_mb)."""
        return int(self.chunk_size_mb) * 1024 * 1024

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
