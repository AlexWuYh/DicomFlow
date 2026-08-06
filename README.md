# DicomFlow

**English** | [简体中文](./README.zh-CN.md)

Convert hospital DICOM archives (**zip / rar**) into **MP4 / GIF** that any phone or desktop player can open — handy for cross-hospital review and sharing.

> Design & specs: [`.ai/00-index.md`](.ai/00-index.md)

## How to use (web)

1. Open the site (local default: http://127.0.0.1:8765 )
2. Upload the archive from the hospital
3. Choose format (MP4/GIF), quality, and optionally **merge into one file**
4. Convert → preview → download
5. **Results are kept for 24 hours by default** — save them promptly

If the site asks for an access password, request it from the operator (end users do not need the server config).

## Quick start (Docker)

```bash
docker compose up -d --build
open http://127.0.0.1:8765
```

Before public exposure, set an access password (token):

```bash
export DICOMFLOW_ACCESS_TOKEN="$(openssl rand -hex 32)"
docker compose up -d --build
```

Optional human verification (Cloudflare Turnstile), independent of the access password:

```bash
export DICOMFLOW_CAPTCHA_ENABLED=true
export DICOMFLOW_TURNSTILE_SITE_KEY="your-site-key"
export TURNSTILE_SECRET="your-secret"   # never commit this
```

More security notes: [`.ai/09-security.md`](.ai/09-security.md).

## Local development

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# CLI
dicomflow convert -i ./study.zip -o ./out --format mp4 --quality high
dicomflow serve   # http://127.0.0.1:8765

# Tests
pytest -q
```

On macOS, RAR extraction: `brew install unar`

## Branches & releases

| Branch | Role |
|--------|------|
| **`main`** | Release line. Every push runs the **Release** workflow (tests + sdist/wheel; creates a GitHub Release when `v{version}` is new). |
| **`dev`** | Development integration. Open feature PRs **into `dev`**. |

Flow: `feature/*` → `dev` → (release) → `main`.  
Details: [CONTRIBUTING.md](./CONTRIBUTING.md).

## Repository layout

```
.ai/              # product / architecture / security specs
src/dicomflow/    # API, engine, tasks, storage
web/              # static frontend
tests/
.github/workflows # CI (dev) + Release (main)
Dockerfile
docker-compose.yml
```

Runtime data (gitignored): `data/` (`dicomflow.db`, uploads, outputs)

## Configuration (common)

| Variable | Default | Description |
|----------|---------|-------------|
| `DICOMFLOW_DATA_DIR` | `./data` | Data root |
| `DICOMFLOW_HOST` / `PORT` | `127.0.0.1` / `8765` | Listen address |
| `DICOMFLOW_ACCESS_TOKEN` | empty | Recommended on public internet (toggle: set / clear) |
| `DICOMFLOW_CAPTCHA_ENABLED` | `false` | Human verification (Cloudflare Turnstile) |
| `DICOMFLOW_TURNSTILE_SITE_KEY` | empty | Required when captcha is on (public site key) |
| `TURNSTILE_SECRET` | empty | Required when captcha is on (server secret; do not commit) |
| `DICOMFLOW_ENABLE_DOCS` | `false` | OpenAPI docs |
| `DICOMFLOW_MAX_UPLOAD_BYTES` | 1 GiB | Upload size limit |
| `DICOMFLOW_JOB_TTL_HOURS` | `24` | Auto-cleanup TTL |
| `DICOMFLOW_TRUST_X_FORWARDED_FOR` | `false` | Enable only behind a trusted reverse proxy |
| `DICOMFLOW_ALLOWED_HOSTS` | `*` | Set to your domain in production |

Full example: [`.env.example`](./.env.example)

For local Turnstile testing, add `localhost` and `127.0.0.1` (no port) under Hostname Management in the Cloudflare dashboard.

## License

[MIT License](./LICENSE).

Not a medical device. Does not replace a clinical PACS/viewer. Not for diagnosis.
