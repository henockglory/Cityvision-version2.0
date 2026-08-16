#!/usr/bin/env bash
# Restart AI if evidence Python on disk is newer than the running process
# (copy_one refreshes src without reloading uvicorn).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
# shellcheck source=scripts/lib/env-utils.sh
source "$ROOT/scripts/lib/env-utils.sh" 2>/dev/null || true

SRC="$ROOT/ai-engine/src/citevision_ai/evidence/frigate_track_evidence.py"
PIDFILE="$ROOT/logs/ai-engine.pid"
AI_PORT="${AI_ENGINE_PORT:-8001}"

if [[ ! -f "$SRC" ]]; then
  echo "[INFO] evidence src missing — skip AI freshness"
  exit 0
fi
if ! curl -sf --max-time 3 "http://127.0.0.1:${AI_PORT}/health" >/dev/null 2>&1; then
  echo "[INFO] AI not up — skip freshness (start path will launch it)"
  exit 0
fi

src_m=$(stat -c %Y "$SRC" 2>/dev/null || echo 0)
pid=""
[[ -f "$PIDFILE" ]] && pid="$(tr -d '[:space:]' < "$PIDFILE" || true)"
proc_m=0
if [[ -n "$pid" && -d "/proc/$pid" ]]; then
  proc_m=$(stat -c %Y "/proc/$pid" 2>/dev/null || echo 0)
fi
if [[ "$proc_m" -eq 0 ]]; then
  echo "[INFO] AI pid unknown — skip freshness"
  exit 0
fi
if [[ "$src_m" -le "$proc_m" ]]; then
  echo "[OK] AI process newer than evidence src"
  exit 0
fi

echo "[INFO] evidence src newer than AI process — restart-ai-engine"
if [[ -x "$ROOT/scripts/restart-ai-engine.sh" ]]; then
  bash "$ROOT/scripts/restart-ai-engine.sh" || true
else
  echo "[WARN] restart-ai-engine.sh missing"
fi
