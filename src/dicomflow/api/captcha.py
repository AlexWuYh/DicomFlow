"""Cloudflare Turnstile verification (optional, toggleable)."""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from typing import Callable

from dicomflow.core.config import Settings

logger = logging.getLogger(__name__)

TURNSTILE_SITEVERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"
# Allow injection in tests
_verify_transport: Callable[[str, dict[str, str]], dict] | None = None


class CaptchaError(Exception):
    """Human-verification failed or misconfigured."""

    def __init__(self, message: str, *, code: str = "CAPTCHA_FAILED") -> None:
        super().__init__(message)
        self.message = message
        self.code = code


def set_verify_transport(fn: Callable[[str, dict[str, str]], dict] | None) -> None:
    """Test hook: replace HTTP transport for siteverify."""
    global _verify_transport
    _verify_transport = fn


def _post_siteverify(url: str, fields: dict[str, str]) -> dict:
    if _verify_transport is not None:
        return _verify_transport(url, fields)
    data = urllib.parse.urlencode(fields).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    try:
        with urllib.request.urlopen(req, timeout=8.0) as resp:  # noqa: S310
            body = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        logger.warning("Turnstile siteverify HTTP error: %s", exc)
        raise CaptchaError("人机验证服务暂时不可用，请稍后再试", code="CAPTCHA_UNAVAILABLE") from exc
    except urllib.error.URLError as exc:
        logger.warning("Turnstile siteverify network error: %s", exc)
        raise CaptchaError("人机验证服务暂时不可用，请稍后再试", code="CAPTCHA_UNAVAILABLE") from exc
    try:
        parsed = json.loads(body)
    except json.JSONDecodeError as exc:
        logger.warning("Turnstile siteverify invalid JSON")
        raise CaptchaError("人机验证服务响应异常", code="CAPTCHA_UNAVAILABLE") from exc
    if not isinstance(parsed, dict):
        raise CaptchaError("人机验证服务响应异常", code="CAPTCHA_UNAVAILABLE")
    return parsed


def verify_turnstile(
    token: str | None,
    *,
    settings: Settings,
    remoteip: str | None = None,
) -> None:
    """
    Verify a Turnstile response token when captcha is active.

    No-op when captcha is disabled or not fully configured.
    Raises CaptchaError on failure.
    """
    if not settings.captcha_enabled:
        return

    if not settings.turnstile_secret_key or not settings.turnstile_site_key:
        logger.error(
            "CAPTCHA_ENABLED but Turnstile keys missing — rejecting protected action"
        )
        raise CaptchaError(
            "人机验证未正确配置，请联系管理员",
            code="CAPTCHA_MISCONFIGURED",
        )

    if not token or not str(token).strip():
        raise CaptchaError("请先完成人机验证", code="CAPTCHA_REQUIRED")

    # Canonical siteverify body: secret (TURNSTILE_SECRET), response, remoteip
    fields: dict[str, str] = {
        "secret": settings.turnstile_secret_key,
        "response": str(token).strip(),
    }
    if remoteip and str(remoteip).strip() and remoteip not in ("unknown",):
        fields["remoteip"] = str(remoteip).strip()

    result = _post_siteverify(TURNSTILE_SITEVERIFY_URL, fields)
    if result.get("success") is True:
        return

    codes = result.get("error-codes") or []
    logger.info("Turnstile verification failed: %s", codes)
    raise CaptchaError("人机验证未通过，请重试", code="CAPTCHA_FAILED")
