#!/usr/bin/env python3
"""Verify live /health against shared/ai-stack-registry.json (+ secondary models).

Usage:
  python ai-engine/scripts/check_ai_health.py
  python ai-engine/scripts/check_ai_health.py --url http://127.0.0.1:8001/health
  python ai-engine/scripts/check_ai_health.py --require-gpu
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "ai-engine" / "src"))

from citevision_ai.utils.ai_registry import required_health_keys  # noqa: E402


def fetch_health(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=10) as resp:
        return json.loads(resp.read().decode())


def check(url: str, require_gpu: bool = False) -> tuple[bool, list[str], dict]:
    try:
        data = fetch_health(url)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        return False, [f"health unreachable: {exc}"], {}

    keys = required_health_keys()
    if not require_gpu and "yolo_cuda" in keys:
        keys = [k for k in keys if k != "yolo_cuda"]

    bad: list[str] = []
    for key in keys:
        if str(data.get(key, "")).lower() != "true":
            bad.append(key)
    return len(bad) == 0, bad, data


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8001/health")
    parser.add_argument("--require-gpu", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    ok, bad, data = check(args.url, require_gpu=args.require_gpu)
    if args.json:
        print(json.dumps({"ok": ok, "bad": bad, "health": data}, indent=2))
    elif ok:
        print("[OK] All required AI health keys true")
        for key in required_health_keys():
            if key == "yolo_cuda" and not args.require_gpu:
                continue
            print(f"  {key}: {data.get(key)}")
    else:
        print("[FAIL] AI health incomplete:", ", ".join(bad), file=sys.stderr)
        for key in bad:
            print(f"  {key}: {data.get(key, 'missing')}", file=sys.stderr)
        print("Run: bash scripts/install-ai-models.sh --fix", file=sys.stderr)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
