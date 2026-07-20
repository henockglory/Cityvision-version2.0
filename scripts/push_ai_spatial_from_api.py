#!/usr/bin/env python3
"""Push full spatial config from API zones directly to AI (bypass orchestrator)."""
from __future__ import annotations

import json
import os
import urllib.request

API = os.environ.get("BACKEND_API_URL", "http://127.0.0.1:8081")
AI = os.environ.get("AI_ENGINE_URL", "http://127.0.0.1:8001")
# [P.131] No hardcoded IDs/creds — resolved live from /auth/me, env overridable.
ORG = os.environ.get("DEMO_ORG_ID", "")
EMAIL = os.environ.get("ADMIN_EMAIL", "glory.henock@hologram.cd")
PASS = os.environ.get("ADMIN_PASSWORD", "Henockglory@03")


def req(method: str, url: str, body: dict | None = None, token: str | None = None) -> object:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(request, timeout=60) as resp:
        return json.loads(resp.read().decode())


def build_spatial(token: str, camera_id: str) -> dict:
    zones = req("GET", f"{API}/api/v1/orgs/{ORG}/zones", token=token)
    lines = req("GET", f"{API}/api/v1/orgs/{ORG}/lines", token=token)
    if isinstance(zones, dict):
        zones = zones.get("items", zones)
    if isinstance(lines, dict):
        lines = lines.get("items", lines)

    zone_list = []
    for z in zones or []:
        if z.get("camera_id") != camera_id:
            continue
        bc = z.get("behavior_config") or {}
        if isinstance(bc, str):
            bc = json.loads(bc) if bc.startswith("{") else {}
        zone_list.append(
            {
                "zone_id": z.get("name"),
                "name": z.get("name"),
                "zone_kind": z.get("zone_kind", ""),
                "behavior": bc.get("behavior", z.get("zone_kind", "")),
                "behavior_config": bc.get("config", {}),
                "polygon": z.get("polygon") or [],
                "loiter_threshold": 30,
            }
        )

    line_list = []
    for line in lines or []:
        if line.get("camera_id") != camera_id:
            continue
        line_list.append(
            {
                "line_id": line.get("name"),
                "name": line.get("name"),
                "start": line.get("start") or line.get("start_point"),
                "end": line.get("end") or line.get("end_point"),
                "direction": line.get("direction") or "unknown",
            }
        )
    return {"zones": zone_list, "lines": line_list}


def main() -> None:
    login = req("POST", f"{API}/api/v1/auth/login", body={"email": EMAIL, "password": PASS})
    token = login["access_token"]

    global ORG
    if not ORG:
        me = req("GET", f"{API}/api/v1/auth/me", token=token)
        ORG = (me or {}).get("org_id", "")

    cameras = req("GET", f"{API}/api/v1/orgs/{ORG}/cameras", token=token)
    if isinstance(cameras, dict):
        cameras = cameras.get("items", cameras)

    for cam in cameras or []:
        name = (cam.get("name") or "").lower()
        meta = cam.get("metadata") or {}
        if isinstance(meta, str):
            meta = json.loads(meta) if meta else {}
        is_demo = meta.get("demo") is True or "démo" in name
        if not is_demo:
            continue
        cid = cam["id"]
        video = meta.get("video_file") or meta.get("local_path") or ""
        if not video and meta.get("demo_video_id"):
            video = (
                f"/home/gheno/citevision-v2/data/videos/demo/{ORG}/"
                f"{meta['demo_video_id']}_stream.mp4"
            )
        spatial = build_spatial(token, cid)
        print(f"\n==> {cam.get('name')} ({cid[:8]})")
        print(f"    zones: {[z.get('behavior') for z in spatial.get('zones', [])]}")
        print(f"    lines: {[ln.get('line_id') for ln in spatial.get('lines', [])]}")
        body = {
            "org_id": ORG,
            "video_file": video,
            "ai_fps": 8,
            "spatial_rules": spatial,
        }
        try:
            req("POST", f"{AI}/cameras/{cid}/stop")
        except Exception:
            pass
        out = req("POST", f"{AI}/cameras/{cid}/start", body=body)
        print(f"    AI start: {out}")


if __name__ == "__main__":
    main()
