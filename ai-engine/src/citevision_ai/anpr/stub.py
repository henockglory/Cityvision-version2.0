"""PaddleOCR interface stub for automatic number plate recognition."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

import numpy as np


@dataclass
class PlateResult:
    text: str
    confidence: float
    bbox: tuple[float, float, float, float]

    def to_dict(self) -> dict[str, Any]:
        x1, y1, x2, y2 = self.bbox
        return {
            "text": self.text,
            "confidence": round(self.confidence, 4),
            "bbox": {"x1": x1, "y1": y1, "x2": x2, "y2": y2},
        }


class PaddleOcrBackend(ABC):
    @abstractmethod
    def recognize(self, crop: np.ndarray) -> list[PlateResult]:
        ...


class AnprModule:
    """Stub implementation — swap with real PaddleOCR backend in production."""

    def __init__(self, backend: PaddleOcrBackend | None = None) -> None:
        self._backend = backend
        self._enabled = False

    def enable(self) -> None:
        self._enabled = True

    def disable(self) -> None:
        self._enabled = False

    @property
    def is_enabled(self) -> bool:
        return self._enabled

    def process(self, frame: np.ndarray, vehicle_bboxes: list[dict[str, float]] | None = None) -> list[PlateResult]:
        if not self._enabled:
            return []
        if self._backend is not None:
            results: list[PlateResult] = []
            for bbox in vehicle_bboxes or []:
                x1, y1, x2, y2 = int(bbox["x1"]), int(bbox["y1"]), int(bbox["x2"]), int(bbox["y2"])
                crop = frame[max(0, y1):y2, max(0, x1):x2]
                if crop.size > 0:
                    results.extend(self._backend.recognize(crop))
            return results
        return []
