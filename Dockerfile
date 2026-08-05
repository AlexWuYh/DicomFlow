# DicomFlow — local-first DICOM → MP4/GIF web converter
FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    DICOMFLOW_HOST=0.0.0.0 \
    DICOMFLOW_PORT=8765 \
    DICOMFLOW_DATA_DIR=/data \
    DICOMFLOW_WEB_DIR=/app/web \
    DICOMFLOW_ENABLE_DOCS=false

# System deps: unrar (RAR5), ffmpeg fallback, build tools for wheels if needed
RUN apt-get update && apt-get install -y --no-install-recommends \
      ca-certificates \
      curl \
      ffmpeg \
      p7zip-full \
      unrar-free \
    && rm -rf /var/lib/apt/lists/*

# Official unrar (RAR5) for amd64 when available; arm64 relies on unrar-free (verified on sample).
RUN set -eux; \
    arch="$(dpkg --print-architecture)"; \
    if [ "$arch" = "amd64" ]; then \
      curl -fsSL -o /tmp/rar.tar.gz https://www.rarlab.com/rar/rarlinux-x64-701.tar.gz; \
      tar -xzf /tmp/rar.tar.gz -C /tmp; \
      install -m 755 /tmp/rar/unrar /usr/local/bin/unrar; \
      rm -rf /tmp/rar /tmp/rar.tar.gz; \
    fi; \
    (command -v unrar && unrar 2>&1 | head -1) || (command -v unrar-free && unrar-free 2>&1 | head -1) || true

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src
COPY web ./web

RUN pip install --upgrade pip \
    && pip install --no-cache-dir .

# Runtime dirs
RUN mkdir -p /data/uploads /data/work /data/outputs \
    && useradd --create-home --shell /bin/bash dicomflow \
    && chown -R dicomflow:dicomflow /data /app

USER dicomflow
EXPOSE 8765
VOLUME ["/data"]

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD curl -fsS "http://127.0.0.1:${DICOMFLOW_PORT}/health" || exit 1

CMD ["dicomflow", "serve", "--host", "0.0.0.0", "--port", "8765"]
