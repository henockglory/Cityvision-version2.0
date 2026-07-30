#!/usr/bin/env bash
set -euo pipefail
ROOT=/home/gheno/citevision-v2
echo "=== TABLES ==="
docker exec citevision-v2-postgres psql -U citevision -d citevision -c "\dt *.*" 2>&1 | head -60
echo "=== SCHEMAS ==="
docker exec citevision-v2-postgres psql -U citevision -d citevision -c "\dn" 2>&1
echo "=== PROCS ==="
pgrep -af "uvicorn|rules-engine|backend|api" | grep -v grep | head -20 || true
echo "=== FRIGATE ==="
sleep 15
curl -sf -m 5 http://127.0.0.1:5000/api/stats 2>&1 | python3 -c "import sys,json; d=json.load(sys.stdin); print(list((d.get('cameras') or {}).keys())[:8])" || echo frigate_not_ready
echo "=== RESTART AI ==="
bash "$ROOT/scripts/_quick_restart_ai.sh"
sleep 10
curl -sf http://127.0.0.1:8001/health | head -c 120; echo
# backend / rules if helpers exist
if [[ -x "$ROOT/scripts/_quick_restart_backend.sh" ]]; then bash "$ROOT/scripts/_quick_restart_backend.sh" || true; fi
if [[ -x "$ROOT/scripts/_quick_restart_rules.sh" ]]; then bash "$ROOT/scripts/_quick_restart_rules.sh" || true; fi
ls "$ROOT/scripts/"*restart* 2>/dev/null | head -20
