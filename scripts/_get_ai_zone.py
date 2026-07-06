#!/usr/bin/env python3
"""Récupère la zone active dans le cache de l'IA via ses endpoints."""
import json, urllib.request

BASE = "http://127.0.0.1:8001"
CAM = "01ee632c-271c-4e66-ba98-3d1d7e430c09"

# Essai de différents endpoints pour obtenir la config de zone
for path in [
    f"/cameras/{CAM}/spatial",
    f"/cameras/{CAM}/config",
    f"/cameras/{CAM}/zones",
    f"/cameras/{CAM}",
    f"/spatial/{CAM}",
    f"/zones",
    f"/config",
]:
    try:
        resp = urllib.request.urlopen(f"{BASE}{path}", timeout=3)
        d = json.load(resp)
        print(f"GET {path}: 200")
        print(json.dumps(d, indent=2)[:800])
        print()
    except urllib.error.HTTPError as e:
        print(f"GET {path}: {e.code}")
    except Exception as e:
        print(f"GET {path}: ERROR {e}")
