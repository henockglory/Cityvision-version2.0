from __future__ import annotations

import logging
import re
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from typing import Any

import cv2
import numpy as np

from citevision_ai.anpr.stub import AnprModule, PaddleOcrBackend, PlateResult
from citevision_ai.evidence.capture import bbox_rear_plate_region, normalize_bbox
from citevision_ai.utils.paddle_ocr_compat import create_paddle_ocr, parse_ocr_lines, run_ocr

logger = logging.getLogger(__name__)

PLATE_RE = re.compile(r"^[A-Z0-9]{4,12}$")
VEHICLE_CLASSES = {"car", "truck", "bus", "motorcycle"}
PLATE_TRACK_CACHE_SEC = 45.0
# Cap sync OCR per frame so ingest never blocks on PaddleOCR (multi-vehicle scenes).
MAX_PLATES_PER_FRAME = 1


_OCR_CIRCUIT_BREAKER_THRESHOLD = 3   # consecutive failures/timeouts before throttling OCR
_OCR_CALL_TIMEOUT_SEC = 3.0          # max seconds per PaddleOCR call (CPU warmup can exceed 1s)
_OCR_CIRCUIT_COOLDOWN_SEC = 30.0     # after tripping, retry (half-open) instead of disabling forever
_ocr_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="paddle-ocr")


class PaddleOcrPlateBackend(PaddleOcrBackend):
    """Real PaddleOCR backend for plate recognition.

    PaddleOCR 3.x can hang indefinitely in WSL on the first inference call.
    Every OCR call is executed in a worker thread and cancelled (counted as
    failure) after ``_OCR_CALL_TIMEOUT_SEC`` seconds.  After
    ``_OCR_CIRCUIT_BREAKER_THRESHOLD`` consecutive failures/timeouts the
    circuit-breaker opens and OCR is permanently disabled for this session,
    freeing the main ingest thread.
    """

    def __init__(self) -> None:
        self._ocr = None
        self._loaded = False
        self._consecutive_failures = 0
        self._circuit_open_until = 0.0  # monotonic ts; >now means OCR is throttled

    def load(self) -> None:
        try:
            self._ocr = create_paddle_ocr()
            smoke = np.zeros((48, 160, 3), dtype=np.uint8)
            # Smoke-test also inside the executor so we hit the same thread
            fut = _ocr_executor.submit(run_ocr, self._ocr, smoke)
            fut.result(timeout=_OCR_CALL_TIMEOUT_SEC * 5)
            self._loaded = True
            self._consecutive_failures = 0
            self._circuit_open_until = 0.0
            logger.info("PaddleOCR loaded for ANPR")
        except Exception:
            logger.exception("PaddleOCR load failed")
            self._ocr = None
            self._loaded = False

    @property
    def is_loaded(self) -> bool:
        # Health reflects whether the MODEL is available, independent of the
        # transient inference throttle — a slow call must not flip plate_loaded
        # to false for the whole session ([G.63]).
        return self._loaded and self._ocr is not None

    def _circuit_blocked(self) -> bool:
        """True while OCR is in cooldown after repeated timeouts (half-open recovery)."""
        if self._circuit_open_until <= 0.0:
            return False
        if time.monotonic() >= self._circuit_open_until:
            # Cooldown elapsed → half-open: allow one probe call to retry.
            self._circuit_open_until = 0.0
            self._consecutive_failures = 0
            return False
        return True

    def _trip_circuit(self, reason: str) -> None:
        self._consecutive_failures += 1
        if self._consecutive_failures >= _OCR_CIRCUIT_BREAKER_THRESHOLD:
            self._circuit_open_until = time.monotonic() + _OCR_CIRCUIT_COOLDOWN_SEC
            logger.warning(
                "PaddleOCR throttled for %.0fs after %d %s — ANPR paused (auto-retry)",
                _OCR_CIRCUIT_COOLDOWN_SEC, self._consecutive_failures, reason,
            )

    def _run_ocr_timed(self, crop: np.ndarray) -> list[Any]:
        """Submit OCR to executor; raise TimeoutError if it takes > _OCR_CALL_TIMEOUT_SEC."""
        fut = _ocr_executor.submit(run_ocr, self._ocr, crop)
        return fut.result(timeout=_OCR_CALL_TIMEOUT_SEC)

    def recognize(self, crop: np.ndarray) -> list[PlateResult]:
        if not self.is_loaded or crop.size == 0 or self._circuit_blocked():
            return []
        try:
            result = self._run_ocr_timed(crop)
            self._consecutive_failures = 0
            plates: list[PlateResult] = []
            for text, conf, box in parse_ocr_lines(result):
                text = self._normalize(text)
                if not box:
                    continue
                x1 = min(p[0] for p in box)
                y1 = min(p[1] for p in box)
                x2 = max(p[0] for p in box)
                y2 = max(p[1] for p in box)
                if text and conf > 0.5:
                    plates.append(PlateResult(text=text, confidence=conf, bbox=(x1, y1, x2, y2)))
            return plates
        except FuturesTimeout:
            self._trip_circuit("timeouts (>%.1fs)" % _OCR_CALL_TIMEOUT_SEC)
            return []
        except Exception:
            self._trip_circuit("consecutive failures")
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
        self._last_plate: dict[tuple[str, int], tuple[str, float, float]] = {}
        self._cache_ttl = PLATE_TRACK_CACHE_SEC

    def load(self) -> None:
        if hasattr(self._backend, "load"):
            self._backend.load()
        self._anpr.enable()

    @property
    def is_loaded(self) -> bool:
        return getattr(self._backend, "is_loaded", False)

    def set_plates(self, entries: list[dict[str, Any]]) -> None:
        self._plates = entries

    def reset_camera(self, camera_id: str) -> None:
        for key in list(self._last_plate):
            if key[0] == camera_id:
                self._last_plate.pop(key, None)

    def _remember_plate(
        self,
        camera_id: str,
        track_id: int,
        plate: str,
        confidence: float,
        now_ts: float | None = None,
    ) -> None:
        if track_id < 0 or not plate:
            return
        self._last_plate[(camera_id, track_id)] = (
            plate,
            confidence,
            now_ts if now_ts is not None else time.monotonic(),
        )

    def get_last_plate(
        self,
        camera_id: str,
        track_id: int,
        *,
        max_age_sec: float | None = None,
    ) -> tuple[str, float] | None:
        if track_id < 0:
            return None
        ttl = self._cache_ttl if max_age_sec is None else max_age_sec
        entry = self._last_plate.get((camera_id, track_id))
        if not entry:
            return None
        plate, conf, ts = entry
        if time.monotonic() - ts > ttl:
            self._last_plate.pop((camera_id, track_id), None)
            return None
        return plate, conf

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

        if not self._anpr.is_enabled:
            return []

        events: list[dict[str, Any]] = []
        h, w = frame.shape[:2]
        ocr_budget = MAX_PLATES_PER_FRAME
        # Recognize per-vehicle so each plate is linked to its track_id and the
        # vehicle bbox is carried for evidence / plate↔vehicle association.
        for t in tracks:
            if ocr_budget <= 0:
                break
            if t.get("class_name") not in VEHICLE_CLASSES:
                continue
            b = t.get("bbox") or {}
            track_id = t.get("track_id", -1)
            norm = normalize_bbox(b, w, h)
            if not norm:
                continue
            rear = bbox_rear_plate_region(norm)
            x1 = max(0, int(rear["x"] * w))
            y1 = max(0, int(rear["y"] * h))
            x2 = min(w, int((rear["x"] + rear["width"]) * w))
            y2 = min(h, int((rear["y"] + rear["height"]) * h))
            if x2 <= x1 or y2 <= y1:
                continue
            crop = frame[y1:y2, x1:x2]
            if crop.size == 0:
                continue
            if crop.shape[0] < 48 or crop.shape[1] < 120:
                crop = cv2.resize(crop, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)

            plates = self._backend.recognize(crop)
            ocr_budget -= 1
            if not plates:
                x1 = max(0, int(norm["x"] * w))
                y1 = max(0, int(norm["y"] * h))
                x2 = min(w, int((norm["x"] + norm["width"]) * w))
                y2 = min(h, int((norm["y"] + norm["height"]) * h))
                if x2 > x1 and y2 > y1:
                    full = frame[y1:y2, x1:x2]
                    if full.size > 0:
                        plates = self._backend.recognize(full)

            for plate in plates:
                if not plate.text:
                    continue
                self._remember_plate(camera_id, int(track_id), plate.text, plate.confidence)
                status = self._match_plate(plate.text)
                event_type = "plate_unknown"
                severity = "info"
                if status == "blocked":
                    event_type = "plate_blocked"
                    severity = "critical"
                elif status == "allowed":
                    event_type = "plate_allowed"
                    severity = "info"

                # Normalized vehicle bbox so the consumer can draw/crop reliably.
                norm_bbox = norm
                base_meta = {
                    "plate_number": plate.text,
                    "plate_confidence": plate.confidence,
                    "status": status,
                }
                events.append({
                    "event_id": str(uuid.uuid4()),
                    "camera_id": camera_id,
                    "event_type": event_type,
                    "timestamp": timestamp,
                    "severity": severity,
                    "track_id": track_id,
                    "class_name": t.get("class_name"),
                    # plate_number exposed at ROOT so rules-engine / evidence read it reliably.
                    "plate_number": plate.text,
                    "plate_confidence": plate.confidence,
                    "bbox": norm_bbox,
                    "metadata": base_meta,
                })
                events.append({
                    "event_id": str(uuid.uuid4()),
                    "camera_id": camera_id,
                    "event_type": "plate_detected",
                    "timestamp": timestamp,
                    "severity": "info",
                    "track_id": track_id,
                    "class_name": t.get("class_name"),
                    "plate_number": plate.text,
                    "plate_confidence": plate.confidence,
                    "bbox": norm_bbox,
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
