#!/usr/bin/env bash
set -uo pipefail
ROOT=/home/gheno/citevision-v2
cd "$ROOT"

# Ensure OCR_URL in .env
if ! grep -q '^OCR_URL=' "$ROOT/.env" 2>/dev/null; then
  echo 'OCR_URL=http://127.0.0.1:8181/ocr' >> "$ROOT/.env"
  echo "appended OCR_URL"
else
  # normalize to local ocr service
  sed -i 's|^OCR_URL=.*|OCR_URL=http://127.0.0.1:8181/ocr|' "$ROOT/.env"
fi
grep '^OCR_URL=' "$ROOT/.env"

echo "=== start OCR ==="
cd "$ROOT/infra"
docker compose --env-file "$ROOT/.env" --profile ocr up -d citevision-ocr
echo "waiting OCR healthz (first start may download models)..."
for i in $(seq 1 60); do
  if curl -sf --max-time 5 http://127.0.0.1:8181/healthz >/dev/null; then
    echo "OCR up after ${i}x5s"
    curl -sf http://127.0.0.1:8181/healthz; echo
    break
  fi
  sleep 5
done
curl -sf http://127.0.0.1:8181/healthz || { echo OCR_STILL_DOWN; docker logs citevision-v2-ocr --tail 40; exit 1; }

# Restart AI to pick OCR_URL
cd "$ROOT"
python3 scripts/_restart_ai.py || true

source scripts/lib/env-utils.sh
load_dotenv "$(ensure_env_file "$ROOT")"
KEY="${INTERNAL_API_KEY:-changeme_internal_service_key}"
curl -sf -X POST http://127.0.0.1:8081/api/v1/internal/ingest/resync-spatial -H "X-Internal-Key: $KEY" || true
echo

# Vite
if ! curl -sf --max-time 2 http://127.0.0.1:5174/ >/dev/null; then
  cd "$ROOT/frontend"
  nohup npm run dev -- --host 127.0.0.1 --port 5174 > /tmp/citevision-vite.log 2>&1 &
  sleep 3
fi

# Kill stuck speeding validate
pkill -f 'validate_rule_dod.py --alias speeding' 2>/dev/null || true
pkill -f '_validate_rule_frigate_1hit' 2>/dev/null || true
pkill -f '_validate_speeding_now' 2>/dev/null || true
sleep 2

# Quick capture probe for plate
CAM=55694d53-8f58-4981-91b2-7c6cd528a25d
ORG=74d51ead-97a7-4e41-a488-503a9b90c466
sleep 10
curl -sS -X POST "http://127.0.0.1:8001/cameras/$CAM/evidence/capture" \
  -H 'Content-Type: application/json' \
  -d "{\"org_id\":\"$ORG\",\"event\":{\"event_type\":\"speeding\",\"event_id\":\"ocr-probe-$(date +%s)\",\"camera_id\":\"$CAM\",\"confidence\":0.9,\"bbox\":{\"x\":0.4,\"y\":0.3,\"width\":0.2,\"height\":0.25},\"bbox_ts\":$(date +%s)}}" \
  -o /tmp/cap_ocr.json -w "http=%{http_code}\n"
python3 - <<'PY'
import json
d=json.load(open("/tmp/cap_ocr.json"))
pkg=d.get("package") or {}
meta=pkg.get("metadata") or d.get("meta") or {}
print("status", d.get("evidence_status"), "missing", meta.get("missing_roles"), "plate_status", meta.get("plate_status"))
print("roles", [i.get("role") for i in (pkg.get("images") or [])])
print("plate_number", meta.get("plate_number"))
PY
