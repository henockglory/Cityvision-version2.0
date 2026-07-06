from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

import numpy as np

from citevision_ai.utils.paddle_ocr_compat import create_paddle_ocr, parse_ocr_lines, run_ocr

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
            self._ocr = create_paddle_ocr(det_model_dir=str(self.model_dir))
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
            results = run_ocr(self._ocr, frame)
            plates: list[dict[str, Any]] = []
            for text, conf, box in parse_ocr_lines(results):
                if not box:
                    continue
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
