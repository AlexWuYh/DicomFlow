# Windows offline packaging

## Dev

```bash
pip install -e ".[app]"
dicomflow app
```

Requires **WebView2** (preinstalled on most Win10/11).

## Portable / installer (planned)

Target stack:

1. **PyInstaller** (or Nuitka) one-folder build including:
   - `dicomflow` + deps
   - `imageio-ffmpeg` binary
   - `web/` static assets
2. Optional **Inno Setup** installer
3. Offline-only: no outbound network required after install

Example (draft, refine on a Windows builder):

```bash
pip install -e ".[app]" pyinstaller
pyinstaller --noconfirm --windowed --name DicomFlow ^
  --add-data "web;web" ^
  --collect-all imageio_ffmpeg ^
  -m dicomflow app
```

CI for signed Windows builds can be added when the milestone nears release.

## Offline checklist

- [ ] No captcha / token prompts
- [ ] Convert zip/rar without internet
- [ ] Outputs under user data dir
- [ ] Quit window stops local server
