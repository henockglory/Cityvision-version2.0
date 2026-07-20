from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)


class FaceRecognizer(ABC):
    @abstractmethod
    def detect_faces(self, frame: np.ndarray) -> list[dict[str, Any]]:
        ...


class InsightFaceModule(FaceRecognizer):
    """Optional InsightFace integration. Returns empty when model missing."""

    def __init__(self, model_path: str = "") -> None:
        self.model_path = Path(model_path) if model_path else None
        self._app = None
        self._enabled = False
        self._device = "cpu"

    def load(self) -> None:
        if not self.model_path or not self.model_path.exists():
            logger.info("InsightFace disabled: model path not configured or missing")
            return
        try:
            from insightface.app import FaceAnalysis  # type: ignore[import-untyped]

            # [G.62]/[P.132] GPU priority, CPU last resort ([A.5]). Auto-detect the
            # CUDA provider; fall back to CPU only when CUDA is unavailable.
            providers = ["CPUExecutionProvider"]
            ctx_id = -1
            try:
                import onnxruntime as ort  # type: ignore[import-untyped]

                if "CUDAExecutionProvider" in ort.get_available_providers():
                    providers = ["CUDAExecutionProvider", "CPUExecutionProvider"]
                    ctx_id = 0
            except Exception:
                logger.warning("onnxruntime provider probe failed; InsightFace on CPU")

            self._app = FaceAnalysis(name=str(self.model_path), providers=providers)
            self._app.prepare(ctx_id=ctx_id, det_size=(640, 640))
            self._enabled = True
            self._device = "cuda" if ctx_id >= 0 else "cpu"
            logger.info(
                "InsightFace loaded from %s (device=%s, providers=%s)",
                self.model_path, self._device, providers,
            )
        except ImportError:
            logger.info("InsightFace package not installed; face detection disabled")
        except Exception:
            logger.exception("InsightFace load failed; face detection disabled")

    @property
    def is_enabled(self) -> bool:
        return self._enabled

    @property
    def device(self) -> str:
        return self._device

    def detect_faces(self, frame: np.ndarray) -> list[dict[str, Any]]:
        if not self._enabled or self._app is None:
            return []
        try:
            faces = self._app.get(frame)
            return [
                {
                    "bbox": {
                        "x": float(f.bbox[0]),
                        "y": float(f.bbox[1]),
                        "width": float(f.bbox[2] - f.bbox[0]),
                        "height": float(f.bbox[3] - f.bbox[1]),
                    },
                    "confidence": float(getattr(f, "det_score", 0.0)),
                }
                for f in faces
            ]
        except Exception:
            logger.exception("InsightFace inference failed")
            return []
