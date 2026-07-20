"""Evidence abort counters — Sprint 1 remédiation (Décision 2 observability).

Transforms \"239 events / 0 alerts, cause floue\" into a readable distribution.
Thread-safe; process-local (reset on AI restart — intentional for session stats).

Terminal accounting (Tâche 3 Phase A):
  every capture *attempt* ends as exactly one of {complete, terminal_abort}.
  Probe rejects (IoU/align during correlate poll) are counted separately and do
  NOT enter the terminal sum — soft-accept / demo fallback may still succeed after.
"""
from __future__ import annotations

import logging
import threading
from collections import defaultdict
from typing import Any

logger = logging.getLogger(__name__)

# Canonical abort reasons (Sprint 1 / remédiation §5).
ABORT_ALIGN_TOO_WIDE = "align_too_wide"
ABORT_SCENE_GREEN = "scene_green"
ABORT_SUBJECT_EMPTY = "subject_empty"
ABORT_NO_SCENE = "no_scene"
ABORT_NO_CORRELATION = "no_correlation"
ABORT_CLIP_NOT_READY = "clip_not_ready"
ABORT_CLIP_NOT_READY_TIMEOUT = "clip_not_ready_timeout"
ABORT_NO_CLIP = "no_clip"
ABORT_QUALITY_OR_COLOR = "quality_or_color_check_failed"
ABORT_FRIGATE_DISABLED = "frigate_disabled"
# Probe / accept-gate reasons (counted in probe_rejects; may be followed by soft-accept).
ABORT_IOU_REJECT = "iou_reject"
ABORT_ALIGN_REJECT = "align_reject"
ABORT_STALE_MATCH = "stale_match"
ABORT_NO_FRIGATE_BBOX = "no_frigate_bbox"

_lock = threading.Lock()
# (event_type or "*", reason) -> count  (terminal aborts only)
_counts: dict[tuple[str, str], int] = defaultdict(int)
# camera_id[:8] -> {reason: count}
_by_camera: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
# Probe rejects during correlate poll (non-terminal)
_probe: dict[tuple[str, str], int] = defaultdict(int)
_attempts: dict[str, int] = defaultdict(int)
_completes: dict[str, int] = defaultdict(int)


def record_attempt(*, camera_id: str = "", event_type: str = "") -> None:
    et = (event_type or "*").strip() or "*"
    with _lock:
        _attempts[et] += 1


def record_complete(*, camera_id: str = "", event_type: str = "", event_id: str = "") -> None:
    et = (event_type or "*").strip() or "*"
    with _lock:
        _completes[et] += 1
    logger.info(
        "evidence_complete %s",
        {
            "camera_id": (camera_id or "")[:8],
            "event_type": et,
            "event_id": (event_id or "")[:24],
            "completes": _completes[et],
        },
    )


def record_probe_reject(
    reason: str,
    *,
    camera_id: str = "",
    event_type: str = "",
    extra: dict[str, Any] | None = None,
) -> None:
    """Non-terminal reject during correlate (IoU/align). Soft-accept may still win."""
    et = (event_type or "*").strip() or "*"
    reason = (reason or "unknown").strip() or "unknown"
    with _lock:
        _probe[(et, reason)] += 1
        n = _probe[(et, reason)]
    payload = {
        "probe_reject": reason,
        "camera_id": (camera_id or "")[:8] or "unknown",
        "event_type": et,
        "count_for_reason": n,
    }
    if extra:
        payload.update(extra)
    logger.warning("evidence_probe_reject %s", payload)


def record_abort(
    reason: str,
    *,
    camera_id: str = "",
    event_type: str = "",
    event_id: str = "",
    extra: dict[str, Any] | None = None,
) -> None:
    """Increment terminal abort counters and emit a structured warning log line."""
    et = (event_type or "*").strip() or "*"
    cam = (camera_id or "")[:8] or "unknown"
    reason = (reason or "unknown").strip() or "unknown"
    with _lock:
        _counts[(et, reason)] += 1
        _by_camera[cam][reason] += 1
        total_et = sum(v for (e, _), v in _counts.items() if e == et)
    payload = {
        "abort_reason": reason,
        "camera_id": cam,
        "event_type": et,
        "event_id": (event_id or "")[:24],
        "count_for_reason": _counts[(et, reason)],
        "count_for_event_type": total_et,
    }
    if extra:
        payload.update(extra)
    logger.warning("evidence_abort %s", payload)


def snapshot() -> dict[str, Any]:
    """Return a JSON-serialisable snapshot of abort counters."""
    with _lock:
        by_type: dict[str, dict[str, int]] = defaultdict(dict)
        for (et, reason), n in _counts.items():
            by_type[et][reason] = n
        by_cam = {cam: dict(reasons) for cam, reasons in _by_camera.items()}
        probe_by_type: dict[str, dict[str, int]] = defaultdict(dict)
        for (et, reason), n in _probe.items():
            probe_by_type[et][reason] = n
        attempts = dict(_attempts)
        completes = dict(_completes)
        terminal_aborts = {et: sum(reasons.values()) for et, reasons in by_type.items()}
        # Reconciliation: every attempt → complete XOR terminal abort
        recon: dict[str, Any] = {}
        all_ets = set(attempts) | set(completes) | set(terminal_aborts)
        ok_all = True
        for et in sorted(all_ets):
            a = attempts.get(et, 0)
            c = completes.get(et, 0)
            t = terminal_aborts.get(et, 0)
            balanced = a == c + t
            if not balanced:
                ok_all = False
            recon[et] = {
                "attempts": a,
                "completes": c,
                "terminal_aborts": t,
                "balanced": balanced,
            }
        return {
            "by_event_type": dict(by_type),
            "by_camera": by_cam,
            "probe_rejects": dict(probe_by_type),
            "attempts": attempts,
            "completes": completes,
            "terminal_aborts": terminal_aborts,
            "reconciliation": {"ok": ok_all, "by_event_type": recon},
            "total": sum(_counts.values()),
        }


def reset() -> None:
    with _lock:
        _counts.clear()
        _by_camera.clear()
        _probe.clear()
        _attempts.clear()
        _completes.clear()
