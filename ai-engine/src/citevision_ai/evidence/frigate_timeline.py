"""Timeline alignment between IA wall clock and Frigate event timestamps (demo go2rtc loops)."""

from __future__ import annotations

from typing import Any

# Frigate on looped go2rtc often exposes stream-relative seconds; wall clock is ~1.7e9+.
_STREAM_CLOCK_MAX = 1_000_000_000.0


def demo_loop_absolute_align_ok(align_delta_sec: float, max_align_sec: float) -> bool:
    """Hard time gate — never bypassed by soft-accept / bound-id trust (demo_loop_guard)."""
    try:
        return float(align_delta_sec) <= float(max_align_sec)
    except (TypeError, ValueError):
        return False


def same_demo_loop_cycle(
    ia_ts: float,
    frigate_ts: float,
    loop_sec: float,
    *,
    boundary_slack_sec: float = 2.0,
) -> bool:
    """True when IA and Frigate timestamps fall in the same demo-loop iteration.

    Rejects pairings separated by ~k full loops (k≥1) even if modulo positions
    look similar — the classic stale Frigate event reuse on looping go2rtc.

    Important: a small wall-clock delta that straddles a ``floor(ts/loop)``
    boundary is still the same capture moment — do **not** reject via floor
    equality (that falsely aborted ~1s-aligned pairs during T1).
    """
    try:
        loop = float(loop_sec)
        a = float(ia_ts)
        b = float(frigate_ts)
    except (TypeError, ValueError):
        return True
    if loop <= 1.0:
        return True
    delta = abs(a - b)
    # Nearly one full loop or more ⇒ different iteration.
    if delta >= max(loop - max(0.0, boundary_slack_sec), loop * 0.95):
        return False
    return True


def best_frigate_ts(ev: dict[str, Any]) -> float | None:
    """Prefer start_time / frame_time for loop-cycle comparison."""
    for key in ("frame_time", "start_time", "end_time"):
        v = ev.get(key)
        if isinstance(v, (int, float)):
            return float(v)
    cands = frigate_event_time_candidates(ev)
    return cands[0] if cands else None


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
