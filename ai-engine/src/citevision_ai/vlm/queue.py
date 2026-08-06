"""Async bounded queue for Gemini VLM jobs — never blocks RTSP infer thread."""
from __future__ import annotations

import logging
import os
import queue
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from citevision_ai.vlm.gemini_client import GeminiClient, _CABIN_RULES, should_emit

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
    shadow_only: bool = False
    paddle_plate_text: str = ""
    paddle_plate_confidence: float = 0.0


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
            "cabin_ignored": 0,
            "unclear": 0,
            "rate_limited": 0,
            "shadow_logged": 0,
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
        plate_fusion_meta: dict[str, Any] = {}
        fused_plate_text = ""
        fused_plate_conf = 0.0
        if job.rule == "plate_ocr":
            from citevision_ai.identity.plate_fusion import (
                PlateReading,
                fuse_plate_readings,
                reading_from_gemini_verdict,
            )

            paddle_hint = None
            if job.paddle_plate_text:
                paddle_hint = PlateReading(
                    text=str(job.paddle_plate_text),
                    confidence=float(job.paddle_plate_confidence or 0.0),
                    source="paddle",
                )
            winner, plate_fusion_meta = fuse_plate_readings(
                reading_from_gemini_verdict(verdict),
                paddle_hint,
            )
            if winner and float(winner.confidence) >= float(job.min_confidence):
                fused_plate_text = winner.text
                fused_plate_conf = float(winner.confidence)
            emit_ok = bool(fused_plate_text)
        else:
            emit_ok = should_emit(verdict, min_confidence=job.min_confidence)

        red_light_hsv_override = False
        if not emit_ok and job.rule == "red_light_violation":
            evt0 = job.event_skeleton if isinstance(job.event_skeleton, dict) else {}
            meta0 = evt0.get("metadata") if isinstance(evt0.get("metadata"), dict) else {}
            hsv_values = {
                str(meta0.get("hsv_light_state") or "").lower().strip(),
                str(meta0.get("hsv_raw") or "").lower().strip(),
                str(meta0.get("hsv_stable") or "").lower().strip(),
            }
            if str(meta0.get("bridge_source") or "").lower() == "frigate" and "red" in hsv_values:
                emit_ok = True
                red_light_hsv_override = True
                logger.info(
                    "vlm_red_light_hsv_override frigate_event=%s reason_short=%s",
                    str(evt0.get("frigate_event_id") or "")[:12],
                    (getattr(verdict, "reason_short", "") or "")[:120],
                )

        if not emit_ok:
            reason = (getattr(verdict, "reason_short", "") or "")[:120]
            reject_reason = "low_confidence"
            cabin_no = (
                job.rule in _CABIN_RULES
                and not bool(getattr(verdict, "violation", False))
                and not getattr(verdict, "error", "")
            )
            if cabin_no:
                with self._lock:
                    self._stats["cabin_ignored"] += 1
                logger.info(
                    "vlm_cabin_no rule=%s conf=%.2f reason_short=%s",
                    job.rule,
                    float(getattr(verdict, "confidence", 0.0) or 0.0),
                    reason,
                )
                return
            with self._lock:
                self._stats["rejected"] += 1
                if job.rule not in _CABIN_RULES:
                    signals = [str(s).lower() for s in (verdict.signals or [])]
                    if "unclear" in signals or not bool(getattr(verdict, "visible", True)):
                        self._stats["unclear"] += 1
            if job.rule in _CABIN_RULES:
                reject_reason = str(getattr(verdict, "error", "") or "error")
            elif job.rule == "plate_ocr":
                reject_reason = "plate_fusion_empty"
            elif not bool(getattr(verdict, "visible", True)):
                reject_reason = "visible"
            elif "unclear" in {str(s).lower() for s in (verdict.signals or [])}:
                reject_reason = "unclear"
            logger.info(
                "vlm_reject rule=%s reason=%s violation=%s visible=%s conf=%.2f min=%.2f "
                "reason_short=%s signals=%s err=%s fusion=%s",
                job.rule,
                reject_reason,
                bool(getattr(verdict, "violation", False)),
                bool(getattr(verdict, "visible", False)),
                float(getattr(verdict, "confidence", 0.0) or 0.0),
                float(job.min_confidence),
                reason,
                list(getattr(verdict, "signals", None) or [])[:6],
                getattr(verdict, "error", "") or "",
                plate_fusion_meta if job.rule == "plate_ocr" else "",
            )
            try:
                from citevision_ai.observability.rule_blockers import blockers
                evt0 = job.event_skeleton if isinstance(job.event_skeleton, dict) else {}
                meta0 = evt0.get("metadata") if isinstance(evt0.get("metadata"), dict) else {}
                blockers.note(
                    "vlm_reject",
                    rule=job.rule,
                    violation=bool(getattr(verdict, "violation", False)),
                    visible=bool(getattr(verdict, "visible", False)),
                    reason_short=reason,
                    reject_reason=reject_reason,
                    event_id=evt0.get("event_id"),
                    frigate_event_id=evt0.get("frigate_event_id"),
                    camera_id=evt0.get("camera_id"),
                    zone_id=evt0.get("zone_id"),
                    bbox_ts=evt0.get("bbox_ts"),
                    bbox=evt0.get("bbox"),
                    hsv_light_state=meta0.get("hsv_light_state"),
                    hsv_raw=meta0.get("hsv_raw"),
                    hsv_stable=meta0.get("hsv_stable"),
                )
            except Exception:
                pass
            return
        if job.rule == "red_light_violation":
            from citevision_ai.road_enforcement.red_light_vote import (
                local_already_emitted,
                red_light_vote_mode,
            )
            fe_id = str(job.event_skeleton.get("frigate_event_id") or "")
            if red_light_vote_mode() == "lf_or_g" and local_already_emitted(fe_id):
                with self._lock:
                    self._stats["rejected"] += 1
                logger.info(
                    "vlm_skip rule=%s frigate_event=%s reason=lf_or_g_local_already_emitted",
                    job.rule, fe_id[:12],
                )
                return
        shadow_env = str(os.environ.get("GEMINI_SHADOW_MODE", "")).strip().lower() in (
            "1", "true", "yes",
        )
        if job.shadow_only or shadow_env:
            with self._lock:
                self._stats["shadow_logged"] += 1
            logger.info(
                "vlm_shadow rule=%s violation=%s visible=%s conf=%.2f (no emit)",
                job.rule,
                bool(getattr(verdict, "violation", False)),
                bool(getattr(verdict, "visible", False)),
                float(getattr(verdict, "confidence", 0.0) or 0.0),
            )
            try:
                from citevision_ai.observability.rule_blockers import blockers
                blockers.note(
                    "vlm_shadow",
                    rule=job.rule,
                    violation=bool(getattr(verdict, "violation", False)),
                    visible=bool(getattr(verdict, "visible", False)),
                    reason_short=(getattr(verdict, "reason_short", "") or "")[:120],
                )
            except Exception:
                pass
            return
        evt = dict(job.event_skeleton)
        evt["confidence"] = round(float(verdict.confidence), 3)
        meta = dict(evt.get("metadata") or {})
        detection_method = "gemini_paddle_fusion" if job.rule == "plate_ocr" else "gemini_vlm"
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
        if red_light_hsv_override:
            meta["vlm_hsv_override"] = True
            meta["vlm_original_violation"] = bool(getattr(verdict, "violation", False))
            meta["vlm_original_reason"] = verdict.reason_short
            evt["confidence"] = max(float(evt.get("confidence") or 0.0), float(job.min_confidence))
            meta["confidence"] = evt["confidence"]
        if job.rule == "plate_ocr":
            meta.update(plate_fusion_meta)
            if fused_plate_text:
                evt["plate_number"] = fused_plate_text
                evt["plate_confidence"] = round(fused_plate_conf, 3)
                meta["plate_number"] = fused_plate_text
                meta["plate_confidence"] = round(fused_plate_conf, 3)
                evt["confidence"] = round(fused_plate_conf, 3)
                meta["confidence"] = round(fused_plate_conf, 3)
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
