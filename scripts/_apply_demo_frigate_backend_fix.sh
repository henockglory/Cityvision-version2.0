#!/usr/bin/env bash
set -euo pipefail
WIN=/mnt/c/Users/gheno/citevision
ROOT=~/citevision-v2
FILES=(
  backend/internal/frigate/sync.go
  backend/internal/frigate/compiler.go
  backend/internal/frigate/sync_test.go
  backend/internal/frigate/compiler_test.go
  backend/internal/camera/service.go
  backend/internal/demo/service.go
)
for f in "${FILES[@]}"; do
  cp "$WIN/$f" "$ROOT/$f"
  sed -i 's/\r$//' "$ROOT/$f"
done
cd "$ROOT/backend"
go test ./internal/frigate/... -count=1

python3 "$ROOT/scripts/_restart_frigate_demo.py"

KEY="${INTERNAL_SERVICE_KEY:-changeme_internal_service_key}"
echo "=== repair demo streams ==="
curl -sf -X POST "http://127.0.0.1:8081/api/v1/internal/demo/repair-streams" \
  -H "X-Internal-Key: $KEY" | python3 -m json.tool || true

echo "=== frigate rebuild ==="
curl -sf -X POST "http://127.0.0.1:8081/api/v1/internal/ingest/frigate/rebuild" \
  -H "X-Internal-Key: $KEY" -o /dev/null -w "rebuild_http=%{http_code}\n"

CFG="$ROOT/infra/frigate-config/config.yml"
echo "=== frigate config demo cameras ==="
grep -E 'cv_[0-9a-f-]+|demo-' "$CFG" | head -30 || true

echo "=== demo camera metadata (go2rtc_src) ==="
python3 - <<'PY'
import json, os, urllib.request
org = "74d51ead-97a7-4e41-a488-503a9b90c466"
req = urllib.request.Request(f"http://127.0.0.1:8081/api/v1/cameras?org_id={org}")
with urllib.request.urlopen(req, timeout=10) as r:
    cams = json.loads(r.read())
for c in cams:
    m = c.get("metadata") or {}
    if not m.get("demo"):
        continue
    print(c["name"][:40], "go2rtc_src=", m.get("go2rtc_src"), "demo_video_id=", m.get("demo_video_id"))
PY

echo "=== AI evidence env ==="
grep -E '^(EVIDENCE_BACKEND|FRIGATE_)' "$ROOT/.env" || true
