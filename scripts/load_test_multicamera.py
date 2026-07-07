#!/usr/bin/env python3
"""Load test: 1 -> 16 simulated cameras (demo video duplicated N times) to
validate multi-camera GPU/ingest capacity BEFORE wiring in real live cameras.

Talks directly to the AI engine's own HTTP API (no backend/DB involved) using
FileVideoWorker cameras (video_file=...), so it exercises the exact same
shared YOLO session, micro-batching queue, and session lock that live RTSP
cameras use — only the ingestion source differs.

At each camera-count tier it measures, per camera:
  - effective processed FPS (frames_processed delta / elapsed time)
  - frames dropped (RTSPWorker/queue drop-oldest is RTSP-only, but
    FileVideoWorker's own last_error/frames_processed still reveal stalls)
  - inference latency (as reported by /cameras + /health/gpu)

and prints a per-tier summary plus a JSON report, so the maximum reliable
camera count for the current GPU can be decided empirically before any real
camera is connected.

Usage:
    python scripts/load_test_multicamera.py
    python scripts/load_test_multicamera.py --steps 1,2,4,8,12,16 --duration 20 --ai-fps 8
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def load_env_file() -> None:
    for candidate in (ROOT / ".env", Path.home() / "citevision-v2" / ".env"):
        if not candidate.exists():
            continue
        for line in candidate.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = val
        break


load_env_file()

AI_URL = os.environ.get("AI_HEALTH_URL", "http://127.0.0.1:8001").rstrip("/")
DEMO_VIDEO_PATH = os.environ.get(
    "DEMO_VIDEO_PATH",
    str(
        Path.home()
        / "citevision-v2/data/videos/demo/e312f375-7442-4089-8022-ed232abc09e8"
        / "d4cadc04-f940-497d-8031-80418ac7dd86_stream.mp4"
    ),
)
LOAD_TEST_ORG_ID = os.environ.get("LOAD_TEST_ORG_ID", "load-test-org")


def req(method: str, url: str, body: dict | None = None, timeout: float = 15.0) -> Any:
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"} if data else {}
    r = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(r, timeout=timeout) as resp:
        raw = resp.read().decode()
        return json.loads(raw) if raw else {}


def start_camera(camera_id: str, ai_fps: float) -> dict[str, Any]:
    body = {
        "video_file": DEMO_VIDEO_PATH,
        "ai_fps": ai_fps,
        "org_id": LOAD_TEST_ORG_ID,
    }
    return req("POST", f"{AI_URL}/cameras/{camera_id}/start", body)


def stop_camera(camera_id: str) -> None:
    try:
        req("POST", f"{AI_URL}/cameras/{camera_id}/stop", {})
    except Exception:
        pass


def stop_all(camera_ids: list[str]) -> None:
    for cid in camera_ids:
        stop_camera(cid)


def cameras_by_id() -> dict[str, dict[str, Any]]:
    try:
        listing = req("GET", f"{AI_URL}/cameras")
    except Exception:
        return {}
    return {c["camera_id"]: c for c in listing.get("cameras", [])}


def run_tier(n: int, ai_fps: float, duration: float, warmup: float) -> dict[str, Any]:
    camera_ids = [f"loadtest-cam-{i:02d}" for i in range(n)]
    print(f"\n=== Palier {n} caméra(s) ===")

    if not Path(DEMO_VIDEO_PATH).exists():
        print(f"  ! Vidéo démo introuvable: {DEMO_VIDEO_PATH}")
        return {"n": n, "error": f"video_missing:{DEMO_VIDEO_PATH}"}

    started: list[str] = []
    start_errors: list[str] = []
    for cid in camera_ids:
        try:
            start_camera(cid, ai_fps)
            started.append(cid)
        except urllib.error.HTTPError as exc:
            start_errors.append(f"{cid}: HTTP {exc.code} {exc.reason}")
        except Exception as exc:  # noqa: BLE001 - report and keep going
            start_errors.append(f"{cid}: {exc}")

    if start_errors:
        print(f"  Erreurs de démarrage ({len(start_errors)}): {start_errors[:3]}")

    time.sleep(max(0.5, warmup))
    baseline = cameras_by_id()
    t0 = time.monotonic()
    time.sleep(duration)
    elapsed = time.monotonic() - t0
    final = cameras_by_id()

    try:
        gpu = req("GET", f"{AI_URL}/health/gpu")
    except Exception as exc:  # noqa: BLE001
        gpu = {"error": str(exc)}

    per_camera: list[dict[str, Any]] = []
    for cid in started:
        b = baseline.get(cid, {})
        f = final.get(cid, {})
        delta_processed = int(f.get("frames_processed", 0)) - int(b.get("frames_processed", 0))
        eff_fps = delta_processed / elapsed if elapsed > 0 else 0.0
        per_camera.append({
            "camera_id": cid,
            "effective_fps": round(eff_fps, 2),
            "frames_dropped": f.get("frames_dropped", 0),
            "queue_depth": f.get("queue_depth", 0),
            "infer_latency_ms": f.get("infer_latency_ms"),
            "running": f.get("running"),
            "last_error": f.get("last_error"),
        })

    stop_all(started)
    time.sleep(1.0)

    eff_fps_values = [c["effective_fps"] for c in per_camera]
    result: dict[str, Any] = {
        "n": n,
        "started": len(started),
        "start_errors": start_errors,
        "elapsed_sec": round(elapsed, 1),
        "avg_effective_fps": round(statistics.mean(eff_fps_values), 2) if eff_fps_values else 0.0,
        "min_effective_fps": round(min(eff_fps_values), 2) if eff_fps_values else 0.0,
        "total_frames_dropped": sum(int(c["frames_dropped"] or 0) for c in per_camera),
        "cameras_with_errors": [c["camera_id"] for c in per_camera if c.get("last_error")],
        "gpu_benchmark_fps": gpu.get("benchmark_fps"),
        "gpu_avg_queue_depth": gpu.get("avg_queue_depth"),
        "gpu_max_queue_depth": gpu.get("max_queue_depth"),
        "gpu_avg_infer_latency_ms": gpu.get("avg_infer_latency_ms"),
        "gpu_max_infer_latency_ms": gpu.get("max_infer_latency_ms"),
        "per_camera": per_camera,
    }
    print(
        f"  démarrées={result['started']}/{n}  fps_moyen={result['avg_effective_fps']}"
        f"  fps_min={result['min_effective_fps']}  dropped_total={result['total_frames_dropped']}"
        f"  latence_moy_gpu={result['gpu_avg_infer_latency_ms']}ms"
    )
    if result["cameras_with_errors"]:
        print(f"  Caméras en erreur: {result['cameras_with_errors']}")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--steps", default="1,2,4,8,12,16", help="paliers de nombre de caméras, séparés par des virgules")
    parser.add_argument("--duration", type=float, default=20.0, help="secondes de mesure par palier")
    parser.add_argument("--warmup", type=float, default=3.0, help="secondes de chauffe avant mesure par palier")
    parser.add_argument("--ai-fps", type=float, default=8.0, dest="ai_fps")
    parser.add_argument("--out", default=str(ROOT / "scripts" / "_load_test_report.json"))
    args = parser.parse_args()

    steps = [int(s) for s in args.steps.split(",") if s.strip()]

    try:
        health = req("GET", f"{AI_URL}/health")
    except Exception as exc:  # noqa: BLE001
        print(f"AI engine inaccessible sur {AI_URL}: {exc}")
        return 1
    print(f"AI engine OK — provider={health.get('yolo_provider')} cuda={health.get('yolo_cuda')}")
    print(f"Vidéo démo: {DEMO_VIDEO_PATH}")

    results: list[dict[str, Any]] = []
    for n in steps:
        try:
            results.append(run_tier(n, args.ai_fps, args.duration, args.warmup))
        except Exception as exc:  # noqa: BLE001
            print(f"  Palier {n}: échec ({exc})")
            results.append({"n": n, "error": str(exc)})
        finally:
            # Always make sure nothing from this tier lingers into the next one.
            stop_all([f"loadtest-cam-{i:02d}" for i in range(n)])

    out_path = Path(args.out)
    out_path.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nRapport détaillé: {out_path}")

    print("\n=== RÉSUMÉ ===")
    header = f"{'N':>4} {'démarrées':>10} {'fps_moy':>8} {'fps_min':>8} {'dropped':>8} {'latence_ms':>11}"
    print(header)
    print("-" * len(header))
    max_stable = 0
    for r in results:
        if "started" not in r:
            print(f"{r.get('n', '?'):>4}  échec: {r.get('error')}")
            continue
        print(
            f"{r['n']:>4} {r['started']:>10} {r['avg_effective_fps']:>8} "
            f"{r['min_effective_fps']:>8} {r['total_frames_dropped']:>8} "
            f"{r.get('gpu_avg_infer_latency_ms') or 0:>11}"
        )
        # "Stable" tier: every requested camera started, ran with no reported
        # error, and sustained at least half the target ai_fps end-to-end.
        if (
            r["started"] == r["n"]
            and not r["cameras_with_errors"]
            and r["min_effective_fps"] >= args.ai_fps * 0.5
        ):
            max_stable = r["n"]

    print(f"\nCapacité stable estimée (fps_min >= 50% de ai_fps cible, 0 erreur): {max_stable} caméra(s)")
    print(
        "Note: charge GPU/CPU pure (détection + tracking), sans zones vitesse/feux "
        "simulées — les règles métier sont validées séparément (audit_live_speed_camera.py)."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
