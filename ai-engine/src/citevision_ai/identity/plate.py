from __future__ import annotations

import logging
import re
import uuid
from typing import Any

import numpy as np

from citevision_ai.anpr.stub import AnprModule, PaddleOcrBackend, PlateResult

logger = logging.getLogger(__name__)

PLATE_RE = re.compile(r"^[A-Z0-9]{5,10}$")
VEHICLE_CLASSES = {"car", "truck", "bus", "motorcycle"}


class PaddleOcrPlateBackend(PaddleOcrBackend):
    """Real PaddleOCR backend for plate recognition."""

    def __init__(self) -> None:
        self._ocr = None
        self._loaded = False

    def load(self) -> None:
        try:
            from paddleocr import PaddleOCR

            self._ocr = PaddleOCR(use_angle_cls=True, lang="en")
            self._loaded = True
            logger.info("PaddleOCR loaded for ANPR")
        except Exception:
            logger.exception("PaddleOCR load failed")
            self._loaded = False

    @property
    def is_loaded(self) -> bool:
        return self._loaded and self._ocr is not None

    def recognize(self, crop: np.ndarray) -> list[PlateResult]:
        if not self.is_loaded or crop.size == 0:
            return []
        try:
            result = self._ocr.ocr(crop, cls=True)
            plates: list[PlateResult] = []
            if not result or not result[0]:
                return plates
            for line in result[0]:
                text = self._normalize(str(line[1][0]))
                conf = float(line[1][1])
                box = line[0]
                x1 = min(p[0] for p in box)
                y1 = min(p[1] for p in box)
                x2 = max(p[0] for p in box)
                y2 = max(p[1] for p in box)
                if text and conf > 0.5:
                    plates.append(PlateResult(text=text, confidence=conf, bbox=(x1, y1, x2, y2)))
            return plates
        except Exception:
            logger.exception("PaddleOCR recognize error")
            return []

    @staticmethod
    def _normalize(text: str) -> str:
        cleaned = re.sub(r"[^A-Za-z0-9]", "", text.upper())
        return cleaned if PLATE_RE.match(cleaned) else ""


class PlateIdentityEngine:
    """ANPR with watchlist matching."""

    def __init__(self, backend: PaddleOcrBackend | None = None) -> None:
        self._backend = backend or PaddleOcrPlateBackend()
        self._anpr = AnprModule(self._backend)
        self._plates: list[dict[str, Any]] = []
        self._process_every_n = 8
        self._frame_counter = 0

    def load(self) -> None:
        if hasattr(self._backend, "load"):
            self._backend.load()
        self._anpr.enable()

    @property
    def is_loaded(self) -> bool:
        return getattr(self._backend, "is_loaded", False)

    def set_plates(self, entries: list[dict[str, Any]]) -> None:
        self._plates = entries

    def process_frame(
        self,
        camera_id: str,
        frame: np.ndarray,
        tracks: list[dict],
        timestamp: str,
    ) -> list[dict[str, Any]]:
        self._frame_counter += 1
        if self._frame_counter % self._process_every_n != 0:
            return []
        if not getattr(self._backend, "is_loaded", False):
            return []

        events: list[dict[str, Any]] = []
        bboxes = []
        for t in tracks:
            if t.get("class_name") not in VEHICLE_CLASSES:
                continue
            b = t["bbox"]
            bboxes.append({
                "x1": b["x"],
                "y1": b["y"],
                "x2": b["x"] + b["width"],
                "y2": b["y"] + b["height"],
            })

        for plate in self._anpr.process(frame, bboxes):
            status = self._match_plate(plate.text)
            event_type = "plate_unknown"
            severity = "info"
            if status == "blocked":
                event_type = "plate_blocked"
                severity = "critical"
            elif status == "allowed":
                event_type = "plate_allowed"
                severity = "info"

            events.append({
                "event_id": str(uuid.uuid4()),
                "camera_id": camera_id,
                "event_type": event_type,
                "timestamp": timestamp,
                "severity": severity,
                "track_id": -1,
                "metadata": {
                    "plate_number": plate.text,
                    "plate_confidence": plate.confidence,
                    "status": status,
                },
            })
            events.append({
                "event_id": str(uuid.uuid4()),
                "camera_id": camera_id,
                "event_type": "plate_detected",
                "timestamp": timestamp,
                "severity": "info",
                "track_id": -1,
                "metadata": {
                    "plate_number": plate.text,
                    "plate_confidence": plate.confidence,
                },
            })
        return events

    def _match_plate(self, plate: str) -> str:
        for entry in self._plates:
            if entry.get("identifier", "").upper() == plate.upper():
                meta = entry.get("metadata", {})
                return meta.get("status", "blocked")
        return "unknown"
