#!/usr/bin/env python3
"""End-to-end wizard flow for 192.168.1.108"""
import json
import sys
import urllib.error
import urllib.request

BASE = "http://localhost:8081/api/v1"
EMAIL = "glory.henock@hologram.cd"
APP_PASS = "TestMode2026!"
CAM_USER = "admin"
CAM_PASS = "hids+1234"
ORG = "e312f375-7442-4089-8022-ed232abc09e8"


def req(method, path, headers=None, body=None, timeout=120):
    h = headers or {}
    data = json.dumps(body).encode() if body is not None else None
    if data is not None:
        h.setdefault("Content-Type", "application/json")
    r = urllib.request.Request(f"{BASE}{path}", data=data, headers=h, method=method)
    try:
        resp = urllib.request.urlopen(r, timeout=timeout)
        raw = resp.read()
        return resp.status, json.loads(raw) if raw else None
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()


def main():
    login = json.loads(urllib.request.urlopen(urllib.request.Request(
        f"{BASE}/auth/login",
        data=json.dumps({"email": EMAIL, "password": APP_PASS}).encode(),
        headers={"Content-Type": "application/json"},
    )).read().decode())
    token = login["access_token"]
    headers = {"Authorization": f"Bearer {token}", "X-Org-ID": ORG}

    me = json.loads(urllib.request.urlopen(urllib.request.Request(
        f"{BASE}/auth/me", headers=headers
    )).read().decode())
    site_id = me.get("site_id")
    print("site_id:", site_id)

    st, probe = req("POST", f"/orgs/{ORG}/cameras/probe", headers, {
        "host": "192.168.1.108", "port": 554, "username": CAM_USER, "password": CAM_PASS,
    }, timeout=90)
    print("probe", st, "best:", probe.get("best") if isinstance(probe, dict) else probe)
    if st != 200 or not probe.get("best", {}).get("ok"):
        sys.exit(1)

    best = probe["best"]
    payload = {
        "site_id": site_id,
        "name": "Camera 192.168.1.108",
        "host": "192.168.1.108",
        "username": CAM_USER,
        "password": CAM_PASS,
        "port": 554,
        "vendor": best.get("vendor", "generic"),
        "rtsp_path": best.get("rtsp_path", "/live"),
        "stream_profile": "main",
    }
    st, cam = req("POST", f"/orgs/{ORG}/cameras", headers, payload, timeout=60)
    print("create", st, cam if st != 200 else {"id": cam.get("id"), "host": cam.get("host")})
    if st != 200 and st != 201:
        sys.exit(2)

    cam_id = cam["id"]
    st, test = req("POST", f"/orgs/{ORG}/cameras/{cam_id}/stream/test", headers, {}, timeout=60)
    print("stream/test", st, test)
    st, preview = req("GET", f"/orgs/{ORG}/cameras/{cam_id}/preview", headers, timeout=60)
    print("preview", st, preview if isinstance(preview, dict) else preview)
    if st == 200 and test.get("video_ok") and preview:
        print("OK full pipeline")
        return
    sys.exit(3)


if __name__ == "__main__":
    main()
