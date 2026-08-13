#!/usr/bin/env python3
"""Exit 0 if /health/platform JSON reports AI models OK (stdin or file arg)."""
import json
import sys


def models_ok(platform: dict) -> bool:
    ai = ((platform.get("components") or {}).get("ai_engine") or {}).get("detail") or {}
    if not ai and "models_all_ok" in platform:
        ai = platform
    all_ok = ai.get("models_all_ok")
    if all_ok is True or str(all_ok).lower() in ("true", "1", "yes"):
        return True
    def on(k: str) -> bool:
        v = ai.get(k)
        return v is True or str(v).lower() in ("true", "1", "yes")
    return on("yolo_loaded") and on("driver_phone_model_loaded") and on("seatbelt_model_loaded") and on("plate_loaded")


def main() -> int:
    raw = sys.stdin.read() if len(sys.argv) < 2 else open(sys.argv[1], encoding="utf-8").read()
    try:
        data = json.loads(raw)
    except Exception:
        return 1
    if not isinstance(data, dict):
        return 1
    return 0 if models_ok(data) else 1


if __name__ == "__main__":
    raise SystemExit(main())
