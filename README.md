# DicomFlow

**English** | [简体中文](./README.zh-CN.md)

Convert hospital DICOM archives (**zip / rar**) into **MP4 / GIF** that any phone or desktop player can open — handy for cross-hospital review and sharing.

## How to use (web)

1. Open the site (local default: http://127.0.0.1:8765 )
2. Upload the archive from the hospital
3. Choose format (MP4/GIF), quality, and optionally **merge into one file**
4. Convert → preview → download
5. **Results are kept for 24 hours by default** — save them promptly

If the site asks for an access password, request it from the operator (end users do not need the server config).

## Quick start (Docker)

### Docker Compose (default: GHCR `latest`)

**Using GHCR does not require a Dockerfile** — only Docker and network access to `ghcr.io`.

| Tag | Image |
|-----|--------|
| Latest (compose default) | `ghcr.io/alexwuyh/dicomflow:latest` |
| Version pin | `ghcr.io/alexwuyh/dicomflow:0.2.0` |
| Package page | https://github.com/AlexWuYh/DicomFlow/pkgs/container/dicomflow |

```bash
# Pull + run (no source tree / Dockerfile needed)
docker compose pull
docker compose up -d
# open http://127.0.0.1:8765

# Pin a version
DICOMFLOW_IMAGE=ghcr.io/alexwuyh/dicomflow:0.2.0 docker compose up -d
```

If `ghcr.io` is unreachable (timeout), fix network/mirror/proxy first — Compose will **not** build from source unless you ask:

```bash
# Full git clone required (Dockerfile + src + web):
docker compose -f docker-compose.yml -f docker-compose.build.yml up -d --build
```

Optional dev mounts (hot-reload `web/`, `./input`):

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d
```

```bash
# Plain docker run
docker pull ghcr.io/alexwuyh/dicomflow:latest
docker run -d --name dicomflow \
  -p 8765:8765 \
  -v dicomflow-data:/data \
  -e DICOMFLOW_ACCESS_TOKEN="$(openssl rand -hex 32)" \
  ghcr.io/alexwuyh/dicomflow:latest
```

If the package is private, authenticate first:

```bash
echo "$GITHUB_TOKEN" | docker login ghcr.io -u USERNAME --password-stdin
```

Public repos can set the package visibility to **Public** under GitHub → Packages → `dicomflow` → Package settings.

Before public exposure, set an access password (token):

```bash
export DICOMFLOW_ACCESS_TOKEN="$(openssl rand -hex 32)"
docker compose up -d
```

Behind **Cloudflare Tunnel / Zero Trust**, single-request uploads are often limited to ~**100MB**. Enable chunked upload:

```bash
export DICOMFLOW_CHUNKED_UPLOAD_ENABLED=true
# optional, default 16 MB per part (range 1–90)
# export DICOMFLOW_CHUNK_SIZE_MB=16
docker compose up -d
```

Optional human verification (Cloudflare Turnstile), independent of the access password:

```bash
export DICOMFLOW_CAPTCHA_ENABLED=true
export DICOMFLOW_TURNSTILE_SITE_KEY="your-site-key"
export TURNSTILE_SECRET="your-secret"   # never commit this
```

For public deploy: set a strong `DICOMFLOW_ACCESS_TOKEN`, use HTTPS, and keep `DICOMFLOW_ENABLE_DOCS=false`. Optional Turnstile captcha via `DICOMFLOW_CAPTCHA_ENABLED` + keys (see configuration table below).

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

## Repository layout

```
src/dicomflow/    # API, engine, tasks, storage
web/              # static frontend
tests/
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
| `DICOMFLOW_CHUNKED_UPLOAD_ENABLED` | `false` | Multi-part upload (enable behind Cloudflare Tunnel) |
| `DICOMFLOW_CHUNK_SIZE_MB` | `16` | Part size in MB when chunked is on (1–90) |
| `DICOMFLOW_JOB_TTL_HOURS` | `24` | Auto-cleanup TTL |
| `DICOMFLOW_TRUST_X_FORWARDED_FOR` | `false` | Enable only behind a trusted reverse proxy |
| `DICOMFLOW_ALLOWED_HOSTS` | `*` | Set to your domain in production |

Full example: [`.env.example`](./.env.example)

For local Turnstile testing, add `localhost` and `127.0.0.1` (no port) under Hostname Management in the Cloudflare dashboard.

## License

[MIT License](./LICENSE).

Not a medical device. Does not replace a clinical PACS/viewer. Not for diagnosis.
