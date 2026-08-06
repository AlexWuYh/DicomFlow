#!/usr/bin/env bash
# Smoke-build the offline desktop bundle (same spec as Windows).
# On macOS/Linux this validates packaging; ship Windows builds from build.ps1.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
cd "$ROOT"

echo "==> Repo: $ROOT"
python3 -m pip install -U pip
python3 -m pip install -e ".[app]" pyinstaller

rm -rf dist/DicomFlow build
python3 -m PyInstaller --noconfirm --clean apps/offline/windows/DicomFlow.spec

if [[ ! -d dist/DicomFlow ]]; then
  echo "Build failed: dist/DicomFlow missing" >&2
  exit 1
fi

echo "OK: dist/DicomFlow (run the DicomFlow binary inside)"
echo "Windows release builds: use apps/offline/windows/build.ps1 on a Windows machine."
