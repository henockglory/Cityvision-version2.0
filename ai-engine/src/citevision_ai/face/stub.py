"""InsightFace interface stub for face detection and embedding."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

import numpy as np


@dataclass
class FaceResult:
    bbox: tuple[float, float, float, float]
    confidence: float
    embedding: list[float] | None = None
    landmarks: list[tuple[float, float]] | None = None

    def to_dict(self) -> dict[str, Any]:
        x1, y1, x2, y2 = self.bbox
        return {
            "bbox": {"x1": x1, "y1": y1, "x2": x2, "y2": y2},
            "confidence": round(self.confidence, 4),
            "embedding_dim": len(self.embedding) if self.embedding else 0,
            "landmarks": self.landmarks,
        }


class InsightFaceBackend(ABC):
    @abstractmethod
    def detect_and_embed(self, frame: np.ndarray) -> list[FaceResult]:
        ...


class FaceModule:
    """Stub implementation — swap with real InsightFace backend in production."""

    def __init__(self, backend: InsightFaceBackend | None = None) -> None:
        self._backend = backend
        self._enabled = False

    def enable(self) -> None:
        self._enabled = True

    def disable(self) -> None:
        self._enabled = False

    @property
    def is_enabled(self) -> bool:
        return self._enabled

    def process(self, frame: np.ndarray, track_bboxes: list[dict[str, float]] | None = None) -> list[FaceResult]:
        if not self._enabled:
            return []
        if self._backend is not None:
            return self._backend.detect_and_embed(frame)
        # Stub: return placeholder results for person tracks
        results: list[FaceResult] = []
        for i, bbox in enumerate(track_bboxes or []):
            results.append(
                FaceResult(
                    bbox=(bbox["x1"], bbox["y1"], bbox["x2"], bbox["y2"]),
                    confidence=0.0,
                    embedding=[0.0] * 512,
                )
            )
        return results
