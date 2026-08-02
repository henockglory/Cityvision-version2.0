#!/usr/bin/env python3
"""Gate Q18 + test 19: dump cabin JPEG crops from Frigate MQTT events."""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(os.environ.get("MICROTEST_ROOT", Path.home() / "citevision-v2"))
FRIGATE = os.environ.get("FRIGATE_URL", "http://127.0.0.1:5000").rstrip("/")
TARGET = int(os.environ.get("CABIN_DUMP_COUNT", "20") or 20)
WAIT = float(os.environ.get("CABIN_DUMP_WAIT_SEC", "600") or 600)


def frigate_events(limit: int = 50) -> list[dict]:
    url = f"{FRIGATE}/api/events?limit={limit}&has_snapshot=1"
    with urllib.request.urlopen(url, timeout=15) as resp:
        data = json.loads(resp.read())
    return data if isinstance(data, list) else []


def download_snapshot(event_id: str) -> bytes | None:
    url = f"{FRIGATE}/api/events/{event_id}/snapshot.jpg"
    try:
        with urllib.request.urlopen(url, timeout=20) as resp:
            return resp.read()
    except Exception:
        return None


def main() -> int:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = ROOT / "validation-evidence" / f"cabin-dump-{ts}"
    win = Path("/mnt/c/Users/gheno/citevision/validation-evidence") / f"cabin-dump-{ts}"
    out.mkdir(parents=True, exist_ok=True)
    try:
        win.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    manifest: list[dict] = []
    deadline = time.time() + WAIT
    seen: set[str] = set()
    print(f"cabin dump target={TARGET} wait={WAIT}s -> {out}", flush=True)
    while len(manifest) < TARGET and time.time() < deadline:
        for ev in frigate_events(80):
            eid = str(ev.get("id") or "")
            if not eid or eid in seen:
                continue
            label = str(ev.get("label") or "").lower()
            if label not in ("car", "truck", "bus", "motorcycle", "person"):
                continue
            zones = ev.get("zones") or ev.get("current_zones") or []
            jpeg = download_snapshot(eid)
            if not jpeg or len(jpeg) < 500:
                continue
            seen.add(eid)
            fname = f"{len(manifest)+1:02d}_{label}_{eid[:16]}.jpg"
            (out / fname).write_bytes(jpeg)
            try:
                (win / fname).write_bytes(jpeg)
            except OSError:
                pass
            box = ev.get("box")
            manifest.append({
                "file": fname,
                "event_id": eid,
                "label": label,
                "zones": zones,
                "bytes": len(jpeg),
                "box": box,
            })
            print(f"  saved {fname} bytes={len(jpeg)}", flush=True)
            if len(manifest) >= TARGET:
                break
        time.sleep(8)
    meta = {"ts": ts, "count": len(manifest), "items": manifest}
    (out / "manifest.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    try:
        (win / "manifest.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    except OSError:
        pass
    print(f"DONE count={len(manifest)} manifest={out}/manifest.json", flush=True)
    print("HUMAN_REVIEW: count discernable driver/seatbelt visible in JPEGs", flush=True)
    return 0 if manifest else 1


if __name__ == "__main__":
    sys.exit(main())
