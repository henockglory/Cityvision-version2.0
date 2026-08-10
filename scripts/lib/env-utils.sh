#!/usr/bin/env bash
# Shared env helpers for Linux/WSL scripts

load_dotenv() {
  local env_file="${1:-.env}"
  [[ -f "$env_file" ]] || return 0
  set -a
  # shellcheck disable=SC1090
  source <(sed 's/\r$//' "$env_file" | grep -v '^\s*#' | grep -v '^\s*$')
  set +a
}

# Force PROJECT_ROOT to the runtime tree (fixes Paramètres start_mode when .env points at another clone).
sync_project_root() {
  local root="${1:-.}"
  local env_path="$root/.env"
  [[ -f "$env_path" ]] || return 0
  sed -i 's/\r$//' "$env_path" 2>/dev/null || true
  if grep -q '^PROJECT_ROOT=' "$env_path" 2>/dev/null; then
    sed -i "s|^PROJECT_ROOT=.*|PROJECT_ROOT=${root}|" "$env_path" 2>/dev/null || true
  else
    echo "PROJECT_ROOT=${root}" >>"$env_path"
  fi
}

random_hex() {
  local bytes="${1:-16}"
  if command -v openssl >/dev/null 2>&1; then
    openssl rand -hex "$bytes"
  else
    head -c "$bytes" /dev/urandom | od -An -tx1 | tr -d ' \n'
  fi
}

ensure_env_file() {
  local root="${1:-.}"
  local env_path="$root/.env"
  local example_path="$root/.env.example"
  if [[ -f "$env_path" ]]; then
    sed -i 's/\r$//' "$env_path" 2>/dev/null || true
    echo "$env_path"
    return 0
  fi
  if [[ ! -f "$example_path" ]]; then
    echo "missing .env.example" >&2
    return 1
  fi
  cp "$example_path" "$env_path"
  local jwt audit cam
  jwt="$(random_hex 24)"
  audit="$(random_hex 24)"
  cam="$(random_hex 32)"
  sed -i "s/^JWT_SECRET=.*/JWT_SECRET=$jwt/" "$env_path"
  sed -i "s/^AUDIT_SIGNING_KEY=.*/AUDIT_SIGNING_KEY=$audit/" "$env_path"
  sed -i "s/^CAMERA_CREDENTIAL_KEY=.*/CAMERA_CREDENTIAL_KEY=$cam/" "$env_path"
  echo "[INFO] Created .env with generated secrets" >&2
  echo "$env_path"
}

_upsert_env_kv_file() {
  local env_path="$1" key="$2" val="$3"
  if grep -q "^${key}=" "$env_path" 2>/dev/null; then
    sed -i "s|^${key}=.*|${key}=${val}|" "$env_path"
  else
    echo "${key}=${val}" >>"$env_path"
  fi
}

# Demo / installer launch defaults — DEMO_MODE, Frigate, videos, rule catalog.
# Upserts keys so silent DEMO_MODE=0 / FRIGATE_*=0 cannot leave Health RED.
ensure_demo_runtime_env() {
  local root="${1:-.}"
  local env_path="${2:-$root/.env}"
  [[ -f "$env_path" ]] || return 1
  root="$(cd "$root" && pwd)"
  env_path="$(cd "$(dirname "$env_path")" && pwd)/$(basename "$env_path")"
  sed -i 's/\r$//' "$env_path" 2>/dev/null || true
  mkdir -p "$root/data/videos" "$root/shared/rule-catalog" 2>/dev/null || true
  local videos="$root/data/videos"
  local catalog="$root/shared/rule-catalog"
  local shared="$root/shared"

  _upsert_env_kv_file "$env_path" DEMO_MODE 1
  _upsert_env_kv_file "$env_path" VIDEOS_PATH "$videos"
  _upsert_env_kv_file "$env_path" RULE_CATALOG_PATH "$catalog"
  _upsert_env_kv_file "$env_path" SHARED_PATH "$shared"
  # Always allow live IP-cam ingest (RTSP/mp4/demo). Lab gate name is historical.
  _upsert_env_kv_file "$env_path" LIVE_108_ENABLED 1
  _upsert_env_kv_file "$env_path" FRIGATE_ENABLED 1
  _upsert_env_kv_file "$env_path" FRIGATE_LIVE 1
  _upsert_env_kv_file "$env_path" FRIGATE_EVIDENCE 1
  _upsert_env_kv_file "$env_path" FRIGATE_EVENTS 1
  _upsert_env_kv_file "$env_path" FRIGATE_CONFIG_SYNC 1
  _upsert_env_kv_file "$env_path" FRIGATE_URL "http://127.0.0.1:5000"
  _upsert_env_kv_file "$env_path" VITE_FRIGATE_ENABLED 1
  _upsert_env_kv_file "$env_path" VITE_FRIGATE_LIVE 1
  grep -q '^ALERT_EMAIL_TO=' "$env_path" 2>/dev/null \
    || echo 'ALERT_EMAIL_TO=demo@citevision.local' >>"$env_path"
  ensure_demo_validation_env "$root" "$env_path" || true
  echo "[INFO] Demo runtime env: DEMO_MODE=1 LIVE_108=1 Frigate=on VIDEOS_PATH=$videos" >&2
}

# Gemini + Frigate cabin bridges — permanent Demo5 profile (never overwrites GEMINI_API_KEY).
ensure_demo_validation_env() {
  local root="${1:-.}"
  local env_path="${2:-$root/.env}"
  [[ -f "$env_path" ]] || return 1
  root="$(cd "$root" && pwd)"
  env_path="$(cd "$(dirname "$env_path")" && pwd)/$(basename "$env_path")"
  sed -i 's/\r$//' "$env_path" 2>/dev/null || true

  local gemini_model="gemini-3.1-flash-lite"
  if grep -q '^GEMINI_MODEL=' "$env_path" 2>/dev/null; then
    gemini_model="$(grep '^GEMINI_MODEL=' "$env_path" | head -1 | cut -d= -f2- | tr -d ' "\r')"
    [[ -n "$gemini_model" ]] || gemini_model="gemini-3.1-flash-lite"
  fi

  _upsert_env_kv_file "$env_path" RED_LIGHT_GATE_MODE or
  _upsert_env_kv_file "$env_path" RED_LIGHT_POST_RED_GRACE_SEC 2.5
  # Permanent Gemini/VLM profile (WSL live lessons — never overwrites GEMINI_API_KEY).
  _upsert_env_kv_file "$env_path" GEMINI_QUEUE_SIZE 16
  _upsert_env_kv_file "$env_path" GEMINI_MIN_INTERVAL_SEC 5
  _upsert_env_kv_file "$env_path" GEMINI_TIMEOUT 90
  _upsert_env_kv_file "$env_path" GEMINI_FORCE_IPV4 1
  _upsert_env_kv_file "$env_path" GEMINI_MAX_AGE_SEC 120
  _upsert_env_kv_file "$env_path" GEMINI_MODEL "$gemini_model"
  _upsert_env_kv_file "$env_path" GEMINI_ENABLED 1
  _upsert_env_kv_file "$env_path" FRIGATE_VLM_BRIDGE 1
  _upsert_env_kv_file "$env_path" FRIGATE_SPEED_BRIDGE 1
  _upsert_env_kv_file "$env_path" FRIGATE_GEOMETRY_BRIDGE 1
  _upsert_env_kv_file "$env_path" FRIGATE_VLM_BRIDGE_CROP_MODE vehicle_bbox
  _upsert_env_kv_file "$env_path" FRIGATE_CABIN_DEDUPE_SEC 15
  _upsert_env_kv_file "$env_path" FRIGATE_CABIN_SIZE_GATE 0
  _upsert_env_kv_file "$env_path" RED_LIGHT_DEBUG_FORCE_ENQUEUE 0
  _upsert_env_kv_file "$env_path" GEMINI_SHADOW_MODE 0
  _upsert_env_kv_file "$env_path" FRIGATE_SPEED_EMIT_MODE exit

  if [[ -x "$root/scripts/ensure-rules-sync-env.sh" ]]; then
    bash "$root/scripts/ensure-rules-sync-env.sh" --resolve-org 2>/dev/null || true
  fi
  # Restore API key from ~/.citevision_gemini_key.tmp when .env key is empty.
  ensure_gemini_key_env "$root" "$env_path" 2>/dev/null || true
  echo "[INFO] Demo validation env: Gemini queue=16 timeout=90 ipv4=1 bridges=vlm+speed+geometry" >&2
}

ensure_frigate_paths_env() {
  local root="${1:-.}"
  local env_path="${2:-$root/.env}"
  [[ -f "$env_path" ]] || return 1
  root="$(cd "$root" && pwd)"
  _upsert_env_kv_file "$env_path" FRIGATE_CONFIG_PATH "$root/infra/frigate-config/config.yml"
  _upsert_env_kv_file "$env_path" FRIGATE_BASE_YAML "$root/infra/frigate.base.yaml"
  _upsert_env_kv_file "$env_path" FRIGATE_GENERATED_DIR "$root/infra/frigate-config"
  _upsert_env_kv_file "$env_path" PROJECT_ROOT "$root"
  if [[ -f "$root/backend/infra/frigate-config/config.yml" ]]; then
    cp -f "$root/backend/infra/frigate-config/config.yml" "$root/infra/frigate-config/config.yml" 2>/dev/null || true
  fi
}

ensure_gemini_key_env() {
  local root="${1:-.}"
  local env_path="${2:-$root/.env}"
  python3 - <<PY
from pathlib import Path
import os

root = Path(${root@Q} if False else "$root")
env_path = Path(${env_path@Q} if False else "$env_path")
root = Path("$root")
env_path = Path("$env_path")
text = env_path.read_text(encoding="utf-8") if env_path.exists() else ""
key = ""
for line in text.splitlines():
    if line.startswith("GEMINI_API_KEY="):
        key = line.split("=", 1)[1].strip().strip('"').strip("'")
        break
if len(key) >= 20:
    print("gemini_key=present")
    raise SystemExit(0)
kf = Path(os.environ.get("GEMINI_KEY_FILE", str(Path.home() / ".citevision_gemini_key.tmp")))
if kf.is_file():
    key = kf.read_text(encoding="utf-8").strip()
    if len(key) >= 20:
        lines, seen = text.splitlines(), False
        out = []
        for line in lines:
            if line.startswith("GEMINI_API_KEY="):
                out.append(f"GEMINI_API_KEY={key}")
                seen = True
            else:
                out.append(line)
        if not seen:
            out.append(f"GEMINI_API_KEY={key}")
        env_path.write_text("\n".join(out) + "\n", encoding="utf-8")
        print("gemini_key=restored_from_file")
        raise SystemExit(0)
print("gemini_key=MISSING")
raise SystemExit(1)
PY
}

wait_http_ok() {
  local url="$1"
  local timeout="${2:-60}"
  local i=0
  while (( i < timeout )); do
    if curl -sf "$url" >/dev/null 2>&1; then
      return 0
    fi
    sleep 2
    ((i += 2))
  done
  return 1
}

start_bg() {
  local name="$1"
  local workdir="$2"
  local cmd="$3"
  local logdir="$4"
  local env_file="${5:-}"
  mkdir -p "$logdir"
  logdir="$(cd "$logdir" && pwd)"
  local logfile="$logdir/${name}.log"
  local pidfile="$logdir/${name}.pid"
  local env_prefix=""
  if [[ -n "$env_file" && -f "$env_file" ]]; then
    env_prefix="set -a && source <(sed 's/\r$//' '$env_file' | grep -v '^\s*#' | grep -v '^\s*$') && set +a && "
  fi
  (
    cd "$workdir"
    setsid bash -c "${env_prefix}${cmd}" >>"$logfile" 2>&1 < /dev/null &
    echo $! >"$pidfile"
  )
  echo "[OK] Started $name PID $(cat "$pidfile") -> $logfile"
}

stop_from_pid() {
  local pidfile="$1"
  [[ -f "$pidfile" ]] || return 0
  local pid
  pid="$(cat "$pidfile")"
  if kill -0 "$pid" 2>/dev/null; then
    kill -- -"$pid" 2>/dev/null || kill "$pid" 2>/dev/null || true
    echo "[OK] Stopped PID $pid"
  fi
  rm -f "$pidfile"
}

free_port() {
  for port in "$@"; do
    if command -v fuser >/dev/null 2>&1; then
      fuser -k "${port}/tcp" 2>/dev/null || true
    fi
    if command -v lsof >/dev/null 2>&1; then
      local pids
      pids="$(lsof -ti "tcp:${port}" 2>/dev/null || true)"
      if [[ -n "$pids" ]]; then
        kill -9 $pids 2>/dev/null || true
      fi
    fi
    if command -v ss >/dev/null 2>&1; then
      local pids
      pids="$(ss -tlnp 2>/dev/null | grep ":${port} " | sed -n 's/.*pid=\([0-9]*\).*/\1/p' | sort -u || true)"
      for pid in $pids; do
        kill -9 "$pid" 2>/dev/null || true
      done
    fi
  done
}

wait_service_with_retry() {
  local name="$1"
  local url="$2"
  local pidfile="$3"
  local start_cmd="$4"
  local workdir="$5"
  local logdir="$6"
  local env_file="${7:-}"
  local timeout="${8:-120}"
  local rounds="${9:-2}"
  local round=1
  while (( round <= rounds )); do
    if wait_http_ok "$url" "$timeout"; then
      echo "[OK] $name healthy"
      return 0
    fi
    if (( round < rounds )); then
      echo "[FIX] $name timeout — restart (round $round/$rounds)…"
      stop_from_pid "$pidfile"
      free_port "$(echo "$url" | sed -n 's/.*:\([0-9]*\)\/.*/\1/p')"
      sleep 2
      start_bg "$name" "$workdir" "$start_cmd" "$logdir" "$env_file"
      sleep 3
    fi
    ((round++)) || true
  done
  echo "[FAIL] $name not healthy after $rounds attempts — see logs/${name}.log" >&2
  return 1
}

# True when node_modules contains native Rollup bindings for this OS (WSL/Linux vs Windows).
frontend_rollup_native_ok() {
  local root="${1:-.}"
  local nm="$root/frontend/node_modules"
  [[ -d "$nm" ]] || return 1
  if [[ "$(uname -s)" == "Linux" ]]; then
    [[ -d "$nm/@rollup/rollup-linux-x64-gnu" ]] || [[ -d "$nm/@rollup/rollup-linux-x64-musl" ]]
    return
  fi
  [[ -d "$nm/@rollup/rollup-win32-x64-msvc" ]] || [[ -d "$nm/@rollup/rollup-win32-x64-gnu" ]]
}

# Reinstall frontend deps when node_modules was built on another OS (common: npm on Windows, Vite in WSL).
ensure_frontend_deps() {
  local root="${1:-.}"
  if frontend_rollup_native_ok "$root"; then
    return 0
  fi
  echo "[FIX] Frontend node_modules incompatible avec $(uname -s) — réinstallation npm…" >&2
  rm -rf "$root/frontend/node_modules"
  if ! (cd "$root/frontend" && npm install --silent); then
    echo "[FAIL] npm install frontend échoué" >&2
    return 1
  fi
  if frontend_rollup_native_ok "$root"; then
    echo "[OK] Frontend dependencies ready ($(uname -s))"
    return 0
  fi
  echo "[FAIL] Bindings Rollup natifs toujours absents après npm install" >&2
  return 1
}

is_wsl() {
  grep -qi microsoft /proc/version 2>/dev/null
}

has_native_docker_engine() {
  command -v dockerd >/dev/null 2>&1
}

# Installe Docker Engine natif (docker-ce) — jamais Docker Desktop.
install_docker_engine_native() {
  if has_native_docker_engine; then
    return 0
  fi
  if ! command -v apt-get >/dev/null 2>&1; then
    echo "[ERR] apt-get requis pour installer Docker Engine natif" >&2
    return 1
  fi
  echo "[INFO] Installation Docker Engine natif (docker-ce)…"
  echo "[INFO] 2–5 min — patientez, ce n'est pas un blocage."
  sudo install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
    | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg 2>/dev/null || true
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
    | sudo tee /etc/apt/sources.list.d/docker.list >/dev/null
  sudo apt-get update -qq
  sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq \
    docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
  sudo usermod -aG docker "${USER:-$(whoami)}" 2>/dev/null || true
  has_native_docker_engine
}

start_docker_daemon_native() {
  if docker info >/dev/null 2>&1; then
    return 0
  fi
  if pgrep -x dockerd >/dev/null 2>&1; then
    return 0
  fi

  sudo mkdir -p /var/run/docker /etc/docker 2>/dev/null || true

  if command -v systemctl >/dev/null 2>&1 \
    && systemctl list-unit-files docker.service 2>/dev/null | grep -q docker.service; then
    echo "[INFO] Démarrage Docker via systemctl…"
    sudo systemctl start docker 2>/dev/null && return 0
  fi

  if [[ -x /etc/init.d/docker ]] || [[ -f /lib/systemd/system/docker.service ]]; then
    echo "[INFO] Démarrage Docker via service docker…"
    sudo service docker start 2>/dev/null && return 0
  fi

  if has_native_docker_engine; then
    local log="${CITEVISION_LOGDIR:-$HOME/citevision-v2/logs}/dockerd.log"
    mkdir -p "$(dirname "$log")" 2>/dev/null || true
    echo "[INFO] Démarrage dockerd (Docker Engine natif WSL, sans systemd)…"
    sudo nohup dockerd --host=unix:///var/run/docker.sock >>"$log" 2>&1 &
    disown 2>/dev/null || true
    return 0
  fi

  return 1
}

# Attend le daemon Docker. WSL = Docker Engine natif uniquement (pas Docker Desktop).
# Usage: ensure_docker_ready [timeout_sec] [install]
ensure_docker_ready() {
  local max_wait="${1:-90}"
  local do_install="${2:-}"

  if docker info >/dev/null 2>&1; then
    echo "[OK] Docker ready"
    return 0
  fi

  if is_wsl; then
    echo "[INFO] Docker daemon absent — démarrage Docker Engine natif (WSL)…"
  else
    echo "[INFO] Docker daemon absent — démarrage Docker Engine…"
  fi
  echo "[INFO] Peut prendre 15–90 s ; les […] confirment que ça avance."

  if ! has_native_docker_engine; then
    if [[ "$do_install" == "install" ]]; then
      install_docker_engine_native || true
    else
      echo "[ERR] dockerd introuvable — Docker Engine natif non installé." >&2
      echo "       Lancez: bash scripts/setup-wsl.sh" >&2
      return 1
    fi
  fi

  if ! start_docker_daemon_native; then
    echo "[ERR] Impossible de démarrer dockerd." >&2
    return 1
  fi

  local i=0
  while (( i < max_wait )); do
    if docker info >/dev/null 2>&1; then
      echo "[OK] Docker ready"
      return 0
    fi
    if (( i > 0 && i % 15 == 0 )); then
      echo "[…]   toujours en cours: attente Docker Engine natif (${i}s/${max_wait}s)…"
    fi
    sleep 3
    ((i += 3)) || true
  done

  echo "[FAIL] Docker Engine natif non joignable après ${max_wait}s." >&2
  if is_wsl; then
    echo "       Vérifiez: bash scripts/setup-wsl.sh  puis  newgrp docker" >&2
    echo "       Logs dockerd: ${CITEVISION_LOGDIR:-/tmp}/dockerd.log" >&2
  else
    echo "       Run: sudo systemctl start docker (ou sudo service docker start)" >&2
  fi
  return 1
}
