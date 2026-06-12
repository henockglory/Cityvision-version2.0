from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

import numpy as np


class PlateRecognizer(ABC):
    """Interface for PaddleOCR-based ANPR."""

    @abstractmethod
    def recognize_plates(self, frame: np.ndarray) -> list[dict[str, Any]]:
        """Return list of plate detections with text and confidence."""
        ...


class PaddleOcrStub(PlateRecognizer):
    """Stub implementation pending PaddleOCR integration."""

    def __init__(self, lang: str = "en") -> None:
        self.lang = lang
        self._loaded = False

    def load(self) -> None:
        self._loaded = True

    def recognize_plates(self, frame: np.ndarray) -> list[dict[str, Any]]:
        return []
