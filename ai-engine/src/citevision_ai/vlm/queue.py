"""Async bounded queue for Gemini VLM jobs — never blocks RTSP infer thread."""
from __future__ import annotations

import logging
import queue
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from citevision_ai.vlm.gemini_client import GeminiClient, should_emit

logger = logging.getLogger(__name__)

EmitCallback = Callable[[dict[str, Any]], None]


@dataclass
class VlmJob:
    jpeg: bytes
    rule: str
    min_confidence: float
    event_skeleton: dict[str, Any]
    extra_context: str = ""
    enqueued_at: float = field(default_factory=time.time)


class VlmQueue:
    """Daemon worker (single) consuming cabin/face VLM jobs with free-tier pacing."""

    def __init__(
        self,
        client: GeminiClient,
        *,
        maxsize: int = 32,
        max_age_sec: float = 12.0,
        min_interval_sec: float = 3.0,
    ) -> None:
        self._client = client
        self._q: queue.Queue[VlmJob | None] = queue.Queue(maxsize=max(1, int(maxsize)))
        self._max_age_sec = float(max_age_sec) if max_age_sec > 0 else 12.0
        self._min_interval_sec = float(min_interval_sec) if min_interval_sec > 0 else 3.0
        self._emit: EmitCallback | None = None
        self._stats = {
            "enqueued": 0,
            "dropped_full": 0,
            "dropped_stale": 0,
            "completed": 0,
            "emitted": 0,
            "rejected": 0,
            "unclear": 0,
            "rate_limited": 0,
        }
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._backoff_until = 0.0
        self._last_call_at = 0.0

    def set_emit_callback(self, cb: EmitCallback | None) -> None:
        self._emit = cb

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run, name="gemini-vlm-worker", daemon=True,
        )
        self._thread.start()
        logger.info("vlm queue worker started model=%s", self._client.model)

    def stop(self) -> None:
        self._stop.set()
        try:
            self._q.put_nowait(None)
        except queue.Full:
            pass

    def stats(self) -> dict[str, int]:
        with self._lock:
            return dict(self._stats)

    def try_enqueue(self, job: VlmJob) -> bool:
        if not self._client.configured:
            return False
        if time.time() < self._backoff_until:
            with self._lock:
                self._stats["rate_limited"] += 1
            return False
        try:
            self._q.put_nowait(job)
            with self._lock:
                self._stats["enqueued"] += 1
            return True
        except queue.Full:
            with self._lock:
                self._stats["dropped_full"] += 1
            logger.warning("vlm_queue_full rule=%s — dropping job", job.rule)
            return False

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                item = self._q.get(timeout=0.5)
            except queue.Empty:
                continue
            if item is None:
                break
            self._process(item)

    def _process(self, job: VlmJob) -> None:
        age = time.time() - float(job.enqueued_at)
        if age > self._max_age_sec:
            with self._lock:
                self._stats["dropped_stale"] += 1
            logger.info("vlm_subject_stale rule=%s age=%.2fs", job.rule, age)
            return
        now = time.time()
        if now < self._backoff_until:
            with self._lock:
                self._stats["rate_limited"] += 1
            return
        wait = self._min_interval_sec - (now - self._last_call_at)
        if wait > 0:
            time.sleep(wait)
        self._last_call_at = time.time()
        verdict = self._client.judge_jpeg(
            job.jpeg, rule=job.rule, extra_context=job.extra_context,
        )
        with self._lock:
            self._stats["completed"] += 1
        if verdict.error == "rate_limited":
            # Free-tier recovery: longer pause, drain queue pressure.
            self._backoff_until = time.time() + 60.0
            with self._lock:
                self._stats["rate_limited"] += 1
            # Drop queued jobs so stale crops don't burn the next quota window.
            drained = 0
            while True:
                try:
                    self._q.get_nowait()
                    drained += 1
                except queue.Empty:
                    break
            logger.warning("vlm_rate_limited — backing off 60s (drained=%d)", drained)
            return
        if not should_emit(verdict, min_confidence=job.min_confidence):
            with self._lock:
                self._stats["rejected"] += 1
                signals = [str(s).lower() for s in (verdict.signals or [])]
                if "unclear" in signals or not bool(getattr(verdict, "visible", True)):
                    self._stats["unclear"] += 1
            return
        evt = dict(job.event_skeleton)
        evt["confidence"] = round(float(verdict.confidence), 3)
        meta = dict(evt.get("metadata") or {})
        detection_method = "gemini_ocr" if job.rule == "plate_ocr" else "gemini_vlm"
        meta.update(
            {
                "detection_method": detection_method,
                "vlm_model": self._client.model,
                "vlm_latency_ms": round(float(verdict.latency_ms), 1),
                "vlm_confidence": round(float(verdict.confidence), 3),
                "vlm_signals": list(verdict.signals),
                "vlm_reason": verdict.reason_short,
                "confidence": round(float(verdict.confidence), 3),
            }
        )
        if job.rule == "plate_ocr" and verdict.plate_text:
            evt["plate_number"] = verdict.plate_text
            evt["plate_confidence"] = round(float(verdict.confidence), 3)
            meta["plate_number"] = verdict.plate_text
            meta["plate_confidence"] = round(float(verdict.confidence), 3)
            evt["event_type"] = str(evt.get("event_type") or "plate_detected")
            evt["event"] = evt["event_type"]
        else:
            evt["event_type"] = job.rule
            evt["event"] = job.rule
        evt["metadata"] = meta
        cb = self._emit
        if cb is None:
            logger.warning("vlm emit callback missing — dropping event")
            return
        try:
            cb(evt)
            with self._lock:
                self._stats["emitted"] += 1
        except Exception:
            logger.exception("vlm emit callback failed rule=%s", job.rule)


_QUEUE: VlmQueue | None = None


def get_vlm_queue() -> VlmQueue | None:
    return _QUEUE


def init_vlm_queue(client: GeminiClient, **kwargs: Any) -> VlmQueue:
    global _QUEUE
    q = VlmQueue(client, **kwargs)
    q.start()
    _QUEUE = q
    return q
