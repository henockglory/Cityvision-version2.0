"""Fuse Gemini OCR + PaddleOCR readings (best confidence wins)."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

import cv2
import numpy as np

from citevision_ai.identity.plate import PaddleOcrPlateBackend

_PLATE_RE = re.compile(r"^[A-Z0-9]{4,12}$")
_paddle_backend: PaddleOcrPlateBackend | None = None


@dataclass(frozen=True)
class PlateReading:
    text: str
    confidence: float
    source: str


def _normalize_plate(text: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", (text or "").upper())[:32]


def _valid_plate(text: str) -> bool:
    return bool(text) and bool(_PLATE_RE.match(text))


def get_paddle_backend() -> PaddleOcrPlateBackend:
    global _paddle_backend
    if _paddle_backend is None:
        _paddle_backend = PaddleOcrPlateBackend()
        _paddle_backend.load()
    return _paddle_backend


def run_paddle_on_jpeg(jpeg: bytes) -> PlateReading | None:
    if not jpeg:
        return None
    backend = get_paddle_backend()
    if not backend.is_loaded:
        return None
    arr = np.frombuffer(jpeg, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None or img.size == 0:
        return None
    results = backend.recognize(img)
    if not results:
        return None
    best = max(results, key=lambda r: float(r.confidence or 0.0))
    text = _normalize_plate(best.text)
    if not _valid_plate(text):
        return None
    return PlateReading(text=text, confidence=float(best.confidence), source="paddle")


def reading_from_gemini_verdict(verdict: Any) -> PlateReading | None:
    text = _normalize_plate(str(getattr(verdict, "plate_text", "") or ""))
    if not _valid_plate(text):
        return None
    conf = float(getattr(verdict, "confidence", 0.0) or 0.0)
    if not getattr(verdict, "readable", True) and conf < 0.35:
        return None
    return PlateReading(text=text, confidence=conf, source="gemini")


def fuse_plate_readings(
    gemini: PlateReading | None,
    paddle: PlateReading | None,
) -> tuple[PlateReading | None, dict[str, Any]]:
    """Return best reading + fusion metadata."""
    meta: dict[str, Any] = {
        "ocr_gemini": gemini.text if gemini else "",
        "ocr_gemini_conf": round(gemini.confidence, 3) if gemini else 0.0,
        "ocr_paddle": paddle.text if paddle else "",
        "ocr_paddle_conf": round(paddle.confidence, 3) if paddle else 0.0,
    }
    if gemini and paddle:
        if gemini.text == paddle.text:
            winner = PlateReading(
                text=gemini.text,
                confidence=max(gemini.confidence, paddle.confidence),
                source="both",
            )
        elif gemini.confidence >= paddle.confidence:
            winner = gemini
        else:
            winner = paddle
    elif gemini:
        winner = gemini
    elif paddle:
        winner = paddle
    else:
        meta["ocr_winner"] = ""
        return None, meta
    meta["ocr_winner"] = winner.source
    return winner, meta
