#!/usr/bin/env bash
set -euo pipefail
export PATH="/usr/local/go/bin:/usr/bin:/bin:${PATH:-}"

WIN=/mnt/c/Users/gheno/citevision
ROOT="$HOME/citevision-v2"
KEY="${INTERNAL_SERVICE_KEY:-changeme_internal_service_key}"

FILES=(
  backend/internal/frigate/sync.go
  backend/internal/frigate/compiler.go
  backend/internal/frigate/sync_test.go
  backend/internal/frigate/compiler_test.go
  backend/internal/camera/service.go
  backend/internal/demo/service.go
)

echo "=== sync backend fixes ==="
for f in "${FILES[@]}"; do
  cp "$WIN/$f" "$ROOT/$f"
  perl -pi -e 's/\x0d$//' "$ROOT/$f"
done

cd "$ROOT/backend"
go test ./internal/frigate/... -count=1
go build -o bin/citevision-api ./cmd/api

echo "=== restart backend ==="
pkill -f citevision-api 2>/dev/null || true
pkill -f 'go run ./cmd/api' 2>/dev/null || true
sleep 2
set -a
# shellcheck disable=SC1091
source "$ROOT/.env"
set +a
nohup "$ROOT/backend/bin/citevision-api" >>"$ROOT/logs/backend.log" 2>&1 &
echo $! >"$ROOT/logs/backend.pid"
for i in $(seq 1 25); do
  if curl -sf http://127.0.0.1:8081/health >/dev/null; then
    echo "backend up"
    break
  fi
  sleep 2
done
curl -sf http://127.0.0.1:8081/health >/dev/null || { echo "backend failed"; exit 1; }

echo "=== repair demo streams + camera metadata ==="
curl -sf -X POST "http://127.0.0.1:8081/api/v1/internal/demo/repair-streams" \
  -H "X-Internal-Key: $KEY" | python3 -m json.tool

echo "=== frigate rebuild ==="
curl -sf -X POST "http://127.0.0.1:8081/api/v1/internal/ingest/frigate/rebuild" \
  -H "X-Internal-Key: $KEY" -o /tmp/frigate_rebuild.json -w "http=%{http_code}\n"
python3 -m json.tool /tmp/frigate_rebuild.json 2>/dev/null || cat /tmp/frigate_rebuild.json

CFG="$ROOT/infra/frigate-config/config.yml"
echo "=== frigate config cameras ==="
grep -E '^  cv_' "$CFG" || true

echo "=== demo camera metadata ==="
python3 - <<'PY'
import json, urllib.request
org = "74d51ead-97a7-4e41-a488-503a9b90c466"
with urllib.request.urlopen(f"http://127.0.0.1:8081/api/v1/cameras?org_id={org}", timeout=15) as r:
    cams = json.loads(r.read())
for c in cams:
    m = c.get("metadata") or {}
    if not m.get("demo"):
        continue
    print(c["name"][:45], "| go2rtc_src=", m.get("go2rtc_src"), "| video=", m.get("demo_video_id", "")[:8])
PY

echo "=== restart frigate container ==="
docker restart citevision-v2-frigate >/dev/null
sleep 15

echo "=== restart AI ==="
python3 "$ROOT/scripts/_restart_ai.py"

echo "=== evidence env ==="
grep -E '^(EVIDENCE_BACKEND|FRIGATE_)' "$ROOT/.env" || true

echo "=== frigate health ==="
curl -sf http://127.0.0.1:8081/health/frigate | python3 -m json.tool || true

echo "[DONE] demo Frigate fix deployed"
