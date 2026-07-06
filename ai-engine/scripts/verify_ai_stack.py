#!/usr/bin/env python3
"""Install gate: verify all AI models load and infer before starting ai-engine.

Reads shared/ai-stack-registry.json + shared/ai-models.json (extensible).

Usage:
  python ai-engine/scripts/verify_ai_stack.py           # verify only (exit 1 if KO)
  python ai-engine/scripts/verify_ai_stack.py --json    # machine-readable report
"""
from __future__ import annotations

import os

# Must be set before any paddle/paddleocr import (WSL oneDNN crash).
os.environ.setdefault("FLAGS_use_mkldnn", "0")
os.environ.setdefault("FLAGS_use_onednn", "0")
os.environ.setdefault("FLAGS_enable_pir_api", "0")
os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")

import argparse
import glob
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
AI_ROOT = ROOT / "ai-engine"
sys.path.insert(0, str(AI_ROOT / "src"))

from citevision_ai.utils.ai_registry import load_stack_registry  # noqa: E402

REGISTRY = ROOT / "shared" / "ai-stack-registry.json"
SECONDARY = ROOT / "shared" / "ai-models.json"


def _setup_cuda_ld() -> None:
    site = AI_ROOT / ".venv" / "lib"
    pkg_dirs = list(site.glob("python*/site-packages"))
    if not pkg_dirs:
        return
    sp = pkg_dirs[0]
    parts = []
    for rel in ("nvidia/cudnn/lib", "nvidia/cublas/lib", "nvidia/cuda_runtime/lib",
                "nvidia/curand/lib", "nvidia/cufft/lib"):
        p = sp / rel
        if p.is_dir():
            parts.append(str(p))
    if parts:
        os.environ["LD_LIBRARY_PATH"] = ":".join(parts)


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _stack_reg() -> dict:
    return load_stack_registry()


def _yolo_path() -> Path:
    gen = ROOT / "generated.env"
    name = "yolov8s.onnx"
    if gen.exists():
        for line in gen.read_text(encoding="utf-8").splitlines():
            if line.startswith("CV_YOLO_MODEL="):
                name = line.split("=", 1)[1].strip().strip('"')
                break
    p = AI_ROOT / "models" / name
    if p.exists():
        return p
    fb = AI_ROOT / "models" / "yolov8n.onnx"
    return fb if fb.exists() else p


def _insightface_ok() -> tuple[bool, str]:
    reg = _stack_reg()
    spec = next(m for m in reg["models"] if m["id"] == "insightface")
    pattern = ROOT / spec.get("required_glob", "")
    files = glob.glob(str(pattern))
    if len(files) < 3:
        return False, f"missing onnx under {pattern} (found {len(files)})"
    try:
        from insightface.app import FaceAnalysis

        root = str(AI_ROOT / "models" / "insightface")
        app = FaceAnalysis(name=spec.get("model_name", "buffalo_l"), root=root, providers=["CPUExecutionProvider"])
        app.prepare(ctx_id=-1, det_size=(640, 640))
        return True, f"{len(files)} onnx files"
    except Exception as exc:
        return False, str(exc)


def _paddle_ok() -> tuple[bool, str]:
    try:
        import numpy as np

        from citevision_ai.utils.paddle_ocr_compat import create_paddle_ocr, parse_ocr_lines, run_ocr

        ocr = create_paddle_ocr()
        img = np.zeros((64, 200, 3), dtype=np.uint8)
        result = run_ocr(ocr, img)
        parse_ocr_lines(result)
        return True, "inference ok"
    except Exception as exc:
        return False, str(exc)


def _yolo_ok(device: str = "cuda") -> tuple[bool, str]:
    path = _yolo_path()
    if not path.exists():
        return False, f"missing {path}"
    try:
        from citevision_ai.detection.yolo_onnx import YoloOnnxDetector

        det = YoloOnnxDetector(path, device=device)
        det.load()
        if not det.is_loaded:
            return False, "session not created"
        import numpy as np

        det.detect(np.zeros((480, 640, 3), dtype=np.uint8))
        cuda = "CUDA" in det.active_provider
        return True, det.active_provider + (" + cuda" if cuda else "")
    except Exception as exc:
        return False, str(exc)


def _secondary_ok(device: str = "cuda") -> list[dict]:
    out: list[dict] = []
    if not SECONDARY.exists():
        return out
    data = _load_json(SECONDARY)
    suffix = _stack_reg().get("secondary_health_suffix", "_model_loaded")
    dest = AI_ROOT / "models" / "secondary"
    for spec in data.get("models", []):
        mid = spec["id"]
        health_key = f"{mid}{suffix}"
        fpath = dest / spec["file"]
        row = {"id": mid, "health_key": health_key, "ok": False, "detail": ""}
        if not fpath.exists() or fpath.stat().st_size < 5000:
            row["detail"] = f"missing {fpath}"
            out.append(row)
            continue
        try:
            import onnxruntime as ort
            from citevision_ai.detection.yolo_onnx import resolve_onnx_providers

            providers, _ = resolve_onnx_providers(device)
            try:
                sess = ort.InferenceSession(str(fpath), providers=providers)
            except Exception:
                sess = ort.InferenceSession(str(fpath), providers=["CPUExecutionProvider"])
            inp = sess.get_inputs()[0]
            import numpy as np

            shape = [1 if (d is None or isinstance(d, str)) else int(d) for d in inp.shape]
            for i, d in enumerate(shape):
                if d <= 0:
                    shape[i] = spec.get("input_size", 640 if i >= 2 else 3)
            arr = np.zeros(shape, dtype=np.float32)
            sess.run(None, {inp.name: arr})
            prov = sess.get_providers()[0] if sess.get_providers() else "?"
            row["ok"] = True
            row["detail"] = prov
        except Exception as exc:
            row["detail"] = str(exc)
        out.append(row)
    return out


def verify(device: str = "cuda", require_gpu: bool | None = None) -> dict:
    _setup_cuda_ld()
    if require_gpu is None:
        require_gpu = bool(os.environ.get("YOLO_DEVICE", "cuda").lower() in ("cuda", "gpu", "0"))

    report: dict = {"ok": True, "models": [], "gpu": {}}
    yolo_ok, yolo_detail = _yolo_ok(device)
    report["models"].append({"id": "yolo", "health_key": "yolo_loaded", "ok": yolo_ok, "detail": yolo_detail})
    face_ok, face_detail = _insightface_ok()
    report["models"].append({"id": "insightface", "health_key": "face_loaded", "ok": face_ok, "detail": face_detail})
    paddle_ok, paddle_detail = _paddle_ok()
    report["models"].append({"id": "paddleocr", "health_key": "plate_loaded", "ok": paddle_ok, "detail": paddle_detail})
    for row in _secondary_ok(device):
        report["models"].append(row)

    cuda_ok = yolo_ok and "CUDA" in yolo_detail
    report["gpu"] = {"yolo_cuda": cuda_ok, "required": require_gpu}
    if require_gpu and not cuda_ok:
        report["ok"] = False

    for m in report["models"]:
        if not m["ok"]:
            report["ok"] = False
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--device", default=os.environ.get("YOLO_DEVICE", "cuda"))
    parser.add_argument("--allow-cpu", action="store_true", help="Skip yolo_cuda requirement")
    args = parser.parse_args()
    rep = verify(device=args.device, require_gpu=not args.allow_cpu)
    if args.json:
        print(json.dumps(rep, indent=2))
    else:
        for m in rep["models"]:
            mark = "OK" if m["ok"] else "FAIL"
            print(f"[{mark}] {m.get('id', m.get('health_key'))}: {m.get('detail', '')}")
        if rep["gpu"].get("required"):
            mark = "OK" if rep["gpu"].get("yolo_cuda") else "FAIL"
            print(f"[{mark}] yolo_cuda (GPU required)")
        if not rep["ok"]:
            print("\n[ERR] AI stack incomplete — run: bash scripts/install-ai-models.sh --fix")
    return 0 if rep["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
