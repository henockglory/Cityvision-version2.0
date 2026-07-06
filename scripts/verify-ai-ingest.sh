#!/usr/bin/env bash
# Fail unless AI ingest frames are advancing (pipeline not frozen).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
AI_PORT="${AI_ENGINE_PORT:-8001}"
MIN_DELTA="${VERIFY_AI_MIN_FRAMES:-6}"
WINDOW="${VERIFY_AI_WINDOW_SEC:-20}"

frames_count() {
  curl -sf "http://127.0.0.1:${AI_PORT}/cameras" 2>/dev/null \
    | python3 -c "import sys,json; d=json.load(sys.stdin); c=d.get('cameras') or []; print(sum(int(x.get('frames_processed') or 0) for x in c))" 2>/dev/null \
    || echo 0
}

running_count() {
  curl -sf "http://127.0.0.1:${AI_PORT}/cameras" 2>/dev/null \
    | python3 -c "import sys,json; d=json.load(sys.stdin); print(sum(1 for x in (d.get('cameras') or []) if x.get('running')))" 2>/dev/null \
    || echo 0
}

if ! curl -sf "http://127.0.0.1:${AI_PORT}/health" >/dev/null 2>&1; then
  echo "[FAIL] AI health :${AI_PORT}" >&2
  exit 1
fi

rc="$(running_count)"
if [[ "$rc" -lt 1 ]]; then
  echo "[WARN] no running AI camera ingest yet (running=${rc}) — waiting orchestrator 20s"
  sleep 20
fi

f0="$(frames_count)"
sleep "$WINDOW"
f1="$(frames_count)"
delta=$((f1 - f0))
echo "[verify-ai-ingest] frames ${f0} -> ${f1} (delta=${delta} in ${WINDOW}s)"
if [[ "$delta" -lt "$MIN_DELTA" ]]; then
  echo "[FAIL] AI ingest not advancing (need >= ${MIN_DELTA} frames / ${WINDOW}s)" >&2
  exit 1
fi
echo "[OK] AI ingest advancing"
