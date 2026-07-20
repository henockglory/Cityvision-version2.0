"""Segment cycle worker — archived (Sprint 4).

Full implementation lives in ``_archive/segment_mode/segment_cycle_worker.py``.
Live path is RTSP/Frigate only; ``SEGMENT_MODE_CAMERA_IDS`` must stay empty.
"""

from __future__ import annotations

from typing import Any, Callable


class SegmentCycleWorker:
    """Stub: constructing this worker is a configuration error."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        raise RuntimeError(
            "SegmentCycleWorker is archived (Sprint 4). "
            "Unset SEGMENT_MODE_CAMERA_IDS and use RTSP/Frigate ingest. "
            "Historical code: _archive/segment_mode/segment_cycle_worker.py"
        )

    def start(self) -> None:  # pragma: no cover
        raise RuntimeError("SegmentCycleWorker is archived")

    def stop(self) -> None:  # pragma: no cover
        return None

    def status(self) -> dict[str, Any]:  # pragma: no cover
        return {"mode": "segment_archived", "running": False}

    @property
    def is_running(self) -> bool:  # pragma: no cover
        return False


# Kept for type checks / isinstance against accidental leftover instances.
__all__ = ["SegmentCycleWorker"]
