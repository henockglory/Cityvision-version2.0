#!/usr/bin/env python3
"""Diagnose demo line counting: go2rtc, AI ingest, line config."""
from __future__ import annotations

import json
import subprocess
import urllib.request

API = "http://127.0.0.1:8081"
AI = "http://127.0.0.1:8001"
EMAIL = "glory.henock@hologram.cd"
PASS = "Henockglory@03"
COMPT_CAM = "9a3cd323-3820-46f0-aa5b-86c086a4a782"
COMPT_VIDEO = "1a7dd0c0-1557-427c-9a9e-03da850561d9"


def req(method: str, url: str, token: str | None = None, body: dict | None = None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(r, timeout=30) as resp:
        raw = resp.read().decode()
        return json.loads(raw) if raw else {}


def probe_rtsp(url: str, sec: int = 4) -> dict:
    cmd = [
        "ffprobe", "-v", "error", "-rtsp_transport", "tcp",
        "-show_entries", "stream=codec_type,width,height,r_frame_rate",
        "-of", "json", "-i", url,
    ]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=sec + 2)
        ok = out.returncode == 0
        streams = []
        if ok and out.stdout.strip():
            streams = json.loads(out.stdout).get("streams", [])
        return {"ok": ok, "streams": streams, "err": (out.stderr or "")[-300:]}
    except Exception as exc:
        return {"ok": False, "streams": [], "err": str(exc)}


def main() -> None:
    login = req("POST", f"{API}/api/v1/auth/login", body={"email": EMAIL, "password": PASS})
    token = login["access_token"]
    me = req("GET", f"{API}/api/v1/auth/me", token)
    org = me["org_id"]
    print(f"org={org}")

    # Demo settings
    ds = req("GET", f"{API}/api/v1/orgs/{org}/demo/settings", token)
    print(f"demo.active_video={ds.get('active_video_id')} expected={COMPT_VIDEO}")
    print(f"demo.active_camera={ds.get('active_camera_id')}")

    # Camera detail
    cam = req("GET", f"{API}/api/v1/orgs/{org}/cameras/{COMPT_CAM}", token)
    print(f"camera.name={cam.get('name')}")
    print(f"camera.demo={cam.get('demo')} enabled={cam.get('is_enabled')}")
    meta = cam.get("metadata") or {}
    if isinstance(meta, str):
        meta = json.loads(meta) if meta else {}
    go2rtc = meta.get("go2rtc_src") or cam.get("go2rtc_src") or ""
    print(f"camera.go2rtc_src={go2rtc}")

    # Lines
    lines = req("GET", f"{API}/api/v1/orgs/{org}/lines?camera_id={COMPT_CAM}", token)
    if isinstance(lines, dict):
        lines = lines.get("items", [])
    print(f"lines.count={len(lines) if isinstance(lines, list) else 'n/a'}")
    for ln in (lines or [])[:5]:
        print(f"  line id={ln.get('id')} name={ln.get('name')} enabled={ln.get('is_enabled')}")

    # Counters
    ctr = req("GET", f"{API}/api/v1/orgs/{org}/lines/counters?camera_id={COMPT_CAM}", token)
    car = [c for c in ctr if c.get("class_filter") == "car"]
    if car:
        print(f"counter.car total={car[0].get('count_total')} updated={car[0].get('updated_at')}")

    # AI camera status
    try:
        ai_cam = req("GET", f"{AI}/cameras/{COMPT_CAM}")
        print(f"ai.camera={json.dumps(ai_cam, indent=2)[:800]}")
    except Exception as exc:
        print(f"ai.camera ERROR: {exc}")

    # go2rtc streams
    for base in ("http://127.0.0.1:8554", "http://127.0.0.1:1984"):
        try:
            with urllib.request.urlopen(f"{base}/api/streams", timeout=3) as r:
                streams = json.loads(r.read().decode())
            print(f"go2rtc {base} streams={list(streams.keys())[:10]}")
        except Exception as exc:
            print(f"go2rtc {base} ERROR: {exc}")

    if go2rtc:
        print(f"ffprobe go2rtc_src: {probe_rtsp(go2rtc)}")
    demo_rtsp = f"rtsp://127.0.0.1:8554/demo-{org[:8]}-{COMPT_VIDEO[:8]}"
    print(f"ffprobe demo path: {probe_rtsp(demo_rtsp)}")

    # Recent line_cross demo events
    ev = req("GET", f"{API}/api/v1/orgs/{org}/events?limit=50&event_type=line_cross", token)
    items = ev if isinstance(ev, list) else ev.get("items", [])
    demo_n = 0
    for e in items:
        p = e.get("payload") or {}
        if isinstance(p, str):
            p = json.loads(p) if p else {}
        if p.get("demo") or (p.get("metadata") or {}).get("demo"):
            demo_n += 1
    print(f"line_cross demo events in last 50: {demo_n}")


if __name__ == "__main__":
    main()
