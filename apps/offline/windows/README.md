# Windows offline packaging

Fully offline desktop tool: local convert only, no password / captcha / outbound services.

## Developer run

```bash
pip install -e ".[app]"
dicomflow app
# or:
python apps/offline/windows/entry.py
```

- Requires **WebView2** (preinstalled on most Win10/11)
- Data dir: `%LOCALAPPDATA%\DicomFlow`
- Binds `127.0.0.1` only

## Portable build (Windows)

On a **Windows** machine with Python 3.11+:

```powershell
powershell -ExecutionPolicy Bypass -File apps/offline/windows/build.ps1
# debug console:
powershell -ExecutionPolicy Bypass -File apps/offline/windows/build.ps1 -Console
```

Output:

```
dist/DicomFlow/
  DicomFlow.exe
  _internal/   # runtime + web/ + ffmpeg via imageio-ffmpeg
```

Copy the whole `DicomFlow` folder to a USB stick; no install required.

### Smoke build on macOS/Linux (packaging only)

```bash
bash apps/offline/windows/build.sh
```

Does not replace a real Windows QA pass.

## Offline acceptance checklist

- [ ] Disconnect network → app still opens
- [ ] No access-password dialog, no Turnstile widget
- [ ] Upload local zip/rar → convert → preview/download works
- [ ] Outputs under `%LOCALAPPDATA%\DicomFlow`
- [ ] Closing the window stops the process (no orphan python/uvicorn)

## Notes

- **RAR**: needs a system `unrar`/`7z` if not bundled; zip always works via stdlib. Future: ship `unrar` in `_internal` if license allows.
- **WebView2**: if missing, install Evergreen Runtime from Microsoft.
- Spec file: `DicomFlow.spec` (one-folder COLLECT layout for easier ffmpeg data files).
