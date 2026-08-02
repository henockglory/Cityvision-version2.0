#!/usr/bin/env python3
"""Poll AI engine blockers for raw HSV gate state (independent of gate mode).

Usage:
  python scripts/microtest/_microtest_raw_hsv_probe.py --duration 60
  python scripts/microtest/_microtest_raw_hsv_probe.py --duration 60 --camera <cam_id>
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

TL_BEHAVIORS = frozenset({"traffic_light_color", "red_light_observation"})
AI_BASE = "http://127.0.0.1:8001"


def _get_json(url: str, timeout: float = 8.0) -> dict | list | None:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError):
        return None


def find_tl_cameras(ai_base: str) -> list[str]:
    """Return camera IDs with TL zones from spatial API."""
    tl_cams: list[str] = []
    payload = _get_json(f"{ai_base}/cameras")
    if not isinstance(payload, dict):
        return tl_cams
    cams = payload.get("cameras") or []
    if isinstance(cams, dict):
        cams = list(cams.values())
    for c in cams:
        if not isinstance(c, dict):
            continue
        cid = str(c.get("camera_id") or c.get("id") or "")
        if not cid:
            continue
        sp = _get_json(f"{ai_base}/cameras/{cid}/spatial")
        if not isinstance(sp, dict):
            continue
        zones = sp.get("zones") or []
        if any(
            isinstance(z, dict) and str(z.get("behavior") or "") in TL_BEHAVIORS
            for z in zones
        ):
            tl_cams.append(cid)
    return tl_cams


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--duration", type=int, default=60, help="Probe duration in seconds")
    parser.add_argument("--camera", type=str, default=None, help="Target camera ID")
    parser.add_argument("--ai-url", type=str, default=AI_BASE, help="AI engine base URL")
    parser.add_argument("--out-dir", type=str, default=None, help="Output directory")
    args = parser.parse_args()

    ai_base = args.ai_url.rstrip("/")
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    root = Path.home() / "citevision-v2"
    out_dir = Path(args.out_dir) if args.out_dir else Path(f"docs/microtest-fix-{ts}")
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / "raw_hsv_probe.csv"

    target_cams: list[str] = []
    if args.camera:
        target_cams = [args.camera]
    else:
        blockers = _get_json(f"{ai_base}/debug/rule-blockers")
        if isinstance(blockers, dict):
            tl_summary = blockers.get("spatial_tl_summary") or {}
            if isinstance(tl_summary, dict) and tl_summary:
                target_cams = list(tl_summary.keys())
        if not target_cams:
            target_cams = find_tl_cameras(ai_base)
        if not target_cams:
            target_cams = ["__all__"]

    print(f"[INFO] CSV: {csv_path}")
    print(f"[INFO] Duration: {args.duration}s")
    print(f"[INFO] Cameras: {target_cams}")

    n_red_raw = n_red_gate = n_unknown = n_total = 0
    last_bridge_enq = 0

    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "timestamp_utc", "camera_id", "raw", "stable", "gate",
            "grace_active", "bridge_red_enqueued",
        ])
        end = time.time() + args.duration
        while time.time() < end:
            ts_row = datetime.now(timezone.utc).isoformat()
            blockers = _get_json(f"{ai_base}/debug/rule-blockers") or {}
            hsv = blockers.get("hsv_gate_debug") if isinstance(blockers, dict) else {}
            bridge = blockers.get("frigate_bridge") if isinstance(blockers, dict) else {}
            bridge_enq = int((bridge or {}).get("red_light_enqueued") or 0)
            last_bridge_enq = bridge_enq

            if not isinstance(hsv, dict):
                hsv = {}

            cams_to_write = target_cams
            if cams_to_write == ["__all__"]:
                cams_to_write = list(hsv.keys()) or ["__none__"]

            for cam_id in cams_to_write:
                if cam_id == "__none__":
                    writer.writerow([ts_row, "", "unknown", "unknown", "unknown", False, bridge_enq])
                    n_unknown += 1
                    n_total += 1
                    continue
                dbg = hsv.get(cam_id) if isinstance(hsv.get(cam_id), dict) else {}
                raw = str(dbg.get("raw") or "unknown")
                stable = str(dbg.get("stable") or "unknown")
                gate = str(dbg.get("gate") or "unknown")
                grace = bool(dbg.get("grace_active"))
                writer.writerow([ts_row, cam_id, raw, stable, gate, grace, bridge_enq])
                n_total += 1
                if raw == "red":
                    n_red_raw += 1
                if gate == "red":
                    n_red_gate += 1
                if raw == "unknown" and stable == "unknown":
                    n_unknown += 1

            time.sleep(1)

    tl_summary_present = False
    blockers_final = _get_json(f"{ai_base}/debug/rule-blockers")
    if isinstance(blockers_final, dict):
        tl_summary_present = bool(blockers_final.get("spatial_tl_summary"))

    print(f"\n[RESULT] frames={n_total} n_red_raw={n_red_raw} n_red_gate={n_red_gate} n_unknown={n_unknown}")
    print(f"[RESULT] bridge_red_enqueued_final={last_bridge_enq}")
    print(f"[RESULT] spatial_tl_summary_present={tl_summary_present}")

    print("\n=== INTERPRÉTATION ===")
    if n_red_raw > 0 and not tl_summary_present:
        print("  raw=red détecté mais spatial_tl_summary vide → bug ROUTAGE (_spatial_configs).")
    elif n_red_raw > 0:
        print("  raw=red détecté + spatial TL résolu → flux HSV OK ; gate A NO-GO = timing/compteurs.")
    elif tl_summary_present:
        print("  spatial TL résolu mais raw=red=0 → pipeline HSV ne voit pas rouge (vidéo/seuils/timing).")
    else:
        print("  spatial TL absent → démarrer caméra feu + zones TL avant probe.")
    print(f"\nCSV: {csv_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
