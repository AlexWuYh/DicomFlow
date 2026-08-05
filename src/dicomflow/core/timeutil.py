from __future__ import annotations

from datetime import datetime, timezone


def utc_now() -> datetime:
    """Timezone-aware UTC now (preferred over datetime.utcnow)."""
    return datetime.now(timezone.utc)


def as_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def to_iso(dt: datetime) -> str:
    return as_utc(dt).isoformat()


def from_iso(value: str) -> datetime:
    dt = datetime.fromisoformat(value)
    return as_utc(dt)
