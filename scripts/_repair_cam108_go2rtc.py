#!/usr/bin/env python3
"""Re-enregistre cam 108 dans go2rtc (preview UI) — WSL only, lecture/écriture go2rtc via API backend."""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

CAM108 = "37c7d7fa-12dc-450c-8c4b-ab63ed43a819"
API = "http://127.0.0.1:8081/api/v1"
GO2RTC = "http://127.0.0.1:1984"
STREAM = f"cam-{CAM108}"
RTSP = "rtsp://admin:hids+1234@192.168.1.108:554/live"
# HEVC → transcode h264 for WebRTC (same as Go2RTCSourceForRTSP)
GO2RTC_SRC = f"ffmpeg:{RTSP}#video=h264"


def load_env() -> None:
    for p in (Path.home() / "citevision-v2" / ".env",):
        if not p.exists():
            continue
        for line in p.read_text().splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, _, v = line.partition("=")
                k, v = k.strip(), v.strip().strip('"').strip("'")
                if k and k not in os.environ:
                    os.environ[k] = v


def req(method: str, url: str, token: str | None = None, body: dict | None = None) -> dict:
    h = {"Content-Type": "application/json"}
    if token:
        h["Authorization"] = f"Bearer {token}"
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(url, data=data, headers=h, method=method)
    with urllib.request.urlopen(r, timeout=60) as resp:
        raw = resp.read().decode()
        return json.loads(raw) if raw else {}


def go2rtc_has(name: str) -> bool:
    try:
        with urllib.request.urlopen(f"{GO2RTC}/api/streams", timeout=10) as r:
            streams = json.loads(r.read().decode())
        return name in streams
    except Exception:
        return False


def register_go2rtc_direct() -> None:
    q = urllib.parse.urlencode({"name": STREAM, "src": GO2RTC_SRC})
    r = urllib.request.Request(f"{GO2RTC}/api/streams?{q}", method="PUT")
    with urllib.request.urlopen(r, timeout=30) as resp:
        print("go2rtc PUT", resp.status, resp.read()[:200])


def main() -> int:
    load_env()
    org = os.environ.get("DEFAULT_ORG_ID", "74d51ead-97a7-4e41-a488-503a9b90c466")
    email = os.environ.get("ADMIN_EMAIL", "glory.henock@hologram.cd")
    password = os.environ.get("ADMIN_PASSWORD", "Henockglory@03")

    print(f"before: go2rtc has {STREAM} =", go2rtc_has(STREAM))

    # Prefer backend ReOnboard (updates DB metadata too)
    try:
        login = req("POST", f"{API}/auth/login", body={"email": email, "password": password})
        token = login["access_token"]
        preview = req("GET", f"{API}/orgs/{org}/cameras/{CAM108}/preview", token=token)
        print("preview API OK:", json.dumps(preview, indent=2))
    except urllib.error.HTTPError as e:
        print(f"preview API failed ({e.code}): {e.read()[:300].decode()}")
        print("fallback: direct go2rtc register…")
        register_go2rtc_direct()
    except Exception as e:
        print(f"preview API error: {e}")
        print("fallback: direct go2rtc register…")
        register_go2rtc_direct()

    print(f"after: go2rtc has {STREAM} =", go2rtc_has(STREAM))
    if go2rtc_has(STREAM):
        print(f"UI: http://127.0.0.1:5174/live — stream {STREAM}")
        return 0
    print("FAIL: stream still missing in go2rtc")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
