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
    return {
        "version": __version__,
        "auth_required": bool(settings.access_token),
        "max_upload_bytes": settings.max_upload_bytes,
        "job_ttl_hours": settings.job_ttl_hours,
    }
