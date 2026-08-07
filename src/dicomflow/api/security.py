from __future__ import annotations

import re
import secrets
import threading
import time
from collections import defaultdict, deque
from typing import Callable

from starlette.datastructures import Headers, MutableHeaders
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from dicomflow.core.config import Settings

# Paths that never require access token (probe / ops)
PUBLIC_PATH_PREFIXES = (
    "/health",
    "/api/v1/health",
    "/api/v1/bootstrap",
)

# Multi-part chunk body: higher RPM so large packages are not mid-stream blocked
_CHUNK_PATH_RE = re.compile(r"^/api/v1/uploads/[^/]+/chunks/\d+$")
# Job status polling (SPA hits this every ~1–2s during convert)
_JOB_STATUS_RE = re.compile(r"^/api/v1/jobs/[a-zA-Z0-9]+$")

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    # strict-origin-when-cross-origin (not no-referrer): Turnstile / third-party
    # challenges need to see our origin for hostname checks
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    "Cross-Origin-Opener-Policy": "same-origin",
    # cross-origin (not same-origin): avoid blocking challenge iframes/workers
    "Cross-Origin-Resource-Policy": "cross-origin",
    # CSP: self + Google Fonts + Cloudflare Turnstile
    # https://developers.cloudflare.com/turnstile/reference/content-security-policy/
    "Content-Security-Policy": (
        "default-src 'self'; "
        "script-src 'self' https://challenges.cloudflare.com; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com data:; "
        "img-src 'self' data: blob: https://challenges.cloudflare.com; "
        "media-src 'self' blob:; "
        "connect-src 'self' https://challenges.cloudflare.com; "
        "frame-src 'self' https://challenges.cloudflare.com; "
        "worker-src 'self' blob: https://challenges.cloudflare.com; "
        "child-src 'self' blob: https://challenges.cloudflare.com; "
        "frame-ancestors 'none'; "
        "base-uri 'self'; "
        "form-action 'self'"
    ),
}


def client_ip(request: Request, *, trust_x_forwarded_for: bool) -> str:
    if trust_x_forwarded_for:
        xff = request.headers.get("x-forwarded-for")
        if xff:
            return xff.split(",")[0].strip() or "unknown"
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


def _client_ip_from_scope(scope: Scope, *, trust_x_forwarded_for: bool) -> str:
    """Resolve client IP without constructing a full Request (avoids body buffering)."""
    if trust_x_forwarded_for:
        headers = Headers(scope=scope)
        xff = headers.get("x-forwarded-for")
        if xff:
            return xff.split(",")[0].strip() or "unknown"
    client = scope.get("client")
    if client and client[0]:
        return str(client[0])
    return "unknown"


class RateLimiter:
    """Simple in-memory sliding window limiter (single-process)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def allow(self, key: str, *, limit: int, window_seconds: float) -> bool:
        now = time.monotonic()
        with self._lock:
            q = self._hits[key]
            cutoff = now - window_seconds
            while q and q[0] < cutoff:
                q.popleft()
            if len(q) >= limit:
                return False
            q.append(now)
            return True


_rate_limiter = RateLimiter()


def extract_access_token(request: Request) -> str | None:
    header = request.headers.get("x-dicomflow-token") or request.headers.get(
        "authorization"
    )
    if header:
        if header.lower().startswith("bearer "):
            return header[7:].strip() or None
        return header.strip() or None
    cookie = request.cookies.get("dicomflow_token")
    return cookie.strip() if cookie else None


def extract_access_token_from_headers(headers: Headers) -> str | None:
    header = headers.get("x-dicomflow-token") or headers.get("authorization")
    if header:
        if header.lower().startswith("bearer "):
            return header[7:].strip() or None
        return header.strip() or None
    # Cookie is available via headers as well
    cookie = headers.get("cookie") or ""
    for part in cookie.split(";"):
        part = part.strip()
        if part.lower().startswith("dicomflow_token="):
            return part.split("=", 1)[1].strip() or None
    return None


def token_ok(provided: str | None, expected: str) -> bool:
    if not provided:
        return False
    return secrets.compare_digest(provided, expected)


class SecurityMiddleware:
    """
    Access token + rate limits + security headers.

    Implemented as pure ASGI middleware (not BaseHTTPMiddleware).
    BaseHTTPMiddleware buffers request bodies and is known to hang/deadlock
    on multi-megabyte uploads — fatal for chunked DICOM packages behind CF Tunnel.
    """

    def __init__(self, app: ASGIApp, settings: Settings):
        self.app = app
        self.settings = settings

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path") or "/"
        path_norm = path.rstrip("/") or "/"
        method = (scope.get("method") or "GET").upper()
        ip = _client_ip_from_scope(
            scope, trust_x_forwarded_for=self.settings.trust_x_forwarded_for
        )
        is_chunk_part = bool(_CHUNK_PATH_RE.match(path_norm)) and method in (
            "PUT",
            "POST",
        )
        # GET /api/v1/jobs/{id} only — not /download or /files/*
        is_job_poll = method == "GET" and bool(_JOB_STATUS_RE.match(path_norm))

        # Rate budgets: chunks and job polls must not share the tiny global RPM
        # (SPA polls ~1/s during convert; 60 RPM global would 429 mid-job).
        if is_chunk_part:
            if not _rate_limiter.allow(
                f"chunk_rpm:{ip}",
                limit=max(1, self.settings.rate_limit_chunk_rpm),
                window_seconds=60.0,
            ):
                await self._send_json(
                    scope,
                    receive,
                    send,
                    429,
                    "RATE_LIMITED",
                    "分片上传过于频繁，请稍后再试",
                )
                return
        elif is_job_poll:
            if not _rate_limiter.allow(
                f"job_poll_rpm:{ip}",
                limit=max(1, self.settings.rate_limit_job_poll_rpm),
                window_seconds=60.0,
            ):
                await self._send_json(
                    scope,
                    receive,
                    send,
                    429,
                    "RATE_LIMITED",
                    "进度查询过于频繁，请稍后再试",
                )
                return
        elif not _rate_limiter.allow(
            f"rpm:{ip}",
            limit=max(1, self.settings.rate_limit_rpm),
            window_seconds=60.0,
        ):
            await self._send_json(
                scope,
                receive,
                send,
                429,
                "RATE_LIMITED",
                "请求过于频繁，请稍后再试",
            )
            return

        # Upload-specific hourly limit (count whole-file and init only — not each part)
        if method == "POST" and path_norm in (
            "/api/v1/uploads",
            "/api/v1/uploads/init",
        ):
            if not _rate_limiter.allow(
                f"up:{ip}",
                limit=max(1, self.settings.rate_limit_uploads_per_hour),
                window_seconds=3600.0,
            ):
                await self._send_json(
                    scope,
                    receive,
                    send,
                    429,
                    "UPLOAD_RATE_LIMITED",
                    "上传次数过多，请稍后再试",
                )
                return

        # Access token for API routes (except public)
        if self.settings.access_token and self._needs_auth(path):
            headers = Headers(scope=scope)
            provided = extract_access_token_from_headers(headers)
            if not token_ok(provided, self.settings.access_token):
                await self._send_json(
                    scope,
                    receive,
                    send,
                    401,
                    "AUTH_REQUIRED",
                    "需要访问密码",
                    extra_headers={"WWW-Authenticate": "Bearer"},
                )
                return

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                for k, v in SECURITY_HEADERS.items():
                    if k not in headers:
                        headers[k] = v
                if path.startswith("/api/") and "cache-control" not in headers:
                    headers["Cache-Control"] = "no-store"
            await send(message)

        await self.app(scope, receive, send_with_headers)

    def _needs_auth(self, path: str) -> bool:
        if not path.startswith("/api/"):
            return False
        for prefix in PUBLIC_PATH_PREFIXES:
            if path == prefix or path.rstrip("/") == prefix.rstrip("/"):
                return False
        return True

    async def _send_json(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
        status: int,
        code: str,
        message: str,
        *,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        # Drain request body so clients/proxies do not hang on unread payload
        more = True
        while more:
            msg = await receive()
            if msg["type"] != "http.request":
                break
            more = bool(msg.get("more_body", False))

        response = JSONResponse(
            status_code=status,
            content={"detail": message, "code": code},
            headers=extra_headers,
        )
        for k, v in SECURITY_HEADERS.items():
            response.headers.setdefault(k, v)
        if (scope.get("path") or "").startswith("/api/"):
            response.headers.setdefault("Cache-Control", "no-store")

        async def _empty_receive() -> Message:
            return {"type": "http.disconnect"}

        await response(scope, _empty_receive, send)
