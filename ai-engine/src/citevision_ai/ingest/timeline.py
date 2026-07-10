from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass(frozen=True)
class FrameTimeline:
    """Synthetic clock for offline segment replay (not live wall clock)."""

    monotonic: float
    wall: float
    video_pts: float
    iso_timestamp: str | None = None

    @classmethod
    def from_segment_start(
        cls,
        segment_start_mono: float,
        segment_start_wall: float,
        video_pts: float,
    ) -> FrameTimeline:
        iso = datetime.fromtimestamp(segment_start_wall + video_pts, tz=timezone.utc).isoformat()
        return cls(
            monotonic=segment_start_mono + video_pts,
            wall=segment_start_wall + video_pts,
            video_pts=video_pts,
            iso_timestamp=iso,
        )


@dataclass(frozen=True)
class SegmentCaptureContext:
    """Metadata linking an event to its source segment file."""

    segment_path: str
    cycle_id: str
    frame_index: int
    frame_pts: float
    segment_start_wall: float = 0.0
    ingest_fps: float = 12.0
