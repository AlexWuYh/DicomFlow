.PHONY: build up down logs convert-sample shell health

IMAGE ?= dicomflow:local
PORT ?= 8765

# Prefer docker compose; fall back to podman
COMPOSE ?= $(shell command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1 && echo "docker compose" || echo "podman compose")

build:
	$(COMPOSE) build

up:
	$(COMPOSE) up -d --build
	@echo "Open http://127.0.0.1:$(PORT)"

down:
	$(COMPOSE) down

logs:
	$(COMPOSE) logs -f dicomflow

health:
	curl -fsS http://127.0.0.1:$(PORT)/health && echo

# Convert mounted real CT package inside container
convert-sample:
	$(COMPOSE) exec dicomflow \
		dicomflow convert -i /input/C252708.rar -o /data/outputs/real_ct \
		--format mp4 --quality medium --fps 10

shell:
	$(COMPOSE) exec dicomflow bash
