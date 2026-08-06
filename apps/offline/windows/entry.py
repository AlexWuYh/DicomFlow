"""
Windows / desktop frozen entry for PyInstaller.

Usage (dev):
  python apps/offline/windows/entry.py

Packaged builds call this module as the Analysis script path.
"""

from __future__ import annotations

import sys
from pathlib import Path


def _ensure_src_on_path() -> None:
    """Dev checkout: allow running without install when src/ is present."""
    if getattr(sys, "frozen", False):
        return
    root = Path(__file__).resolve().parents[3]
    src = root / "src"
    if src.is_dir() and str(src) not in sys.path:
        sys.path.insert(0, str(src))


def main() -> None:
    _ensure_src_on_path()
    from dicomflow.desktop.app import run_offline_app

    raise SystemExit(run_offline_app())


if __name__ == "__main__":
    main()
