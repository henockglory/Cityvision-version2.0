.PHONY: help setup start stop test validate build-video clean

help:
	@echo "Citévision 2.0 — available targets:"
	@echo "  setup         WSL/dev environment setup"
	@echo "  start         Start infrastructure + AI engine"
	@echo "  stop          Stop all services"
	@echo "  test          Run all validation scripts"
	@echo "  validate      Run L1-L13 + final validation"
	@echo "  build-video   Build video engine (requires FFmpeg dev libs)"
	@echo "  download-model Download YOLOv8n ONNX model"
	@echo "  ai-dev        Run AI engine locally"

setup:
	bash scripts/setup-wsl.sh

start:
	bash scripts/start-all.sh

stop:
	bash scripts/stop-all.sh

test:
	bash scripts/run-all-tests.sh

validate:
	@for i in 1 2 3 4 5 6 7 8 9 10 11 12 13; do bash scripts/validate-l$$i.sh; done
	bash scripts/validate-final.sh

download-model:
	bash scripts/download-yolo-model.sh

build-video:
	cd video-engine && mkdir -p build && cd build && cmake .. && cmake --build .

ai-dev:
	cd ai-engine && PYTHONPATH=src uvicorn citevision_ai.main:app --reload --port 8000

clean:
	rm -rf video-engine/build ai-engine/.pytest_cache ai-engine/**/__pycache__
