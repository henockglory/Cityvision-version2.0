#!/usr/bin/env python3
"""Dump Frigate snapshots from feu camera for Gemini tests 11-18."""
from __future__ import annotations

import json
import os
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(os.environ.get("MICROTEST_ROOT", Path.home() / "citevision-v2"))
FRIGATE = os.environ.get("FRIGATE_URL", "http://127.0.0.1:5000").rstrip("/")
TARGET = int(os.environ.get("FEU_DUMP_COUNT", "10") or 10)
WAIT = float(os.environ.get("FEU_DUMP_WAIT_SEC", "120") or 120)


def frigate_events(limit: int = 80) -> list[dict]:
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
    out = ROOT / "validation-evidence" / f"feu-roi-{ts}"
    win = Path("/mnt/c/Users/gheno/citevision/validation-evidence") / f"feu-roi-{ts}"
    out.mkdir(parents=True, exist_ok=True)
    try:
        win.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    manifest: list[dict] = []
    deadline = time.time() + WAIT
    seen: set[str] = set()
    print(f"feu roi dump target={TARGET} -> {out}", flush=True)
    while len(manifest) < TARGET and time.time() < deadline:
        for ev in frigate_events(100):
            eid = str(ev.get("id") or "")
            if not eid or eid in seen:
                continue
            label = str(ev.get("label") or "").lower()
            if label not in ("car", "truck", "bus", "motorcycle"):
                continue
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
            manifest.append({"file": fname, "event_id": eid, "label": label, "bytes": len(jpeg)})
            print(f"  saved {fname}", flush=True)
            if len(manifest) >= TARGET:
                break
        time.sleep(6)
    meta = {"ts": ts, "count": len(manifest), "items": manifest}
    (out / "manifest.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(f"DONE feu-roi count={len(manifest)}", flush=True)
    return 0 if manifest else 1


if __name__ == "__main__":
    raise SystemExit(main())
