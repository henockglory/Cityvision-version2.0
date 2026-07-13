"""Timeline alignment between IA wall clock and Frigate event timestamps (demo go2rtc loops)."""

from __future__ import annotations

from typing import Any

# Frigate on looped go2rtc often exposes stream-relative seconds; wall clock is ~1.7e9+.
_STREAM_CLOCK_MAX = 1_000_000_000.0


def frigate_event_time_candidates(ev: dict[str, Any]) -> list[float]:
    """Collect comparable timestamps from a Frigate event."""
    out: list[float] = []
    for key in ("frame_time", "start_time", "end_time"):
        v = ev.get(key)
        if isinstance(v, (int, float)):
            out.append(float(v))
    data = ev.get("data") if isinstance(ev.get("data"), dict) else {}
    for pt in data.get("path_data") or []:
        if not isinstance(pt, (list, tuple)) or len(pt) < 2:
            continue
        ts = pt[1]
        if isinstance(ts, (int, float)):
            out.append(float(ts))
    return out


def min_time_delta(anchor: float, ev: dict[str, Any]) -> float:
    candidates = frigate_event_time_candidates(ev)
    if not candidates:
        return 1e18
    return min(abs(t - anchor) for t in candidates)


def learn_clock_offset(
    offsets: dict[str, float],
    camera_id: str,
    ia_anchor: float,
    frigate_ts: float,
    *,
    ema_alpha: float = 0.35,
) -> float:
    """Estimate IA_wall - Frigate_ts for looped demo streams; returns learned offset."""
    sample = float(ia_anchor) - float(frigate_ts)
    prev = offsets.get(camera_id)
    if prev is None:
        offsets[camera_id] = sample
    else:
        offsets[camera_id] = prev * (1.0 - ema_alpha) + sample * ema_alpha
    return offsets[camera_id]


def aligned_anchor(offsets: dict[str, float], camera_id: str, anchor: float) -> float:
    off = offsets.get(camera_id)
    if off is None:
        return anchor
    return float(anchor) - float(off)


def frigate_times_look_stream_relative(events: list[dict[str, Any]]) -> bool:
    """True when Frigate event times look like go2rtc loop positions, not unix epoch."""
    samples: list[float] = []
    for ev in events[:12]:
        samples.extend(frigate_event_time_candidates(ev))
    if not samples:
        return False
    return max(samples) < _STREAM_CLOCK_MAX


def wall_clock_skewed_from_frigate(anchor: float, events: list[dict[str, Any]]) -> bool:
    """True when IA wall anchor cannot match Frigate times within loose window."""
    if not events:
        return False
    samples: list[float] = []
    for ev in events[:8]:
        samples.extend(frigate_event_time_candidates(ev))
    if not samples:
        return False
    return min(abs(anchor - t) for t in samples) > 3600.0
