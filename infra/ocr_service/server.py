"""
CitéVision OCR service.

Goal: replace the failing Plate Recognizer cloud API with a robust, CPU-only,
open-source pipeline served as a tiny FastAPI HTTP service inside the Docker
network.

Pipeline:
    image bytes -> cv2 decode -> Fast-ALPR (YOLO plate detector + ONNX OCR)
                -> best plate (string + confidence + bbox)

The whole stack uses ONNX Runtime CPU. Models are pulled the first time the
container starts and cached in /models.
"""
from __future__ import annotations

import io
import logging
import os
import threading
import time
from typing import List, Optional

import cv2
import numpy as np
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from PIL import Image

logging.basicConfig(
    level=os.environ.get("OCR_LOG_LEVEL", "INFO"),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("ocr")

DETECTOR_MODEL = os.environ.get("OCR_DETECTOR_MODEL", "yolo-v9-t-384-license-plate-end2end")
OCR_MODEL = os.environ.get("OCR_OCR_MODEL", "global-plates-mobile-vit-v2-model")
NORMALIZE_REGEX = os.environ.get("OCR_NORMALIZE_REGEX", r"[^A-Z0-9]")
MIN_CONFIDENCE = float(os.environ.get("OCR_MIN_CONFIDENCE", "0.30"))
OCR_MAX_EDGE = int(os.environ.get("OCR_MAX_EDGE", "1280"))


for _d in ("/models/hf", "/models/xdg", "/models/torch", "/models/home/.cache/open-image-models"):
    try:
        os.makedirs(_d, exist_ok=True)
    except Exception:
        pass


_alpr = None
_alpr_lock = threading.Lock()
_alpr_loading = False
_alpr_error: Optional[str] = None


def _load_alpr_blocking() -> None:
    """Load Fast-ALPR once. Always called under `_alpr_lock`."""
    global _alpr, _alpr_loading, _alpr_error
    if _alpr is not None:
        return
    _alpr_loading = True
    _alpr_error = None
    try:
        log.info("Loading Fast-ALPR (detector=%s, ocr=%s)", DETECTOR_MODEL, OCR_MODEL)
        from fast_alpr import ALPR

        _alpr = ALPR(detector_model=DETECTOR_MODEL, ocr_model=OCR_MODEL)
        log.info("Fast-ALPR ready")
    except Exception as exc:
        _alpr_error = str(exc)
        log.exception("Fast-ALPR failed to load: %s", exc)
    finally:
        _alpr_loading = False


def _ensure_alpr():
    if _alpr is not None:
        return _alpr
    with _alpr_lock:
        if _alpr is None and not _alpr_loading:
            _load_alpr_blocking()
    return _alpr


def _decode_image(content: bytes) -> Optional[np.ndarray]:
    if not content:
        return None
    arr = np.frombuffer(content, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        try:
            pil = Image.open(io.BytesIO(content)).convert("RGB")
            img = cv2.cvtColor(np.array(pil), cv2.COLOR_RGB2BGR)
        except Exception:
            return None
    return img


def _resize_for_ocr(img: np.ndarray) -> np.ndarray:
    h, w = img.shape[:2]
    me = max(640, min(1920, OCR_MAX_EDGE))
    if max(h, w) <= me:
        return img
    scale = me / float(max(h, w))
    nw, nh = max(1, int(w * scale)), max(1, int(h * scale))
    return cv2.resize(img, (nw, nh), interpolation=cv2.INTER_AREA)


def _normalize(plate: str) -> str:
    import re

    if not plate:
        return ""
    return re.sub(NORMALIZE_REGEX, "", plate.upper())


app = FastAPI(title="CitéVision OCR", version="1.0.0")


def _async_warmup():
    """Background warmup: load models without blocking the HTTP server."""
    try:
        with _alpr_lock:
            _load_alpr_blocking()
        if _alpr is not None:
            try:
                dummy = np.zeros((96, 256, 3), dtype=np.uint8)
                _alpr.predict(dummy)
                log.info("Warmup pass complete")
            except Exception as exc:
                log.warning("Warmup predict failed (will recover on next call): %s", exc)
    except Exception as exc:
        log.exception("Warmup thread crashed: %s", exc)


@app.on_event("startup")
def _on_startup():
    threading.Thread(target=_async_warmup, name="alpr-warmup", daemon=True).start()


@app.get("/healthz")
def healthz():
    if _alpr is not None:
        return {"ok": True, "detector": DETECTOR_MODEL, "ocr": OCR_MODEL}
    if _alpr_loading:
        return JSONResponse(
            {"ok": False, "loading": True, "detector": DETECTOR_MODEL, "ocr": OCR_MODEL},
            status_code=503,
        )
    return JSONResponse(
        {"ok": False, "loading": False, "error": _alpr_error or "not_initialised"},
        status_code=503,
    )


@app.post("/ocr")
async def ocr(file: UploadFile = File(...)):
    started = time.perf_counter()
    raw = await file.read()
    img = _decode_image(raw)
    if img is None:
        raise HTTPException(status_code=400, detail="invalid_image")
    img = _resize_for_ocr(img)

    alpr = _ensure_alpr()
    results = alpr.predict(img)

    def _coerce_confidence(value, det_score: float) -> float:
        if value is None:
            return float(det_score or 0.0)
        if isinstance(value, (int, float)):
            return float(value)
        try:
            seq = [float(v) for v in value if v is not None]
        except TypeError:
            return float(det_score or 0.0)
        if not seq:
            return float(det_score or 0.0)
        return sum(seq) / len(seq)

    candidates: List[dict] = []
    for r in results or []:
        ocr_obj = getattr(r, "ocr", None)
        det = getattr(r, "detection", None)
        det_score = float(getattr(det, "confidence", 0.0) or 0.0) if det is not None else 0.0
        if ocr_obj is None:
            continue
        text = getattr(ocr_obj, "text", "") or ""
        conf = _coerce_confidence(getattr(ocr_obj, "confidence", None), det_score)
        bbox = None
        if det is not None and getattr(det, "bounding_box", None) is not None:
            bb = det.bounding_box
            bbox = {
                "x1": int(getattr(bb, "x1", 0)),
                "y1": int(getattr(bb, "y1", 0)),
                "x2": int(getattr(bb, "x2", 0)),
                "y2": int(getattr(bb, "y2", 0)),
            }
        candidates.append({
            "plate_raw": text,
            "plate_norm": _normalize(text),
            "confidence": conf,
            "detector_confidence": det_score,
            "bbox": bbox,
        })

    candidates.sort(key=lambda c: c["confidence"], reverse=True)

    best = candidates[0] if candidates and candidates[0]["confidence"] >= MIN_CONFIDENCE else None

    elapsed_ms = (time.perf_counter() - started) * 1000.0
    return {
        "plate": (best["plate_norm"] if best else ""),
        "plate_raw": (best["plate_raw"] if best else ""),
        "confidence": (best["confidence"] if best else 0.0),
        "bbox": (best["bbox"] if best else None),
        "candidates": candidates,
        "latency_ms": round(elapsed_ms, 1),
    }


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("OCR_PORT", "8181"))
    uvicorn.run("server:app", host="0.0.0.0", port=port, workers=1, log_level="info")
