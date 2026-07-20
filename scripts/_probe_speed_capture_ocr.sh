#!/usr/bin/env bash
set -uo pipefail
ROOT=/home/gheno/citevision-v2
ORG=74d51ead-97a7-4e41-a488-503a9b90c466
CAM=55694d53-8f58-4981-91b2-7c6cd528a25d
source "$ROOT/scripts/lib/env-utils.sh"
load_dotenv "$(ensure_env_file "$ROOT")"
KEY="${INTERNAL_API_KEY:-changeme_internal_service_key}"

echo "=== OCR env ==="
grep -E 'OCR_|ocr_' "$ROOT/.env" | head -15
curl -sf --max-time 3 "${OCR_URL:-http://127.0.0.1:8099}/health" 2>/dev/null | head -c 200 || echo OCR_DOWN

echo "=== rule evidence policy ==="
docker exec citevision-v2-postgres psql -U citevision -d citevision -t -A -c \
"SELECT left(definition::text, 800) FROM rules WHERE id='9e66ecfa-c91f-495f-b314-f7cbd16bc372'::uuid;" | python3 -c '
import json,sys,re
s=sys.stdin.read()
# try parse as json blob
try:
  d=json.loads(s)
except Exception:
  print(s[:500]); raise SystemExit
ev=d.get("evidence") or {}
print("enabled", ev.get("enabled"), "clip", ev.get("clip_seconds"))
print("images", ev.get("images"))
'

echo "=== probe capture response ==="
# Build minimal event body matching EvidenceCaptureRequest
curl -sS -X POST "http://127.0.0.1:8001/cameras/$CAM/evidence/capture" \
  -H 'Content-Type: application/json' \
  -d "{\"org_id\":\"$ORG\",\"event\":{\"event_type\":\"speeding\",\"event_id\":\"probe-$(date +%s)\",\"camera_id\":\"$CAM\",\"confidence\":0.9,\"bbox\":{\"x\":0.4,\"y\":0.3,\"width\":0.2,\"height\":0.25},\"bbox_ts\":$(date +%s)}}" \
  -o /tmp/cap_probe.json -w "http=%{http_code}\n"
python3 - <<'PY'
import json
from pathlib import Path
p=Path("/tmp/cap_probe.json")
print("size", p.stat().st_size)
d=json.loads(p.read_text())
print("keys", list(d.keys())[:20])
print("evidence_status", d.get("evidence_status") or d.get("status"))
print("abort", d.get("abort_reason") or (d.get("meta") or {}).get("abort_reason"))
pkg=d.get("package") or d
meta=(pkg.get("metadata") if isinstance(pkg,dict) else {}) or d.get("meta") or {}
print("capture_source", meta.get("capture_source") if isinstance(meta,dict) else None)
print("missing_roles", meta.get("missing_roles") if isinstance(meta,dict) else None)
print("plate_status", meta.get("plate_status") if isinstance(meta,dict) else None)
imgs=pkg.get("images") if isinstance(pkg,dict) else None
if isinstance(imgs,list):
  print("roles", [i.get("role") for i in imgs if isinstance(i,dict)])
clip=pkg.get("clip") if isinstance(pkg,dict) else None
print("clip", bool(clip))
print("raw_head", p.read_text()[:600])
PY
