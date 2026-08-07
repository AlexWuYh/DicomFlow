from __future__ import annotations

import asyncio
import json
import queue

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from starlette.requests import ClientDisconnect

from dicomflow.api.captcha import CaptchaError, verify_turnstile
from dicomflow.api.deps import get_app_settings, get_job_service
from dicomflow.api.security import client_ip
from dicomflow.api.upload_validate import validate_upload_filename
from dicomflow.core.config import Settings
from dicomflow.core.exceptions import ChunkUploadError, UploadTooLargeError
from dicomflow.core.models import (
    ChunkUploadInitRequest,
    ChunkUploadInitResponse,
    ChunkUploadPartResponse,
    ConvertParams,
    JobCreateResponse,
    JobStartRequest,
    JobStatusResponse,
    UploadResponse,
)
from dicomflow.tasks.job_service import JobService
from dicomflow.tasks.progress_hub import progress_hub

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


def _chunk_http_error(exc: ChunkUploadError) -> JSONResponse:
    status = 403 if "未启用" in (exc.message or "") else 400
    return JSONResponse(
        status_code=status,
        content={
            "detail": exc.message,
            "code": getattr(exc, "code", "CHUNK_UPLOAD_ERROR"),
        },
    )


def _disabled_chunk_response() -> JSONResponse:
    return JSONResponse(
        status_code=403,
        content={"detail": "分片上传未启用", "code": "CHUNK_UPLOAD_DISABLED"},
    )


def _verify_upload_captcha(
    request: Request, settings: Settings, token: str | None
) -> JSONResponse | None:
    tok = (token or "").strip() or None
    if not tok:
        tok = request.headers.get("cf-turnstile-response") or request.headers.get(
            "x-turnstile-token"
        )
    try:
        verify_turnstile(
            tok,
            settings=settings,
            remoteip=client_ip(
                request, trust_x_forwarded_for=settings.trust_x_forwarded_for
            ),
        )
    except CaptchaError as exc:
        return _captcha_http_error(exc)
    return None


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
    """Single-shot upload. Prefer chunked init/parts/complete behind reverse proxies."""
    captcha_err = _verify_upload_captcha(
        request, settings, cf_turnstile_response or turnstile_token
    )
    if captcha_err is not None:
        return captcha_err

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


@router.post(
    "/uploads/init",
    response_model=ChunkUploadInitResponse,
    status_code=201,
)
async def init_chunk_upload(
    request: Request,
    body: ChunkUploadInitRequest,
    service: JobService = Depends(get_job_service),
    settings: Settings = Depends(get_app_settings),
):
    """
    Start a multi-part upload session.
    Captcha (if enabled) is verified here once; subsequent parts skip captcha.
    """
    if not settings.chunked_upload_enabled:
        return _disabled_chunk_response()
    captcha_tok = body.captcha_token or body.turnstile_token
    captcha_err = _verify_upload_captcha(request, settings, captcha_tok)
    if captcha_err is not None:
        return captcha_err

    safe_name = validate_upload_filename(body.filename, settings)
    try:
        session = service.init_chunk_upload(safe_name, body.size_bytes)
    except UploadTooLargeError as exc:
        raise HTTPException(status_code=413, detail=exc.message) from None
    except ChunkUploadError as exc:
        return _chunk_http_error(exc)
    return ChunkUploadInitResponse(
        upload_id=session.upload_id,
        chunk_size_bytes=session.chunk_size_bytes,
        total_chunks=session.total_chunks,
        size_bytes=session.size_bytes,
        filename=session.filename,
    )


@router.api_route(
    "/uploads/{upload_id}/chunks/{chunk_index}",
    methods=["PUT", "POST"],
    response_model=ChunkUploadPartResponse,
)
async def upload_chunk(
    upload_id: str,
    chunk_index: int,
    request: Request,
    service: JobService = Depends(get_job_service),
    settings: Settings = Depends(get_app_settings),
):
    """
    Upload one binary part (raw body). No captcha re-check.

    Accepts PUT or POST. Body is streamed to disk (not fully buffered in RAM)
    so multi-hundred-MB packages do not stall the event loop / proxies.
    """
    if not settings.chunked_upload_enabled:
        return _disabled_chunk_response()
    if chunk_index < 0 or chunk_index > 100_000:
        raise HTTPException(status_code=400, detail="无效的分片序号")

    # Stream body to disk; full await request.body() is avoided under CF Tunnel.
    try:
        session = await _save_chunk_streaming(
            service, upload_id, chunk_index, request
        )
    except ClientDisconnect:
        # Cloudflare 524 / client abort while body is still streaming in
        return JSONResponse(
            status_code=400,
            content={
                "detail": (
                    "上传中断（常见于 Cloudflare 约 100 秒超时）。"
                    "请将 DICOMFLOW_CHUNK_SIZE_MB 设为 2 或 4 后重启服务再试。"
                ),
                "code": "CHUNK_UPLOAD_INTERRUPTED",
            },
        )
    except ChunkUploadError as exc:
        return _chunk_http_error(exc)
    return ChunkUploadPartResponse(
        upload_id=session.upload_id,
        chunk_index=chunk_index,
        received_chunks=len(session.received_indexes),
        total_chunks=session.total_chunks,
    )


async def _save_chunk_streaming(
    service: JobService,
    upload_id: str,
    chunk_index: int,
    request: Request,
):
    """
    Stream the request body to a temp file, then persist via JobService off the
    event loop (sync disk IO in a thread pool).
    """
    import tempfile
    from pathlib import Path

    from starlette.concurrency import run_in_threadpool

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".part")
    tmp_path = Path(tmp.name)
    try:
        written = 0
        # Hard ceiling slightly above max configured part (90 MB) + slack
        hard_cap = max(service.settings.chunk_size_bytes * 2, 100 * 1024 * 1024)
        try:
            async for piece in request.stream():
                if not piece:
                    continue
                written += len(piece)
                if written > hard_cap:
                    raise ChunkUploadError("分片过大")
                tmp.write(piece)
        except ClientDisconnect:
            raise
        tmp.flush()
        tmp.close()

        def _persist():
            with tmp_path.open("rb") as f:
                return service.save_chunk(upload_id, chunk_index, f)

        return await run_in_threadpool(_persist)
    finally:
        try:
            tmp.close()
        except Exception:
            pass
        tmp_path.unlink(missing_ok=True)


@router.post(
    "/uploads/{upload_id}/complete",
    response_model=UploadResponse,
    status_code=201,
)
async def complete_chunk_upload(
    upload_id: str,
    service: JobService = Depends(get_job_service),
    settings: Settings = Depends(get_app_settings),
):
    """Assemble parts and register a final UploadRecord (same shape as single-shot)."""
    if not settings.chunked_upload_enabled:
        return _disabled_chunk_response()
    try:
        rec = service.complete_chunk_upload(upload_id)
    except UploadTooLargeError as exc:
        raise HTTPException(status_code=413, detail=exc.message) from None
    except ChunkUploadError as exc:
        return _chunk_http_error(exc)
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


def _sse_pack(payload: dict, *, event: str = "status") -> str:
    """Format one SSE message (text/event-stream)."""
    data = json.dumps(payload, ensure_ascii=False, default=str)
    return f"event: {event}\ndata: {data}\n\n"


@router.get("/jobs/{job_id}/events")
async def job_events(
    job_id: str,
    request: Request,
    service: JobService = Depends(get_job_service),
):
    """
    Server-Sent Events stream of job status snapshots.

    Preferred over polling: one long-lived connection, push on progress change.
    Heartbeat comments every ~15s keep reverse proxies (Cloudflare) from idling out.
    Falls back is client-side: if EventSource fails, SPA uses GET /jobs/{id}.
    """
    if not job_id.isalnum() or len(job_id) > 64:
        raise HTTPException(status_code=404, detail="job not found")
    rec = service.get(job_id)
    if not rec:
        raise HTTPException(status_code=404, detail="job not found")

    terminal = {"SUCCEEDED", "FAILED"}

    async def event_gen():
        # Immediate snapshot so UI paints without waiting for next worker tick
        latest = service.get(job_id)
        if latest is None:
            yield _sse_pack(
                {"detail": "job not found", "code": "NOT_FOUND"},
                event="error",
            )
            return
        payload = service.status_payload(latest)
        yield _sse_pack(payload)
        if payload.get("status") in terminal:
            yield _sse_pack(payload, event="done")
            return

        q = progress_hub.subscribe(job_id)
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    # Wait up to 15s for a real progress event (worker thread publishes)
                    item = await asyncio.to_thread(q.get, True, 15.0)
                except queue.Empty:
                    # Heartbeat + soft re-sync from DB (covers missed publishes)
                    yield ": heartbeat\n\n"
                    cur = service.get(job_id)
                    if cur is None:
                        break
                    payload = service.status_payload(cur)
                    yield _sse_pack(payload)
                    if payload.get("status") in terminal:
                        yield _sse_pack(payload, event="done")
                        break
                    continue

                yield _sse_pack(item)
                if item.get("status") in terminal:
                    yield _sse_pack(item, event="done")
                    break
        finally:
            progress_hub.unsubscribe(job_id, q)

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # nginx / some proxies
            "CDN-Cache-Control": "no-store",
            "Cloudflare-CDN-Cache-Control": "no-store",
        },
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
