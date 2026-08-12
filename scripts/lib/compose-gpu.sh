#!/usr/bin/env bash
# Frigate GPU compose override (TensorRT image + gpus: all).
# Source: source "$ROOT/scripts/lib/compose-gpu.sh"
#
# Usage:
#   cd infra && docker compose $(compose_gpu_files) --profile frigate up -d frigate
#   # from repo root:
#   docker compose $(compose_gpu_files infra/) --profile frigate up -d frigate
#
# prefix: "" (cwd=infra) or "infra/" (cwd=repo root). Do not also pass -f docker-compose.yml.

compose_gpu_files() {
  local prefix="${1:-}"
  local nvidia=""
  local base=""
  if [[ -n "${ROOT:-}" && -f "$ROOT/infra/docker-compose.nvidia.yml" ]]; then
    nvidia="$ROOT/infra/docker-compose.nvidia.yml"
    base="$ROOT/infra/docker-compose.yml"
  elif [[ -n "$prefix" && -f "${prefix}docker-compose.nvidia.yml" ]]; then
    nvidia="${prefix}docker-compose.nvidia.yml"
    base="${prefix}docker-compose.yml"
  elif [[ -f ./docker-compose.nvidia.yml ]]; then
    nvidia="./docker-compose.nvidia.yml"
    base="./docker-compose.yml"
  else
    return 0
  fi
  # When ROOT absolute paths are used, prefer relative compose files from expected cwd.
  if [[ -n "$prefix" ]]; then
    printf '%s' "-f ${prefix}docker-compose.yml -f ${prefix}docker-compose.nvidia.yml"
  elif [[ -n "${ROOT:-}" && -f "$ROOT/infra/docker-compose.nvidia.yml" && ! -f ./docker-compose.nvidia.yml ]]; then
    # Called with ROOT set but cwd may be infra already via (cd "$ROOT/infra" && ...)
    printf '%s' "-f docker-compose.yml -f docker-compose.nvidia.yml"
  else
    printf '%s' "-f docker-compose.yml -f docker-compose.nvidia.yml"
  fi
}

ensure_nvidia_container_runtime() {
  if ! command -v docker >/dev/null 2>&1; then
    return 0
  fi
  if docker info 2>/dev/null | grep -qi 'Runtimes:.*nvidia'; then
    return 0
  fi
  if command -v nvidia-ctk >/dev/null 2>&1; then
    sudo nvidia-ctk runtime configure --runtime=docker >/dev/null 2>&1 || true
    echo "[WARN] nvidia runtime configured — restart dockerd if Frigate GPU fails"
  else
    echo "[WARN] nvidia-container-toolkit missing — Frigate may detect on CPU (ONNX)"
  fi
}
