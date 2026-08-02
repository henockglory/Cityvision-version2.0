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


def get_json(path: str) -> dict:
    with urllib.request.urlopen(f"{AI}{path}", timeout=12) as resp:
        return json.loads(resp.read().decode())


def main() -> int:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    root = OUT_DIR or os.path.expanduser("~/citevision-v2/logs")
    os.makedirs(root, exist_ok=True)
    out_path = os.path.join(root, f"blockers-{RULE}-{ts}.json")
    samples: list[dict] = []
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
        samples.append(row)
        print(
            f"  t+{int(DURATION - (deadline - time.time()))}s "
            f"emitted={row.get('health', {}).get('vlm_queue_emitted')} "
            f"rejected={row.get('health', {}).get('vlm_queue_rejected')} "
            f"red_enq={row.get('health', {}).get('frigate_bridge_red_light_enqueued')} "
            f"cabin={row.get('health', {}).get('frigate_bridge_cabin_enqueued')}",
            flush=True,
        )
        time.sleep(max(2.0, INTERVAL))
    payload = {"rule": RULE, "ts": ts, "samples": samples}
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    win = f"/mnt/c/Users/gheno/citevision/logs/blockers-{RULE}-{ts}.json"
    try:
        os.makedirs(os.path.dirname(win), exist_ok=True)
        with open(win, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        print(f"mirrored {win}", flush=True)
    except OSError as exc:
        print(f"WARN mirror: {exc}", flush=True)
    print(f"DONE {out_path}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
