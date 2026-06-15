.PHONY: help setup start-linux stop-linux doctor-linux infra-up infra-down test-ai test-go test validate build-video ai-dev

help:
	@echo "Citévision v2 targets:"
	@echo "  setup        WSL/dev environment (setup-wsl.sh)"
	@echo "  start-linux  Full stack Linux/WSL (recommended)"
	@echo "  stop-linux   Stop stack Linux/WSL"
	@echo "  doctor-linux Health check Linux/WSL"
	@echo "  infra-up     Start Docker infra (ports 5433/6380/1884/9003)"
	@echo "  infra-down   Stop Docker infra"
	@echo "  test-ai      Run ai-engine pytest"
	@echo "  test-go      Run rules-engine go test"
	@echo "  test         Run all unit tests"
	@echo "  validate     Run validate-phase1..8"
	@echo "  build-video  Build video engine (FFmpeg required)"
	@echo "  ai-dev       Run AI engine on :8001"

setup:
	bash scripts/setup-wsl.sh

start-linux:
	bash scripts/start-linux.sh

stop-linux:
	bash scripts/stop-linux.sh

doctor-linux:
	bash scripts/doctor-linux.sh

reset-db:
	bash scripts/reset-db.sh

infra-up:
	docker compose -f infra/docker-compose.yml up -d

infra-down:
	docker compose -f infra/docker-compose.yml down

test-ai:
	cd ai-engine && pip install -q -e . pytest pytest-asyncio httpx && pytest

test-go:
	cd rules-engine && go test ./...

test: test-ai test-go

validate:
	@for i in 1 2 3 4 5 6 7 8; do bash scripts/validate-phase$$i.sh; done

build-video:
	cd video-engine && mkdir -p build && cd build && cmake .. && cmake --build .

ai-dev:
	cd ai-engine && PYTHONPATH=src uvicorn citevision_ai.main:app --reload --port 8001

start:
	bash scripts/start-linux.sh
