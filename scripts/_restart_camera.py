#!/usr/bin/env python3
"""Redémarre le flux caméra en passant par le backend (resync-spatial)."""
import json, subprocess, urllib.request, time

CAM = "01ee632c-271c-4e66-ba98-3d1d7e430c09"
ORG = "e312f375-7442-4089-8022-ed232abc09e8"

# L'AI engine a la caméra mais elle est stoppée - on vérifie l'état
req = urllib.request.Request("http://127.0.0.1:8001/cameras")
d = json.load(urllib.request.urlopen(req, timeout=5))
print("Caméras AI:", json.dumps(d, indent=2))

# Récupérer la config complète de la caméra depuis l'AI engine docs/openapi
# Pour relancer proprement: appel au backend pour déclencher re-sync complet
print("\nForçage resync-spatial (doit relancer l'ingest)...")
req2 = urllib.request.Request(
    "http://127.0.0.1:8081/api/v1/internal/ingest/resync-spatial",
    data=b"", method="POST",
    headers={"X-Internal-Key": "changeme_internal_service_key"})
resp = urllib.request.urlopen(req2, timeout=10)
print("Resync:", resp.read().decode())

time.sleep(8)

# Vérifier
req3 = urllib.request.Request("http://127.0.0.1:8001/cameras")
d3 = json.load(urllib.request.urlopen(req3, timeout=5))
for c in d3.get("cameras", []):
    print(f"  {c['camera_id']}  running={c.get('running')}  frames={c.get('frames_processed')}")
