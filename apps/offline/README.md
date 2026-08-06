# Offline App (Windows + Android)

Fully offline tool packaging for DicomFlow. Product rules: [`.ai/12-offline-app.md`](../../.ai/12-offline-app.md).

| Platform | Status | Entry |
|----------|--------|--------|
| **Windows** | In progress | `dicomflow app` (pywebview + local server) |
| **Android** | Scaffold | See [android/](./android/) |

## Windows (developer run)

```bash
pip install -e ".[app]"
dicomflow app
```

- Binds **127.0.0.1 only**
- Disables access password and Turnstile
- Data under `%LOCALAPPDATA%\DicomFlow` by default

Packaging notes: [windows/](./windows/).

## Android

See [android/README.md](./android/README.md). Engine reuse on Android is harder; Windows ships first.
