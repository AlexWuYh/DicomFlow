from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse

from dicomflow.api.captcha import CaptchaError, verify_turnstile
from dicomflow.api.deps import get_app_settings, get_job_service
from dicomflow.api.security import client_ip
from dicomflow.api.upload_validate import validate_upload_filename
from dicomflow.core.config import Settings
from dicomflow.core.exceptions import UploadTooLargeError
from dicomflow.core.models import (
    ConvertParams,
    JobCreateResponse,
    JobStartRequest,
    JobStatusResponse,
    UploadResponse,
)
from dicomflow.tasks.job_service import JobService

router = APIRouter()


def _captcha_http_error(exc: CaptchaError) -> JSONResponse:
    status = 400
    if exc.code == "CAPTCHA_MISCONFIGURED":
        status = 503
    elif exc.code == "CAPTCHA_UNAVAILABLE":
        status = 503
    return JSONResponse(
        status_code=status,
        content={"detail": exc.message, "code": exc.code},
    )


@router.post("/uploads", response_model=UploadResponse, status_code=201)
async def create_upload(
    request: Request,
    file: UploadFile = File(...),
    # Cloudflare Turnstile widget posts as cf-turnstile-response; also accept alias
    cf_turnstile_response: str | None = Form(None, alias="cf-turnstile-response"),
    turnstile_token: str | None = Form(None),
    service: JobService = Depends(get_job_service),
    settings: Settings = Depends(get_app_settings),
):
    """Upload archive only. Conversion starts later via POST /jobs."""
    token = (cf_turnstile_response or turnstile_token or "").strip() or None
    # Header fallback (handy for non-form clients / tests)
    if not token:
        token = request.headers.get("cf-turnstile-response") or request.headers.get(
            "x-turnstile-token"
        )
    try:
        verify_turnstile(
            token,
            settings=settings,
            remoteip=client_ip(
                request, trust_x_forwarded_for=settings.trust_x_forwarded_for
            ),
        )
    except CaptchaError as exc:
        return _captcha_http_error(exc)

    safe_name = validate_upload_filename(file.filename, settings)
    try:
        rec = service.create_upload(
            file.file,
            safe_name,
            max_bytes=settings.max_upload_bytes,
        )
    except UploadTooLargeError as exc:
        raise HTTPException(
            status_code=413,
            detail=exc.message,
        ) from None
    return UploadResponse(
        upload_id=rec.upload_id,
        filename=rec.filename,
        size_bytes=rec.size_bytes,
    )


@router.post("/jobs", response_model=JobCreateResponse, status_code=202)
async def start_job(
    body: JobStartRequest,
    service: JobService = Depends(get_job_service),
):
    """Start conversion for an already-uploaded file (no re-upload)."""
    if body.fps < 1 or body.fps > 30:
        raise HTTPException(status_code=400, detail="fps must be 1-30")
    # upload_id must look like hex uuid-ish to reduce junk keys
    if not body.upload_id or len(body.upload_id) > 64 or not body.upload_id.isalnum():
        raise HTTPException(status_code=400, detail="invalid upload_id")
    params = ConvertParams(
        format=body.format,
        quality=body.quality,
        merge=body.merge,
        fps=body.fps,
    )
    try:
        record = service.start_job(body.upload_id, params)
    except KeyError:
        raise HTTPException(status_code=404, detail="upload not found") from None
    except FileNotFoundError:
        raise HTTPException(status_code=410, detail="upload file missing") from None
    return JobCreateResponse(job_id=record.job_id, status=record.status)


@router.get("/jobs/{job_id}", response_model=JobStatusResponse)
def get_job(job_id: str, service: JobService = Depends(get_job_service)):
    if not job_id.isalnum() or len(job_id) > 64:
        raise HTTPException(status_code=404, detail="job not found")
    rec = service.get(job_id)
    if not rec:
        raise HTTPException(status_code=404, detail="job not found")
    return JobStatusResponse(
        job_id=rec.job_id,
        status=rec.status,
        progress=rec.progress,
        result=rec.result,
        error=rec.error,
        created_at=rec.created_at,
        updated_at=rec.updated_at,
        source_name=rec.source_name,
        upload_id=rec.upload_id,
    )


@router.get("/jobs/{job_id}/download")
def download_job(job_id: str, service: JobService = Depends(get_job_service)):
    if not job_id.isalnum() or len(job_id) > 64:
        raise HTTPException(status_code=404, detail="job not found")
    rec = service.get(job_id)
    if not rec:
        raise HTTPException(status_code=404, detail="job not found")
    if rec.status.value != "SUCCEEDED" or not rec.result:
        raise HTTPException(status_code=409, detail="job not ready")
    path = service.resolve_download(job_id)
    if not path:
        raise HTTPException(status_code=404, detail="output missing")
    return FileResponse(
        path,
        filename=rec.result.download_name,
        media_type=rec.result.content_type,
        content_disposition_type="attachment",
    )


@router.get("/jobs/{job_id}/files/{filename}")
def preview_file(
    job_id: str,
    filename: str,
    service: JobService = Depends(get_job_service),
):
    """Stream a single output for in-browser preview (inline)."""
    if not job_id.isalnum() or len(job_id) > 64:
        raise HTTPException(status_code=404, detail="job not found")
    rec = service.get(job_id)
    if not rec:
        raise HTTPException(status_code=404, detail="job not found")
    if rec.status.value != "SUCCEEDED":
        raise HTTPException(status_code=409, detail="job not ready")
    path = service.resolve_file(job_id, filename)
    if not path:
        raise HTTPException(status_code=404, detail="file not found")
    # Only allow preview of files listed in result artifacts
    allowed = {o.name for o in (rec.result.outputs if rec.result else [])}
    if path.name not in allowed and (
        not rec.result or path.name != rec.result.download_name
    ):
        raise HTTPException(status_code=404, detail="file not found")
    media = (
        next(
            (
                o.content_type
                for o in (rec.result.outputs if rec.result else [])
                if o.name == path.name
            ),
            None,
        )
        or "application/octet-stream"
    )
    return FileResponse(
        path,
        filename=path.name,
        media_type=media,
        content_disposition_type="inline",
    )
