# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for offline Windows (also works on macOS/Linux for smoke builds).
# Build from repo root:
#   pyinstaller apps/offline/windows/DicomFlow.spec
from __future__ import annotations

import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_submodules

REPO = Path(SPECPATH).resolve().parents[2]
ENTRY = REPO / "apps" / "offline" / "windows" / "entry.py"
WEB = REPO / "web"

datas: list = [(str(WEB), "web")]
binaries: list = []
hiddenimports: list = [
    "uvicorn.logging",
    "uvicorn.loops",
    "uvicorn.loops.auto",
    "uvicorn.protocols",
    "uvicorn.protocols.http",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan",
    "uvicorn.lifespan.on",
    "dicomflow",
    "dicomflow.api",
    "dicomflow.api.app",
    "dicomflow.api.routes",
    "dicomflow.api.routes.jobs",
    "dicomflow.api.routes.system",
    "dicomflow.desktop",
    "dicomflow.desktop.app",
    "dicomflow.engine",
    "dicomflow.tasks",
    "dicomflow.storage",
    "webview",
]

for pkg in (
    "imageio_ffmpeg",
    "imageio",
    "pydicom",
    "uvicorn",
    "anyio",
    "starlette",
    "fastapi",
    "pydantic",
    "pydantic_settings",
):
    try:
        d, b, h = collect_all(pkg)
        datas += d
        binaries += b
        hiddenimports += h
    except Exception:
        hiddenimports += collect_submodules(pkg)

# Windows GUI subsystem when building on Windows; console helps debugging first builds
console = False
if "--console" in sys.argv:
    console = True

a = Analysis(
    [str(ENTRY)],
    pathex=[str(REPO / "src")],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="DicomFlow",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=console,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="DicomFlow",
)
