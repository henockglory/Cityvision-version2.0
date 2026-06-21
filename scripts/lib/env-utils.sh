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
