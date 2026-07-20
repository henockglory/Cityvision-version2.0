#!/usr/bin/env bash
set -euo pipefail
ROOT=/home/gheno/citevision-v2
cd "$ROOT"
source scripts/lib/env-utils.sh
ENV_FILE="$(ensure_env_file "$ROOT")"
load_dotenv "$ENV_FILE"
KEY="${INTERNAL_API_KEY:-changeme_internal_service_key}"

echo "=== AI health ==="
curl -sf http://127.0.0.1:8001/health | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("status"), "models", d.get("models_all_ok"), "gpu", d.get("gpu_active"))'

echo "=== resync-spatial x2 ==="
curl -sf -X POST "http://127.0.0.1:8081/api/v1/internal/ingest/resync-spatial" -H "X-Internal-Key: $KEY"; echo
sleep 5
curl -sf -X POST "http://127.0.0.1:8081/api/v1/internal/ingest/resync-spatial" -H "X-Internal-Key: $KEY"; echo

for i in $(seq 1 24); do
  out=$(curl -sS http://127.0.0.1:8001/cameras | python3 -c '
import json,sys
d=json.load(sys.stdin)
cams=d.get("cameras") or []
n=len(cams)
fr=sum(int(c.get("frames_read") or 0) for c in cams)
err=";".join((c.get("last_error") or "")[:40] for c in cams)
print(f"n={n} frames={fr} err={err}")
')
  echo "t=$i $out"
  frames=$(echo "$out" | sed -n 's/.*frames=\([0-9]*\).*/\1/p')
  if [[ "${frames:-0}" -ge 10 ]]; then
    echo INGEST_READY
    break
  fi
  sleep 5
done

echo "=== Frigate fresh events ==="
curl -sS "http://127.0.0.1:5000/api/events?limit=5" | python3 -c '
import json,sys,time
evs=json.load(sys.stdin)
now=time.time()
for e in (evs if isinstance(evs,list) else [])[:5]:
  st=e.get("start_time")
  age=now-float(st) if isinstance(st,(int,float)) else None
  print(str(e.get("id",""))[:24], e.get("camera"), e.get("label"), f"age={age:.0f}s" if age is not None else "")
'

echo "=== rules-engine ==="
curl -sf http://127.0.0.1:8010/health || echo rules_down
echo
curl -sf -o /dev/null -w "ui=%{http_code} api=%{http_code}\n" http://127.0.0.1:5174/ http://127.0.0.1:8081/health || true
