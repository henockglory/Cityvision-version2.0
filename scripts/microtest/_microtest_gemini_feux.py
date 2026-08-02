#!/usr/bin/env python3
"""Tests 11-18: batch Gemini red-light judgment on saved JPEGs."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(os.environ.get("MICROTEST_ROOT", Path.home() / "citevision-v2"))
VENV_PY = ROOT / "ai-engine" / ".venv" / "bin" / "python"


def load_client():
    sys.path.insert(0, str(ROOT / "ai-engine" / "src"))
    from citevision_ai.config import settings
    from citevision_ai.vlm.gemini_client import GeminiClient

    key = (settings.gemini_api_key or os.environ.get("GEMINI_API_KEY") or "").strip()
    if not key:
        raise SystemExit("GEMINI_API_KEY missing")
    model = os.environ.get("GEMINI_MODEL") or settings.gemini_model or "gemini-2.5-flash"
    return GeminiClient(key, model=model, timeout=float(settings.gemini_timeout or 45))


def judge_dir(client, img_dir: Path, rule: str = "red_light_violation") -> list[dict]:
    rows: list[dict] = []
    for p in sorted(img_dir.glob("*.jpg"))[: int(os.environ.get("GEMINI_BATCH_N", "20") or 20)]:
        jpeg = p.read_bytes()
        v = client.judge_jpeg(jpeg, rule=rule, extra_context="microtest batch")
        rows.append({
            "file": p.name,
            "violation": bool(v.violation),
            "visible": bool(v.visible),
            "confidence": float(v.confidence or 0),
            "unclear": "unclear" in {s.lower() for s in (v.signals or [])},
            "error": v.error or "",
        })
        print(f"  {p.name} violation={v.violation} visible={v.visible} conf={v.confidence:.2f}", flush=True)
    return rows


def main() -> int:
    dump_glob = sorted((ROOT / "validation-evidence").glob("cabin-dump-*"))
    feu_glob = sorted((ROOT / "validation-evidence").glob("feu-roi-*"))
    img_dir = Path(os.environ.get("GEMINI_TEST_DIR", ""))
    if not img_dir.is_dir():
        img_dir = feu_glob[-1] if feu_glob else (dump_glob[-1] if dump_glob else None)
    if not img_dir or not Path(img_dir).is_dir():
        print("No image dir — run feu dump test 6 or set GEMINI_TEST_DIR", flush=True)
        return 1
    client = load_client()
    rows = judge_dir(client, Path(img_dir))
    viol = sum(1 for r in rows if r["violation"])
    vis = sum(1 for r in rows if r["visible"])
    out = ROOT / "logs" / f"microtest-gemini-feux-{os.environ.get('GEMINI_MODEL','flash')}.json"
    out.write_text(json.dumps({"rows": rows, "violation_count": viol, "visible_count": vis}, indent=2))
    gate = "GO" if viol >= 8 or vis >= 12 else "NO-GO"
    print(f"GATE_GEMINI_FEU={gate} violation={viol}/{len(rows)} visible={vis}/{len(rows)}", flush=True)
    return 0 if gate == "GO" else 1


if __name__ == "__main__":
    sys.exit(main())
