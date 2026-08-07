from fastapi import APIRouter, Depends

from dicomflow import __version__
from dicomflow.api.deps import get_app_settings
from dicomflow.core.config import Settings

router = APIRouter()


@router.get("/health")
@router.get("/api/v1/health")
def health():
    """Liveness probe — no secrets, no auth."""
    return {"status": "ok", "version": __version__}


@router.get("/api/v1/bootstrap")
def bootstrap(settings: Settings = Depends(get_app_settings)):
    """Minimal public config for the SPA (no secrets)."""
    # Widget can render with site key alone; server still needs TURNSTILE_SECRET to verify
    captcha_on = bool(settings.captcha_enabled and settings.turnstile_site_key)
    return {
        "version": __version__,
        "auth_required": bool(settings.access_token),
        "captcha_enabled": captcha_on,
        # Site key is public by design; secret never leaves the server
        "captcha_site_key": settings.turnstile_site_key if captcha_on else None,
        "max_upload_bytes": settings.max_upload_bytes,
        "job_ttl_hours": settings.job_ttl_hours,
        # Chunked upload (for reverse proxies / Cloudflare body limits)
        "chunked_upload_enabled": bool(settings.chunked_upload_enabled),
        "chunk_size_mb": int(settings.chunk_size_mb),
        # Bytes kept for SPA math / progress (derived from chunk_size_mb)
        "chunk_size_bytes": int(settings.chunk_size_bytes),
        # Progress: SPA prefers SSE (GET /jobs/{id}/events); poll is fallback
        "progress_sse": True,
    }


@router.get("/api/v1/auth/check")
def auth_check(settings: Settings = Depends(get_app_settings)):
    """
    Verify access token for the SPA gate.

    Protected by SecurityMiddleware when ACCESS_TOKEN is set (not in public paths).
    Returns 200 only after middleware accepts the token.
    """
    return {
        "ok": True,
        "auth_required": bool(settings.access_token),
    }
