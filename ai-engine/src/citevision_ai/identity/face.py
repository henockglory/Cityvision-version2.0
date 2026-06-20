from __future__ import annotations

import logging
import re
import time
from typing import Any

import numpy as np

from citevision_ai.face.insightface_stub import FaceRecognizer

logger = logging.getLogger(__name__)


class InsightFaceRecognizer(FaceRecognizer):
    """Production InsightFace face detection and embedding."""

    def __init__(self, model_name: str = "buffalo_l", model_root: str = "models/insightface") -> None:
        self.model_name = model_name
        self.model_root = model_root
        self._app = None
        self._loaded = False

    def load(self) -> None:
        try:
            from insightface.app import FaceAnalysis

            self._app = FaceAnalysis(
                name=self.model_name,
                root=self.model_root,
                providers=["CPUExecutionProvider"],
            )
            self._app.prepare(ctx_id=0, det_size=(640, 640))
            self._loaded = True
            logger.info("InsightFace loaded: %s", self.model_name)
        except Exception:
            logger.exception("InsightFace load failed")
            self._loaded = False

    @property
    def is_loaded(self) -> bool:
        return self._loaded and self._app is not None

    def detect_faces(self, frame: np.ndarray) -> list[dict[str, Any]]:
        if not self.is_loaded:
            return []
        faces = self._app.get(frame)
        results = []
        for f in faces:
            bbox = f.bbox.astype(float)
            results.append({
                "bbox": {
                    "x": float(bbox[0]),
                    "y": float(bbox[1]),
                    "width": float(bbox[2] - bbox[0]),
                    "height": float(bbox[3] - bbox[1]),
                },
                "embedding": f.embedding.tolist() if f.embedding is not None else None,
                "confidence": float(getattr(f, "det_score", 0.9)),
            })
        return results


class FaceIdentityEngine:
    """Matches detected faces against org watchlist."""

    def __init__(self, recognizer: FaceRecognizer | None = None, match_threshold: float = 0.45) -> None:
        self.recognizer = recognizer or InsightFaceRecognizer()
        self.match_threshold = match_threshold
        self._watchlist: list[dict[str, Any]] = []
        self._last_refresh = 0.0
        self._refresh_interval = 60.0
        self._process_every_n = 5
        self._frame_counter = 0

    def load(self) -> None:
        if hasattr(self.recognizer, "load"):
            self.recognizer.load()

    @property
    def is_loaded(self) -> bool:
        return hasattr(self.recognizer, "is_loaded") and bool(self.recognizer.is_loaded)

    def set_watchlist(self, entries: list[dict[str, Any]]) -> None:
        self._watchlist = entries
        self._last_refresh = time.monotonic()

    def process_frame(
        self,
        camera_id: str,
        frame: np.ndarray,
        timestamp: str,
    ) -> list[dict[str, Any]]:
        self._frame_counter += 1
        if self._frame_counter % self._process_every_n != 0:
            return []
        if not hasattr(self.recognizer, "is_loaded") or not self.recognizer.is_loaded:
            return []

        import uuid

        events: list[dict[str, Any]] = []
        faces = self.recognizer.detect_faces(frame)
        for face in faces:
            emb = face.get("embedding")
            if emb is None:
                continue
            match = self._match_embedding(emb)
            if match:
                events.append({
                    "event_id": str(uuid.uuid4()),
                    "camera_id": camera_id,
                    "event_type": "face_watchlist_match",
                    "timestamp": timestamp,
                    "severity": "critical",
                    "track_id": -1,
                    "metadata": {
                        "label": match.get("label"),
                        "identifier": match.get("identifier"),
                        "confidence": match.get("score"),
                        "bbox": face["bbox"],
                    },
                })
            else:
                events.append({
                    "event_id": str(uuid.uuid4()),
                    "camera_id": camera_id,
                    "event_type": "face_unknown",
                    "timestamp": timestamp,
                    "severity": "warning",
                    "track_id": -1,
                    "metadata": {"bbox": face["bbox"], "confidence": face.get("confidence")},
                })
            events.append({
                "event_id": str(uuid.uuid4()),
                "camera_id": camera_id,
                "event_type": "face_detected",
                "timestamp": timestamp,
                "severity": "info",
                "track_id": -1,
                "metadata": {"bbox": face["bbox"], "confidence": face.get("confidence")},
            })
        return events

    def _match_embedding(self, embedding: list[float]) -> dict[str, Any] | None:
        if not self._watchlist:
            return None
        vec = np.array(embedding, dtype=np.float32)
        vec = vec / (np.linalg.norm(vec) + 1e-9)
        best_score = 0.0
        best_entry = None
        for entry in self._watchlist:
            meta = entry.get("metadata", {})
            ref = meta.get("embedding")
            if not ref:
                continue
            ref_vec = np.array(ref, dtype=np.float32)
            ref_vec = ref_vec / (np.linalg.norm(ref_vec) + 1e-9)
            score = float(np.dot(vec, ref_vec))
            if score > best_score:
                best_score = score
                best_entry = entry
        if best_entry and best_score >= self.match_threshold:
            return {"label": best_entry.get("label"), "identifier": best_entry.get("identifier"), "score": best_score}
        return None
