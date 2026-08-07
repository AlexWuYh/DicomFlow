from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.responses import Response

from dicomflow import __version__
from dicomflow.api.deps import get_job_service
from dicomflow.api.routes import jobs, system
from dicomflow.api.security import SecurityMiddleware
from dicomflow.core.config import get_settings
from dicomflow.tasks.cleanup import CleanupScheduler

logger = logging.getLogger(__name__)


class _SpaStaticFiles(StaticFiles):
    """StaticFiles with no-cache for HTML/JS/CSS so UI deploys are not sticky."""

    def file_response(self, full_path, stat_result, scope, status_code: int = 200) -> Response:  # noqa: ANN001
        response = super().file_response(full_path, stat_result, scope, status_code=status_code)
        ctype = (response.headers.get("content-type") or "").lower()
        lower = str(full_path).lower()
        if (
            lower.endswith((".html", ".js", ".css", ".mjs", ".map"))
            or "text/html" in ctype
            or "javascript" in ctype
            or "text/css" in ctype
        ):
            response.headers["Cache-Control"] = "no-cache, must-revalidate"
            response.headers["Pragma"] = "no-cache"
        return response


def create_app() -> FastAPI:
    settings = get_settings()
    settings.ensure_dirs()

    docs_url = "/docs" if settings.enable_docs else None
    redoc_url = "/redoc" if settings.enable_docs else None
    openapi_url = "/openapi.json" if settings.enable_docs else None

    scheduler_holder: dict[str, CleanupScheduler | None] = {"scheduler": None}

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        service = get_job_service()
        scheduler = CleanupScheduler(settings, service)
        scheduler.start()
        scheduler_holder["scheduler"] = scheduler
        logger.info(
            "File retention: %s hours (uploads/work/outputs auto-cleaned)",
            settings.job_ttl_hours,
        )
        try:
            yield
        finally:
            scheduler.stop()
            scheduler_holder["scheduler"] = None

    app = FastAPI(
        title="DicomFlow",
        version=__version__,
        description="Local-first DICOM → MP4/GIF converter",
        docs_url=docs_url,
        redoc_url=redoc_url,
        openapi_url=openapi_url,
        lifespan=lifespan,
    )

    hosts = settings.allowed_host_list
    if hosts != ["*"]:
        app.add_middleware(TrustedHostMiddleware, allowed_hosts=hosts)

    origins = settings.cors_origin_list
    if origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_credentials=False,
            allow_methods=["GET", "POST", "OPTIONS"],
            allow_headers=["*"],
            max_age=600,
        )

    app.add_middleware(SecurityMiddleware, settings=settings)

    app.include_router(system.router, tags=["system"])
    app.include_router(jobs.router, prefix="/api/v1", tags=["jobs"])

    web_dir = Path(settings.web_dir)
    if web_dir.is_dir():
        # no-cache on SPA assets so deploys (chunked upload JS etc.) take effect without
        # users being stuck on a stale app.js that still uses large PUT parts.
        app.mount(
            "/",
            _SpaStaticFiles(directory=str(web_dir), html=True),
            name="web",
        )
        logger.info("Serving web UI from %s", web_dir)
    else:
        logger.warning("Web UI directory not found: %s", web_dir)

    if settings.access_token:
        logger.info("Access token protection is ENABLED")
    else:
        logger.warning(
            "Access token is NOT set — API is open to anyone who can reach the host. "
            "Set DICOMFLOW_ACCESS_TOKEN before public deployment."
        )
    if settings.captcha_active:
        logger.info("Turnstile captcha is ENABLED (upload protected via siteverify)")
    elif settings.captcha_enabled and settings.turnstile_site_key:
        logger.error(
            "CAPTCHA_ENABLED=true and site key set, but TURNSTILE_SECRET is missing — "
            "widget may render; uploads will fail siteverify until secret is set"
        )
    elif settings.captcha_enabled:
        logger.error(
            "CAPTCHA_ENABLED=true but Turnstile site key / TURNSTILE_SECRET missing — "
            "uploads that require captcha will fail until keys are set"
        )
    else:
        logger.info("Turnstile captcha is DISABLED (DICOMFLOW_CAPTCHA_ENABLED=false)")
    if settings.chunked_upload_enabled:
        logger.info(
            "Chunked upload is ENABLED (part size %s MB) — SPA will use multi-part",
            settings.chunk_size_mb,
        )
    else:
        logger.info(
            "Chunked upload is DISABLED — enable DICOMFLOW_CHUNKED_UPLOAD_ENABLED=true "
            "behind Cloudflare Tunnel for large packages"
        )
    if settings.enable_docs:
        logger.warning("OpenAPI docs are ENABLED at /docs — disable for public deploy")

    return app
