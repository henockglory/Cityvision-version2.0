#!/usr/bin/env bash
set -uo pipefail
ROOT=~/citevision-v2
cd "$ROOT"
source scripts/lib/env-utils.sh
ENV_FILE="$(ensure_env_file "$ROOT")"
load_dotenv "$ENV_FILE"
KEY="${INTERNAL_API_KEY:-changeme_internal_service_key}"
ORG=74d51ead-97a7-4e41-a488-503a9b90c466
CAM=8ed20433-57d5-4999-a6ab-0bea028b23a3

python3 - <<PY
import json, urllib.request, os
API="http://127.0.0.1:8081"
body=json.dumps({"email":"glory.henock@hologram.cd","password":"Hologram2026!"}).encode()
tok=json.loads(urllib.request.urlopen(urllib.request.Request(
  f"{API}/api/v1/auth/login",data=body,headers={"Content-Type":"application/json"},method="POST"),timeout=15).read())["access_token"]
h={"Authorization":f"Bearer {tok}"}
ORG="$ORG"; CAM="$CAM"
# zones
raw=json.loads(urllib.request.urlopen(urllib.request.Request(
  f"{API}/api/v1/orgs/{ORG}/cameras/{CAM}/zones",headers=h),timeout=20).read())
zones=raw if isinstance(raw,list) else raw.get("zones") or raw.get("items") or []
print(f"zones={len(zones)}")
for z in zones:
  beh=z.get("behavior") or z.get("behaviors") or z.get("behavior_type")
  name=z.get("name")
  poly=z.get("polygon") or z.get("points") or []
  print(f"  name={name} behavior={beh} poly_pts={len(poly)} cfg={z.get('behavior_config')}")
# rules
raw=json.loads(urllib.request.urlopen(urllib.request.Request(
  f"{API}/api/v1/orgs/{ORG}/rules",headers=h),timeout=20).read())
rules=raw if isinstance(raw,list) else raw.get("rules") or raw.get("items") or []
for r in rules:
  if "Feu" in str(r.get("name","")) or "red_light" in str(r.get("event_type","")):
    print(f"RULE name={r.get('name')} enabled={r.get('is_enabled')} event={r.get('event_type')} cams={r.get('camera_ids')}")
# AI camera status
try:
  st=json.loads(urllib.request.urlopen(f"http://127.0.0.1:8001/cameras/{CAM}/status",timeout=8).read())
  print("ai status", st)
except Exception as e:
  print("ai status err", e)
# recent DB events for cam via API
raw=json.loads(urllib.request.urlopen(urllib.request.Request(
  f"{API}/api/v1/orgs/{ORG}/events?limit=10&camera_id={CAM}",headers=h),timeout=20).read())
evs=raw if isinstance(raw,list) else raw.get("events") or raw.get("items") or []
print(f"recent events API n={len(evs)}")
for e in evs[:8]:
  print(f"  type={e.get('event_type')} t={e.get('created_at') or e.get('timestamp')}")
PY
