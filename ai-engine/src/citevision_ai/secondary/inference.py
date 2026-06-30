"""Secondary ONNX inference for driver-cabin violations (phone use, seatbelt).

For zones with behavior ``phone_use`` or ``seatbelt`` we crop the vehicle's
bounding box (the driver cabin region), run a dedicated ONNX model, and emit
``phone_use_violation`` / ``seatbelt_violation`` events when a *positive* class
is detected above the configured confidence.

Honesty guarantees:
  * If onnxruntime is unavailable or the model file is missing, the model is
    simply not loaded — it emits NOTHING (never a fabricated result) and the
    health endpoint reports it as not loaded.
  * Each emitted event carries the real model confidence and the source model id.

The registry (shared/ai-models.json) declares each model's file, classes and the
subset of ``positive_classes`` that constitute a violation.
"""

from __future__ import annotations

import json
import logging
import uuid
from pathlib import Path
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

_AI_ROOT = Path(__file__).resolve().parents[3]
_REPO_ROOT = _AI_ROOT.parent
VEHICLE_CLASSES = {"car", "truck", "bus", "motorcycle"}


def _registry_path() -> Path:
    for candidate in (
        _REPO_ROOT / "shared" / "ai-models.json",
        _AI_ROOT / "shared" / "ai-models.json",
    ):
        if candidate.exists():
            return candidate
    return _REPO_ROOT / "shared" / "ai-models.json"


def load_registry() -> list[dict[str, Any]]:
    path = _registry_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return list(data.get("models", []))
    except Exception:
        logger.warning("Could not read AI model registry at %s", path)
        return []


def models_dir() -> Path:
    return (_AI_ROOT / "models" / "secondary").resolve()


def _point_in_polygon(px: float, py: float, polygon: list[dict]) -> bool:
    n = len(polygon)
    if n < 3:
        return False
    inside = False
    j = n - 1
    for i in range(n):
        xi, yi = float(polygon[i].get("x", 0)), float(polygon[i].get("y", 0))
        xj, yj = float(polygon[j].get("x", 0)), float(polygon[j].get("y", 0))
        if ((yi > py) != (yj > py)) and (
            px < (xj - xi) * (py - yi) / (yj - yi + 1e-9) + xi
        ):
            inside = not inside
        j = i
    return inside


class _OnnxModel:
    """Thin YOLOv8-style ONNX detector for a fixed class list."""

    def __init__(self, spec: dict[str, Any], device: str = "cuda") -> None:
        self.id = str(spec.get("id"))
        self.behavior = str(spec.get("behavior", ""))
        self.event_type = str(spec.get("event_type", f"{self.id}_violation"))
        self.classes: list[str] = list(spec.get("classes", []))
        self.positive = set(spec.get("positive_classes", []))
        self.task = str(spec.get("task", "detection"))
        self.input_size = int(spec.get("input_size", 640))
        self.path = models_dir() / str(spec.get("file", f"{self.id}.onnx"))
        self.device = device
        self._session = None
        self._input_name: str | None = None
        self.active_provider = "none"

    def load(self) -> None:
        if not self.path.exists():
            logger.warning(
                "Secondary model '%s' missing at %s — behavior degraded (emits nothing).",
                self.id, self.path,
            )
            return
        try:
            import onnxruntime as ort
            from citevision_ai.detection.yolo_onnx import resolve_onnx_providers

            providers, label = resolve_onnx_providers(self.device)
            try:
                self._session = ort.InferenceSession(str(self.path), providers=providers)
            except Exception as cuda_err:
                if "CUDAExecutionProvider" in providers:
                    logger.warning(
                        "Secondary model '%s' CUDA init failed (%s) — retrying CPU",
                        self.id, cuda_err,
                    )
                    self._session = ort.InferenceSession(
                        str(self.path), providers=["CPUExecutionProvider"]
                    )
                else:
                    raise
            self._input_name = self._session.get_inputs()[0].name
            active = self._session.get_providers()
            self.active_provider = active[0] if active else label
            logger.info("Loaded secondary model '%s' (%s)", self.id, self.active_provider)
        except Exception:
            logger.exception("Failed to load secondary model '%s'", self.id)
            self._session = None

    @property
    def is_loaded(self) -> bool:
        return self._session is not None

    def infer_crop(self, crop: np.ndarray, conf: float) -> tuple[str, float] | None:
        """Return (class_name, confidence) of the top positive detection, else None."""
        if self._session is None or crop is None or crop.size == 0:
            return None
        import cv2

        size = self.input_size
        resized = cv2.resize(crop, (size, size))
        blob = (resized.astype(np.float32) / 255.0).transpose(2, 0, 1)[np.newaxis, ...]
        try:
            out = self._session.run(None, {self._input_name: blob})[0]
        except Exception:
            logger.debug("Secondary inference failed for '%s'", self.id, exc_info=True)
            return None
        if self.task == "classification":
            return self._parse_classification(out, conf)
        if out.ndim == 3:
            out = out[0]
        # YOLOv8 export is (4+nc, N); transpose to (N, 4+nc).
        if out.shape[0] == 4 + len(self.classes):
            out = out.T
        best: tuple[str, float] | None = None
        for row in out:
            scores = row[4:]
            if scores.size == 0:
                continue
            cid = int(np.argmax(scores))
            score = float(scores[cid])
            if score < conf or cid >= len(self.classes):
                continue
            name = self.classes[cid]
            if name in self.positive and (best is None or score > best[1]):
                best = (name, score)
        return best

    def _parse_classification(self, out: np.ndarray, conf: float) -> tuple[str, float] | None:
        """YOLOv8-cls ONNX output: (1, nc) logits or probabilities."""
        flat = out.reshape(-1)
        if flat.size == 0:
            return None
        cid = int(np.argmax(flat))
        score = float(flat[cid])
        if score < conf or cid >= len(self.classes):
            return None
        name = self.classes[cid]
        if name in self.positive:
            return (name, score)
        return None


class SecondaryInferenceEngine:
    """Loads registry models and runs driver-cabin violation detection per zone."""

    def __init__(self, device: str = "cuda") -> None:
        self._models: dict[str, _OnnxModel] = {}
        self._device = device
        self._frame_counter = 0
        self._process_every_n = 3
        self._cooldown: dict[tuple[str, int, str], int] = {}
        self._cooldown_frames = 45

    def load(self) -> None:
        for spec in load_registry():
            model = _OnnxModel(spec, device=self._device)
            model.load()
            # Index by behavior so a zone behavior maps directly to its model.
            if model.behavior:
                self._models[model.behavior] = model

    def health(self) -> dict[str, bool]:
        return {
            f"{m.id}_model_loaded": m.is_loaded
            for m in self._models.values()
        }

    def camera_has_behavior(self, zones: list[dict] | None) -> bool:
        if not zones:
            return False
        for z in zones:
            b = str(z.get("behavior", ""))
            if b in self._models or b == "driver_cabin":
                if b == "driver_cabin" and self._cabin_models():
                    return True
                if b in self._models:
                    return True
        return False

    def _cabin_models(self) -> list[_OnnxModel]:
        out: list[_OnnxModel] = []
        for key in ("phone_use", "seatbelt"):
            m = self._models.get(key)
            if m and m.is_loaded:
                out.append(m)
        return out

    def behaviors_present(self, zones: list[dict] | None) -> set[str]:
        if not zones:
            return set()
        return {str(z.get("behavior", "")) for z in zones if str(z.get("behavior", "")) in self._models}

    def process_frame(
        self,
        camera_id: str,
        frame: np.ndarray,
        tracks: list[dict],
        zones: list[dict] | None,
        timestamp: str,
    ) -> list[dict[str, Any]]:
        self._frame_counter += 1
        if frame is None or frame.size == 0 or not zones:
            return []
        target_zones: list[tuple[dict, list[_OnnxModel]]] = []
        for z in zones:
            b = str(z.get("behavior", ""))
            if b == "driver_cabin":
                models = self._cabin_models()
                if models:
                    target_zones.append((z, models))
            elif b in self._models:
                target_zones.append((z, [self._models[b]]))
        if not target_zones or (self._frame_counter - 1) % self._process_every_n != 0:
            return []

        h, w = frame.shape[:2]
        events: list[dict[str, Any]] = []
        for zone, models in target_zones:
            cfg = zone.get("behavior_config") or {}
            try:
                conf = float(cfg.get("confidence", 0.45))
            except (TypeError, ValueError):
                conf = 0.45
            poly = zone.get("polygon") or []
            for track in tracks:
                if str(track.get("class_name", "")) not in VEHICLE_CLASSES:
                    continue
                bbox = track.get("bbox") or {}
                cx = (float(bbox.get("x", 0)) + float(bbox.get("width", 0)) / 2) / max(w, 1)
                cy = (float(bbox.get("y", 0)) + float(bbox.get("height", 0)) / 2) / max(h, 1)
                if poly and not _point_in_polygon(cx, cy, poly):
                    continue
                crop = self._crop(frame, bbox)
                for model in models:
                    result = model.infer_crop(crop, conf)
                    if not result:
                        continue
                    tid = int(track.get("track_id", -1))
                    if not self._allow_emit(camera_id, tid, model.event_type):
                        continue
                    cls_name, score = result
                    events.append(
                        self._make_event(
                            camera_id, model, track, cls_name, score, timestamp, zone=zone,
                        )
                    )
        return events

    @staticmethod
    def _crop(frame: np.ndarray, bbox: dict) -> np.ndarray | None:
        if not bbox:
            return None
        h, w = frame.shape[:2]
        x1 = max(0, int(bbox.get("x", 0)))
        y1 = max(0, int(bbox.get("y", 0)))
        x2 = min(w, int(x1 + bbox.get("width", 0)))
        y2 = min(h, int(y1 + bbox.get("height", 0)))
        if x2 <= x1 or y2 <= y1:
            return None
        return frame[y1:y2, x1:x2]

    def _allow_emit(self, camera_id: str, track_id: int, event_type: str) -> bool:
        key = (camera_id, track_id, event_type)
        last = self._cooldown.get(key, -9999)
        if self._frame_counter - last < self._cooldown_frames:
            return False
        self._cooldown[key] = self._frame_counter
        return True

    @staticmethod
    def _make_event(
        camera_id: str,
        model: _OnnxModel,
        track: dict,
        cls_name: str,
        score: float,
        timestamp: str,
        *,
        zone: dict | None = None,
    ) -> dict[str, Any]:
        zone_id = ""
        if zone:
            zone_id = str(zone.get("zone_id") or zone.get("name") or "")
        return {
            "event_id": str(uuid.uuid4()),
            "camera_id": camera_id,
            "event_type": model.event_type,
            "event": model.event_type,
            "timestamp": timestamp,
            "track_id": track.get("track_id"),
            "class_name": track.get("class_name"),
            "zone_id": zone_id or None,
            "bbox": track.get("bbox") or {},
            "confidence": round(score, 3),
            "severity": "high",
            "metadata": {
                "model_id": model.id,
                "detected_class": cls_name,
                "confidence": round(score, 3),
                "detection_method": "secondary_onnx_model",
            },
        }
