from __future__ import annotations

import re
import secrets
import threading
import time
from collections import defaultdict, deque
from typing import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from dicomflow.core.config import Settings

# Paths that never require access token (probe / ops)
PUBLIC_PATH_PREFIXES = (
    "/health",
    "/api/v1/health",
    "/api/v1/bootstrap",
)

# Multi-part chunk PUT: higher RPM so large packages are not mid-stream blocked
_CHUNK_PATH_RE = re.compile(r"^/api/v1/uploads/[^/]+/chunks/\d+$")

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


def token_ok(provided: str | None, expected: str) -> bool:
    if not provided:
        return False
    return secrets.compare_digest(provided, expected)


class SecurityMiddleware(BaseHTTPMiddleware):
    """Access token + rate limits + security headers."""

    def __init__(self, app, settings: Settings):  # noqa: ANN001
        super().__init__(app)
        self.settings = settings

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        path = request.url.path
        path_norm = path.rstrip("/") or "/"
        method = request.method.upper()
        ip = client_ip(request, trust_x_forwarded_for=self.settings.trust_x_forwarded_for)
        is_chunk_part = bool(_CHUNK_PATH_RE.match(path_norm)) and method == "PUT"

        # Global RPM (chunk parts use a higher dedicated budget)
        if is_chunk_part:
            if not _rate_limiter.allow(
                f"chunk_rpm:{ip}",
                limit=max(1, self.settings.rate_limit_chunk_rpm),
                window_seconds=60.0,
            ):
                return self._json(
                    429,
                    "RATE_LIMITED",
                    "分片上传过于频繁，请稍后再试",
                )
        elif not _rate_limiter.allow(
            f"rpm:{ip}",
            limit=max(1, self.settings.rate_limit_rpm),
            window_seconds=60.0,
        ):
            return self._json(
                429,
                "RATE_LIMITED",
                "请求过于频繁，请稍后再试",
            )

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
                return self._json(
                    429,
                    "UPLOAD_RATE_LIMITED",
                    "上传次数过多，请稍后再试",
                )

        # Access token for API routes (except public)
        if self.settings.access_token and self._needs_auth(path):
            provided = extract_access_token(request)
            if not token_ok(provided, self.settings.access_token):
                return self._json(
                    401,
                    "AUTH_REQUIRED",
                    "需要访问密码",
                    headers={"WWW-Authenticate": "Bearer"},
                )

        response = await call_next(request)
        for k, v in SECURITY_HEADERS.items():
            response.headers.setdefault(k, v)
        # Avoid caching sensitive API responses
        if path.startswith("/api/"):
            response.headers.setdefault("Cache-Control", "no-store")
        return response

    def _needs_auth(self, path: str) -> bool:
        if not path.startswith("/api/"):
            return False
        for prefix in PUBLIC_PATH_PREFIXES:
            if path == prefix or path.rstrip("/") == prefix.rstrip("/"):
                return False
        return True

    @staticmethod
    def _json(
        status: int,
        code: str,
        message: str,
        *,
        headers: dict[str, str] | None = None,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status,
            content={"detail": message, "code": code},
            headers=headers,
        )
