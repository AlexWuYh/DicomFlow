# Build offline Windows portable folder with PyInstaller.
# Run from anywhere; switches to repo root.
#   powershell -ExecutionPolicy Bypass -File apps/offline/windows/build.ps1
# Optional: -Console   keep a console window for debugging

param(
    [switch]$Console
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..\..\..")
Set-Location $Root

Write-Host "==> Repo: $Root"
Write-Host "==> Installing app + pyinstaller deps"
python -m pip install -U pip
python -m pip install -e ".[app]" pyinstaller

$spec = Join-Path $Root "apps\offline\windows\DicomFlow.spec"
$dist = Join-Path $Root "dist\DicomFlow"
if (Test-Path $dist) {
    Remove-Item -Recurse -Force $dist
}

Write-Host "==> PyInstaller"
if ($Console) {
    python -m PyInstaller --noconfirm --clean $spec -- --console
} else {
    python -m PyInstaller --noconfirm --clean $spec
}

$exe = Join-Path $dist "DicomFlow.exe"
if (-not (Test-Path $exe)) {
    Write-Error "Build failed: $exe not found"
}

Write-Host ""
Write-Host "OK: portable app at:"
Write-Host "  $dist"
Write-Host "Run: $exe"
Write-Host "Data: %LOCALAPPDATA%\DicomFlow"
Write-Host ""
Write-Host "Offline check: disconnect network, open app, convert a local zip."
