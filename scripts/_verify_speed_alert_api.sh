#!/usr/bin/env bash
set -euo pipefail
cd /home/gheno/citevision-v2
ORG=74d51ead-97a7-4e41-a488-503a9b90c466
CAM=55694d53-8f58-4981-91b2-7c6cd528a25d
python3 scripts/_reset_demo_password.py 'Hologram2026!' || true
python3 <<PY
import json, urllib.request, urllib.parse, urllib.error, subprocess

ORG="$ORG"
CAM="$CAM"
body = json.dumps({"email":"glory.henock@hologram.cd","password":"Hologram2026!"}).encode()
tok = json.loads(urllib.request.urlopen(urllib.request.Request(
    "http://127.0.0.1:8081/api/v1/auth/login", data=body,
    headers={"Content-Type":"application/json"}, method="POST"), timeout=15).read())["access_token"]
h = {"Authorization": f"Bearer {tok}"}

# Try common alert list paths
paths = [
    f"/api/v1/orgs/{ORG}/alerts?limit=5&camera_id={CAM}",
    f"/api/v1/orgs/{ORG}/alerts?limit=5",
    f"/api/v1/alerts?org_id={ORG}&limit=5",
]
raw = None
for p in paths:
    try:
        raw = json.loads(urllib.request.urlopen(urllib.request.Request(
            f"http://127.0.0.1:8081{p}", headers=h), timeout=20).read())
        print("endpoint_ok", p)
        break
    except urllib.error.HTTPError as e:
        print("endpoint", p, e.code)

if raw is None:
    # DB fallback — same source as validator
    out = subprocess.check_output([
        "bash","-lc",
        f"cd /home/gheno/citevision-v2 && source scripts/lib/env-utils.sh && "
        f"psql \"\$DATABASE_URL\" -t -A -c \"SELECT id::text, created_at::text, "
        f"evidence_snapshot->'package'->'metadata'->>'capture_source', "
        f"evidence_snapshot->'package'->'metadata'->>'evidence_status' "
        f"FROM alerts WHERE org_id='{ORG}'::uuid ORDER BY created_at DESC LIMIT 5\""
    ], text=True)
    print("db_alerts:")
    print(out)
else:
    items = raw if isinstance(raw, list) else raw.get("alerts") or raw.get("items") or raw.get("data") or []
    print(f"alerts={len(items)}")
    for a in items[:5]:
        snap = a.get("evidence_snapshot") or {}
        if isinstance(snap, str):
            try: snap = json.loads(snap)
            except Exception: snap = {}
        pkg = snap.get("package") or {}
        meta = pkg.get("metadata") if isinstance(pkg, dict) else {}
        src = (meta or {}).get("capture_source")
        imgs = pkg.get("images") if isinstance(pkg, dict) else []
        roles = [i.get("role") for i in (imgs or []) if isinstance(i, dict) and (i.get("url") or i.get("asset_id"))]
        clip = pkg.get("clip") if isinstance(pkg, dict) else {}
        has_clip = bool(isinstance(clip, dict) and (clip.get("url") or clip.get("asset_id")))
        print(f"  id={str(a.get('id',''))[:8]} src={src} roles={roles} clip={has_clip}")

for port in (5174, 5173):
    try:
        r = urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=5)
        print(f"frontend_{port}={r.status}")
    except Exception as e:
        print(f"frontend_{port}_err={type(e).__name__}")
PY
