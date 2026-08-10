#!/usr/bin/env bash
# Lightweight service heal — backend / AI / rules-engine + published Docker ports.
# Permanent ops path (sourced by health_check_all / start-full-stack / watch-infra-ports).
# Do NOT set -e/-o pipefail here: when sourced, pipefail breaks health_check pgrep|wc pipelines.
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  set -uo pipefail
fi

ROOT="${CITEVISION_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
API="${BACKEND_API_URL:-http://127.0.0.1:8081}"
AI="${AI_URL:-http://127.0.0.1:8001}"
RULES_PORT="${RULES_ENGINE_PORT:-8010}"

# Prefer free_port from env-utils when already sourced.
if ! declare -F free_port >/dev/null 2>&1; then
  # shellcheck source=scripts/lib/env-utils.sh
  source "$ROOT/scripts/lib/env-utils.sh" 2>/dev/null || true
fi

tcp_ok() {
  local host="${1:-127.0.0.1}"
  local port="${2:-}"
  [[ -n "$port" ]] || return 1
  if command -v nc >/dev/null 2>&1; then
    nc -z -w 2 "$host" "$port" >/dev/null 2>&1 && return 0
  fi
  (echo >/dev/tcp/"$host"/"$port") >/dev/null 2>&1
}

# Restart a published container and wait until host TCP ports answer.
# Usage: heal_published_container citevision-v2-redis 6380
# Optional compose service name as 2nd arg if different: heal_published_container NAME [compose_svc] PORTS...
heal_published_container() {
  local name="$1"
  shift
  local compose_svc=""
  local ports=()
  if [[ "${1:-}" =~ ^[A-Za-z] ]] && ! [[ "${1:-}" =~ ^[0-9]+$ ]]; then
    compose_svc="$1"
    shift
  fi
  ports=("$@")
  [[ -n "$name" ]] || return 1
  [[ ${#ports[@]} -gt 0 ]] || return 1

  local env_file="${ENV_FILE:-$ROOT/.env}"
  echo "[INFO] heal published $name ports=${ports[*]}"
  # Prefer start/restart WITHOUT free_port first — free_port can kill docker-proxy
  # and leave the container "running" with a dead host publish.
  docker start "$name" >/dev/null 2>&1 || true
  docker restart "$name" >/dev/null 2>&1 || true
  local i p ok=0
  for i in $(seq 1 12); do
    ok=1
    for p in "${ports[@]}"; do
      tcp_ok 127.0.0.1 "$p" || ok=0
    done
    [[ "$ok" -eq 1 ]] && return 0
    sleep 1
  done
  # Recreate via compose when restart did not restore docker-proxy.
  if [[ -f "$ROOT/infra/docker-compose.yml" ]]; then
    local svc="${compose_svc:-}"
    if [[ -z "$svc" ]]; then
      case "$name" in
        citevision-v2-redis) svc=redis ;;
        citevision-v2-mosquitto) svc=mosquitto ;;
        citevision-v2-postgres) svc=postgres ;;
        citevision-v2-minio) svc=minio ;;
        citevision-v2-ocr|citevision-ocr) svc=citevision-ocr ;;
        citevision-v2-mailhog) svc=mailhog ;;
        citevision-v2-go2rtc) svc=go2rtc ;;
        *) svc="" ;;
      esac
    fi
    if [[ -n "$svc" ]]; then
      docker rm -f "$name" 2>/dev/null || true
      if declare -F free_port >/dev/null 2>&1; then
        free_port "${ports[@]}" 2>/dev/null || true
      fi
      (cd "$ROOT/infra" && docker compose --env-file "$env_file" --profile ocr --profile frigate up -d "$svc") >/dev/null 2>&1 || \
        (cd "$ROOT/infra" && docker compose --env-file "$env_file" up -d "$svc") >/dev/null 2>&1 || true
      for i in $(seq 1 20); do
        ok=1
        for p in "${ports[@]}"; do
          tcp_ok 127.0.0.1 "$p" || ok=0
        done
        [[ "$ok" -eq 1 ]] && return 0
        sleep 1
      done
    fi
  fi
  return 1
}

# Ensure infra host publishes that apps use (Redis session, MQTT, Postgres, MinIO, OCR).
# Echoes OK/FAIL lines; returns 0 only if all required ports are up (after heal).
ensure_infra_host_ports() {
  local redis_port="${REDIS_PORT:-6380}"
  local mqtt_port="${MQTT_PORT:-1884}"
  local pg_port="${POSTGRES_PORT:-5433}"
  local minio_port="${MINIO_API_PORT:-9003}"
  local ocr_port="${OCR_PORT:-8181}"
  local mailhog_ui="${MAILHOG_UI_PORT:-8025}"
  local rc=0

  # Redis — host TCP is mandatory (docker exec ping alone is insufficient).
  if tcp_ok 127.0.0.1 "$redis_port"; then
    echo "[OK] redis host :${redis_port}"
  else
    echo "[WARN] redis host :${redis_port} dead — heal"
    if heal_published_container citevision-v2-redis redis "$redis_port" && tcp_ok 127.0.0.1 "$redis_port"; then
      echo "[OK] redis host :${redis_port} after heal"
    else
      echo "[FAIL] redis host :${redis_port} still dead"
      rc=1
    fi
  fi

  if tcp_ok 127.0.0.1 "$mqtt_port"; then
    echo "[OK] mosquitto host :${mqtt_port}"
  else
    echo "[WARN] mosquitto host :${mqtt_port} dead — heal"
    if heal_published_container citevision-v2-mosquitto mosquitto "$mqtt_port" && tcp_ok 127.0.0.1 "$mqtt_port"; then
      echo "[OK] mosquitto host :${mqtt_port} after heal"
    else
      echo "[FAIL] mosquitto host :${mqtt_port} still dead"
      rc=1
    fi
  fi

  if tcp_ok 127.0.0.1 "$pg_port"; then
    echo "[OK] postgres host :${pg_port}"
  else
    echo "[WARN] postgres host :${pg_port} dead — heal"
    if heal_published_container citevision-v2-postgres postgres "$pg_port" && tcp_ok 127.0.0.1 "$pg_port"; then
      echo "[OK] postgres host :${pg_port} after heal"
    else
      echo "[FAIL] postgres host :${pg_port} still dead"
      rc=1
    fi
  fi

  if curl -sf --max-time 3 "http://127.0.0.1:${minio_port}/minio/health/live" >/dev/null 2>&1 \
    || tcp_ok 127.0.0.1 "$minio_port"; then
    echo "[OK] minio host :${minio_port}"
  else
    echo "[WARN] minio host :${minio_port} dead — heal"
    if heal_published_container citevision-v2-minio minio "$minio_port" \
      && { curl -sf --max-time 3 "http://127.0.0.1:${minio_port}/minio/health/live" >/dev/null 2>&1 || tcp_ok 127.0.0.1 "$minio_port"; }; then
      echo "[OK] minio host :${minio_port} after heal"
    else
      echo "[FAIL] minio host :${minio_port} still dead"
      rc=1
    fi
  fi

  if curl -sf --max-time 3 "http://127.0.0.1:${ocr_port}/healthz" >/dev/null 2>&1; then
    echo "[OK] ocr host :${ocr_port}"
  else
    echo "[WARN] ocr host :${ocr_port} dead — heal"
    if heal_published_container citevision-v2-ocr citevision-ocr "$ocr_port" \
      && curl -sf --max-time 5 "http://127.0.0.1:${ocr_port}/healthz" >/dev/null 2>&1; then
      echo "[OK] ocr host :${ocr_port} after heal"
    else
      echo "[FAIL] ocr host :${ocr_port} still dead"
      rc=1
    fi
  fi

  if curl -sf --max-time 3 "http://127.0.0.1:${mailhog_ui}/" >/dev/null 2>&1; then
    echo "[OK] mailhog host :${mailhog_ui}"
  else
    echo "[WARN] mailhog host :${mailhog_ui} dead — heal"
    if heal_published_container citevision-v2-mailhog mailhog "$mailhog_ui" 1025 \
      && curl -sf --max-time 5 "http://127.0.0.1:${mailhog_ui}/" >/dev/null 2>&1; then
      echo "[OK] mailhog host :${mailhog_ui} after heal"
    else
      echo "[FAIL] mailhog host :${mailhog_ui} still dead"
      rc=1
    fi
  fi

  # go2rtc — live preview for ALL cameras (demo + IP). Dead :1984 = black players everywhere.
  if curl -sf --max-time 3 "http://127.0.0.1:1984/api" >/dev/null 2>&1; then
    echo "[OK] go2rtc host :1984"
  else
    echo "[WARN] go2rtc host :1984 dead — heal"
    if heal_published_container citevision-v2-go2rtc go2rtc 1984 8554 8555 \
      && curl -sf --max-time 5 "http://127.0.0.1:1984/api" >/dev/null 2>&1; then
      echo "[OK] go2rtc host :1984 after heal"
    else
      echo "[FAIL] go2rtc host :1984 still dead"
      rc=1
    fi
  fi

  return "$rc"
}

restart_ai_engine() {
  local i
  if [[ -f "$ROOT/scripts/_restart_ai.py" ]]; then
    python3 "$ROOT/scripts/_restart_ai.py" || return 1
  else
    bash "$ROOT/scripts/run-ai-engine.sh" >/dev/null 2>&1 &
  fi
  for i in $(seq 1 20); do
    curl -sf -m 8 "$AI/health" >/dev/null && return 0
    sleep 3
  done
  return 1
}

ensure_backend_up() {
  local wait_sec="${1:-30}"
  local i=0
  while (( i < wait_sec )); do
    if curl -sf -m 5 "$API/health" >/dev/null 2>&1 \
      || curl -sf -m 5 "$API/api/v1/health" >/dev/null 2>&1; then
      return 0
    fi
    if (( i == 0 )) && [[ -f "$ROOT/scripts/_restart_backend.sh" ]]; then
      bash "$ROOT/scripts/_restart_backend.sh" >/dev/null 2>&1 || true
    fi
    sleep 2
    ((i += 2)) || true
  done
  return 1
}

ensure_ai_up() {
  curl -sf -m 8 "$AI/health" >/dev/null && return 0
  restart_ai_engine
}

ensure_rules_engine_up() {
  if curl -sf -m 8 "http://127.0.0.1:${RULES_PORT}/health" >/dev/null 2>&1; then
    return 0
  fi
  if [[ -f "$ROOT/scripts/_start-rules-engine.sh" ]]; then
    bash "$ROOT/scripts/_start-rules-engine.sh" >/dev/null 2>&1 || true
    sleep 5
  fi
  curl -sf -m 8 "http://127.0.0.1:${RULES_PORT}/health" >/dev/null 2>&1
}

ensure_services_healthy() {
  local ok=0
  ensure_backend_up 30 || ok=1
  ensure_ai_up || ok=1
  ensure_rules_engine_up || ok=1
  return "$ok"
}
