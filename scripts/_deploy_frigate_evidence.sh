#!/usr/bin/env bash
set -euo pipefail
WIN=/mnt/c/Users/gheno/citevision
ROOT=~/citevision-v2
cp "$WIN/ai-engine/src/citevision_ai/evidence/frigate_backend.py" "$ROOT/ai-engine/src/citevision_ai/evidence/frigate_backend.py"
cp "$WIN/frontend/src/components/evidence/EvidenceViewer.tsx" "$ROOT/frontend/src/components/evidence/EvidenceViewer.tsx"
cp "$WIN/scripts/_enable_frigate_env.py" "$ROOT/scripts/"
python3 "$ROOT/scripts/_enable_frigate_env.py" "$ROOT"
grep -E 'EVIDENCE_BACKEND|FRIGATE_EVIDENCE' "$ROOT/.env"
cd "$ROOT/ai-engine" && .venv/bin/python -m pytest tests/test_frigate_backend.py -q
source "$ROOT/scripts/lib/env-utils.sh"
stop_from_pid "$ROOT/logs/ai-engine.pid" 2>/dev/null || true
pkill -f 'uvicorn citevision_ai.main' 2>/dev/null || true
free_port 8001 2>/dev/null || true
sleep 2
start_bg ai-engine "$ROOT/ai-engine" ".venv/bin/uvicorn citevision_ai.main:app --host 0.0.0.0 --port 8001" "$ROOT/logs" "$ROOT/.env"
sleep 8
curl -sf http://127.0.0.1:8001/health | head -c 200 && echo
stop_from_pid "$ROOT/logs/frontend.pid" 2>/dev/null || true
pkill -f 'vite --host' 2>/dev/null || true
free_port 5174 2>/dev/null || true
sleep 2
start_bg frontend "$ROOT/frontend" "npm run dev -- --host 0.0.0.0 --port 5174 --strictPort" "$ROOT/logs" "$ROOT/.env"
sleep 10
echo DEPLOY_OK
