#!/usr/bin/env bash
# Heartbeat + messages explicites pour les étapes d'install longues (WSL /mnt/c).
# Usage: source scripts/lib/install-progress.sh

log_slow_step() {
  local msg="$1"
  local hint="${2:-}"
  echo "==> $msg"
  if [[ -n "$hint" ]]; then
    echo "[INFO] $hint"
  fi
}

# run_with_heartbeat INTERVAL_SEC LABEL CMD...
# Affiche un message toutes les INTERVAL_SEC secondes pendant CMD.
run_with_heartbeat() {
  local interval="$1"
  local label="$2"
  shift 2
  local hb_pid=""
  (
    while sleep "$interval"; do
      echo "[…]   toujours en cours: $label ($(date +%H:%M:%S)) — patientez, l'installation avance"
    done
  ) &
  hb_pid=$!
  local rc=0
  "$@" || rc=$?
  kill "$hb_pid" 2>/dev/null || true
  wait "$hb_pid" 2>/dev/null || true
  return "$rc"
}

sync_secondary_from_runtime() {
  local root="${1:-.}"
  local dest="$root/ai-engine/models/secondary"
  mkdir -p "$dest"
  local src file
  for src in \
    "$HOME/citevision-v2/ai-engine/models/secondary" \
    "/mnt/c/Users/gheno/citevision-v2/ai-engine/models/secondary"; do
    [[ -d "$src" ]] || continue
    for file in "$src"/*.onnx; do
      [[ -f "$file" ]] || continue
      local base
      base="$(basename "$file")"
      if [[ ! -f "$dest/$base" ]] || [[ "$(stat -c%s "$dest/$base" 2>/dev/null || echo 0)" -lt 5000 ]]; then
        cp -f "$file" "$dest/$base"
        echo "[OK] synced $base from $src"
      fi
    done
  done
}
