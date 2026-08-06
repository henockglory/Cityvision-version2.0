#!/usr/bin/env python3
"""Poll /health + /debug/rule-blockers during a 1-hit (read-only, no DB writes)."""
from __future__ import annotations

import json
import os
import time
import urllib.request
from datetime import datetime, timezone

AI = os.environ.get("AI_URL", "http://127.0.0.1:8001").rstrip("/")
RULE = os.environ.get("RULE_ALIAS", "unknown").strip() or "unknown"
INTERVAL = float(os.environ.get("OBSERVE_INTERVAL_SEC", "8") or 8)
DURATION = float(os.environ.get("OBSERVE_DURATION_SEC", "780") or 780)
OUT_DIR = os.environ.get("OBSERVE_OUT_DIR", "").strip()
OBSERVE_TS = os.environ.get("OBSERVE_TS", "").strip()


def get_json(path: str) -> dict:
    with urllib.request.urlopen(f"{AI}{path}", timeout=12) as resp:
        return json.loads(resp.read().decode())


def main() -> int:
    ts = OBSERVE_TS or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    root = OUT_DIR or os.path.expanduser("~/citevision-v2/logs")
    os.makedirs(root, exist_ok=True)
    out_path = os.path.join(root, f"blockers-{RULE}-{ts}.json")
    rejects_path = os.path.join(root, f"blockers-{RULE}-{ts}-rejects.json")
    samples: list[dict] = []
    reject_events: list[dict] = []
    seen_reject_keys: set[str] = set()
    deadline = time.time() + DURATION
    print(f"observe rule={RULE} duration={DURATION}s -> {out_path}", flush=True)
    while time.time() < deadline:
        row: dict = {"wall": time.time()}
        try:
            h = get_json("/health")
            row["health"] = {
                k: h.get(k)
                for k in h
                if any(
                    x in k
                    for x in (
                        "vlm",
                        "frigate_bridge",
                        "gemini",
                        "cabin_source",
                        "blocker",
                        "demo",
                    )
                )
            }
        except Exception as exc:
            row["health_err"] = str(exc)
        try:
            row["blockers"] = get_json("/debug/rule-blockers")
        except Exception as exc:
            row["blockers_err"] = str(exc)
        recent = (row.get("blockers") or {}).get("recent")
        if isinstance(recent, list):
            for ent in recent:
                if not isinstance(ent, dict):
                    continue
                if str(ent.get("kind") or "") != "vlm_reject":
                    continue
                key = "|".join(
                    [
                        str(ent.get("ts") or ""),
                        str(ent.get("event_id") or ""),
                        str(ent.get("frigate_event_id") or ""),
                        str(ent.get("reason_short") or ""),
                    ]
                )
                if key in seen_reject_keys:
                    continue
                seen_reject_keys.add(key)
                item = {
                    "wall": row["wall"],
                    "rule": ent.get("rule"),
                    "reason_short": ent.get("reason_short"),
                    "reject_reason": ent.get("reject_reason"),
                    "visible": ent.get("visible"),
                    "violation": ent.get("violation"),
                    "event_id": ent.get("event_id"),
                    "frigate_event_id": ent.get("frigate_event_id"),
                    "camera_id": ent.get("camera_id"),
                    "zone_id": ent.get("zone_id"),
                    "bbox_ts": ent.get("bbox_ts"),
                    "bbox": ent.get("bbox"),
                    "hsv_light_state": ent.get("hsv_light_state"),
                    "hsv_raw": ent.get("hsv_raw"),
                    "hsv_stable": ent.get("hsv_stable"),
                    "hsv_probe_not_red": ent.get("hsv_probe_not_red"),
                }
                reject_events.append(item)
                print(
                    "  reject "
                    f"reason={item.get('reason_short')} "
                    f"frigate_event={str(item.get('frigate_event_id') or '')[:12]} "
                    f"camera={str(item.get('camera_id') or '')[:8]}",
                    flush=True,
                )
        samples.append(row)
        print(
            f"  t+{int(DURATION - (deadline - time.time()))}s "
            f"emitted={row.get('health', {}).get('vlm_queue_emitted')} "
            f"completed={((row.get('blockers') or {}).get('vlm_queue') or {}).get('completed')} "
            f"rejected={row.get('health', {}).get('vlm_queue_rejected')} "
            f"red_enq={row.get('health', {}).get('frigate_bridge_red_light_enqueued')} "
            f"cabin={row.get('health', {}).get('frigate_bridge_cabin_enqueued')}",
            flush=True,
        )
        time.sleep(max(2.0, INTERVAL))
    payload = {"rule": RULE, "ts": ts, "samples": samples}
    rejects_payload = {"rule": RULE, "ts": ts, "rejects": reject_events}
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    with open(rejects_path, "w", encoding="utf-8") as f:
        json.dump(rejects_payload, f, indent=2)
    win = f"/mnt/c/Users/gheno/citevision/logs/blockers-{RULE}-{ts}.json"
    win_rejects = f"/mnt/c/Users/gheno/citevision/logs/blockers-{RULE}-{ts}-rejects.json"
    try:
        os.makedirs(os.path.dirname(win), exist_ok=True)
        with open(win, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        with open(win_rejects, "w", encoding="utf-8") as f:
            json.dump(rejects_payload, f, indent=2)
        print(f"mirrored {win}", flush=True)
        print(f"mirrored {win_rejects}", flush=True)
    except OSError as exc:
        print(f"WARN mirror: {exc}", flush=True)
    print(f"DONE {out_path}", flush=True)
    print(f"DONE {rejects_path}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
