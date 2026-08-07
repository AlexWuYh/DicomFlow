from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
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

# Tell browsers AND Cloudflare edge not to sticky-cache SPA assets.
# Plain Cache-Control:no-cache is often still edge-cached by CF for hours.
_SPA_NO_STORE = {
    "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
    "CDN-Cache-Control": "no-store",
    "Cloudflare-CDN-Cache-Control": "no-store",
    "Pragma": "no-cache",
    "Expires": "0",
}


class _SpaStaticFiles(StaticFiles):
    """StaticFiles with no-store so Cloudflare edge cannot pin stale app.js."""

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
            for k, v in _SPA_NO_STORE.items():
                response.headers[k] = v
        return response


def _versioned_index_html(web_dir: Path) -> str:
    """
    Rewrite asset URLs with ?v={version} so CF/browser cache keys change every release.
    Without this, edge may keep serving an old app.js that still uses PUT + 16MB parts.
    """
    path = web_dir / "index.html"
    text = path.read_text(encoding="utf-8")
    ver = __version__
    text = text.replace('href="/styles.css"', f'href="/styles.css?v={ver}"')
    text = text.replace('src="/app.js"', f'src="/app.js?v={ver}"')
    return text


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
        # Version-busted index BEFORE static mount — changes CF cache key every release.
        @app.get("/", include_in_schema=False)
        @app.get("/index.html", include_in_schema=False)
        def spa_index() -> HTMLResponse:
            return HTMLResponse(
                content=_versioned_index_html(web_dir),
                headers=dict(_SPA_NO_STORE),
            )

        # Remaining static assets (app.js, css, icons). html=False: / handled above.
        app.mount(
            "/",
            _SpaStaticFiles(directory=str(web_dir), html=False),
            name="web",
        )
        logger.info("Serving web UI from %s (asset bust v=%s)", web_dir, __version__)
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
