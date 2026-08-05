from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _default_web_dir() -> Path:
    here = Path(__file__).resolve()
    candidate = here.parents[3] / "web"
    if candidate.is_dir():
        return candidate
    return here.parents[1] / "static"


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
    trust_x_forwarded_for: bool = True  # behind reverse proxy

    @field_validator("access_token", mode="before")
    @classmethod
    def empty_token_as_none(cls, v):  # noqa: ANN001
        if v is None:
            return None
        s = str(v).strip()
        return s or None

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
