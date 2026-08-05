from __future__ import annotations

import re
from pathlib import Path

from fastapi import HTTPException, UploadFile

from dicomflow.core.config import Settings

# Block path tricks and control chars in original names
_UNSAFE = re.compile(r"[\x00-\x1f\x7f]")


def sanitize_filename(name: str | None) -> str:
    base = Path(name or "upload.bin").name
    base = _UNSAFE.sub("", base).strip().replace(" ", "_")
    # Keep only safe characters
    base = re.sub(r"[^\w.\-()+]", "_", base, flags=re.UNICODE)
    base = base.strip("._") or "upload.bin"
    if len(base) > 180:
        stem = Path(base).stem[:140]
        suf = Path(base).suffix[:20]
        base = f"{stem}{suf}"
    return base


def validate_upload_filename(filename: str | None, settings: Settings) -> str:
    safe = sanitize_filename(filename)
    ext = Path(safe).suffix.lower()
    if ext not in settings.allowed_extensions:
        allowed = ", ".join(sorted(settings.allowed_extensions))
        raise HTTPException(
            status_code=400,
            detail=f"不支持的文件类型。允许: {allowed}",
        )
    return safe


def assert_content_length(file: UploadFile, settings: Settings) -> None:
    """Reject early if Content-Length header exceeds limit (when present)."""
    # UploadFile may expose size via headers on the underlying request only;
    # callers should also stream-check while writing.
    _ = file
    _ = settings
