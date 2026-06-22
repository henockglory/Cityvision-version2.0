from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

import numpy as np


class FaceRecognizer(ABC):
    """Interface for InsightFace-based face recognition."""

    @abstractmethod
    def detect_faces(self, frame: np.ndarray) -> list[dict[str, Any]]:
        """Return list of face detections with bbox and optional embedding."""
        ...


class InsightFaceStub(FaceRecognizer):
    """Stub implementation pending InsightFace integration."""

    def __init__(self, model_name: str = "buffalo_l") -> None:
        self.model_name = model_name
        self._loaded = False

    def load(self) -> None:
        self._loaded = True

    def detect_faces(self, frame: np.ndarray) -> list[dict[str, Any]]:
        return []
