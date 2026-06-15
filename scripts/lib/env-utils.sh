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
