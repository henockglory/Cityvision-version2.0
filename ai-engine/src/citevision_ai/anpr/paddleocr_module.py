from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)


class PlateRecognizer(ABC):
    @abstractmethod
    def recognize_plates(self, frame: np.ndarray) -> list[dict[str, Any]]:
        ...


class PaddleOcrModule(PlateRecognizer):
    """Optional PaddleOCR integration. Returns empty when model missing."""

    def __init__(self, model_dir: str = "") -> None:
        self.model_dir = Path(model_dir) if model_dir else None
        self._ocr = None
        self._enabled = False

    def load(self) -> None:
        if not self.model_dir or not self.model_dir.exists():
            logger.info("PaddleOCR disabled: model dir not configured or missing")
            return
        try:
            from paddleocr import PaddleOCR  # type: ignore[import-untyped]

            self._ocr = PaddleOCR(use_angle_cls=True, lang="en", det_model_dir=str(self.model_dir))
            self._enabled = True
            logger.info("PaddleOCR loaded from %s", self.model_dir)
        except ImportError:
            logger.info("PaddleOCR package not installed; ANPR disabled")
        except Exception:
            logger.exception("PaddleOCR load failed; ANPR disabled")

    @property
    def is_enabled(self) -> bool:
        return self._enabled

    def recognize_plates(self, frame: np.ndarray) -> list[dict[str, Any]]:
        if not self._enabled or self._ocr is None:
            return []
        try:
            results = self._ocr.ocr(frame, cls=True)
            plates: list[dict[str, Any]] = []
            if not results:
                return plates
            for line in results[0] or []:
                text = line[1][0]
                conf = float(line[1][1])
                box = line[0]
                xs = [p[0] for p in box]
                ys = [p[1] for p in box]
                plates.append(
                    {
                        "text": text,
                        "confidence": conf,
                        "bbox": {
                            "x": float(min(xs)),
                            "y": float(min(ys)),
                            "width": float(max(xs) - min(xs)),
                            "height": float(max(ys) - min(ys)),
                        },
                    }
                )
            return plates
        except Exception:
            logger.exception("PaddleOCR inference failed")
            return []
