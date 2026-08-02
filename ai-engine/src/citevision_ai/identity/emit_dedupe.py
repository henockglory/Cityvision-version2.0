"""Short-TTL dedupe for parallel identity emits (face / plate)."""
from __future__ import annotations

import threading
import time

_lock = threading.Lock()
_seen: dict[str, float] = {}
_sources: dict[str, tuple[float, str]] = {}
_DEFAULT_TTL = 30.0


def should_skip_emit(key: str, *, ttl_sec: float = _DEFAULT_TTL, source: str = "") -> bool:
    """True if this key was emitted recently (skip duplicate)."""
    k = str(key or "").strip()
    if not k:
        return False
    now = time.time()
    with _lock:
        ts = _seen.get(k)
        if ts is not None and now - ts < ttl_sec:
            return True
        _seen[k] = now
        if source:
            _sources[k] = (now, str(source))
        stale = [sk for sk, st in _seen.items() if now - st > ttl_sec * 2]
        for sk in stale:
            _seen.pop(sk, None)
            _sources.pop(sk, None)
        return False


def peek_prior_source(key: str, *, ttl_sec: float = _DEFAULT_TTL) -> str | None:
    """Return the detection_method of a recent emit on this key, if any."""
    k = str(key or "").strip()
    if not k:
        return None
    now = time.time()
    with _lock:
        prior = _sources.get(k)
        if prior and now - prior[0] < ttl_sec:
            return str(prior[1])
    return None


def merged_detection_method(key: str, source: str, *, ttl_sec: float = _DEFAULT_TTL) -> str:
    """If another source emitted recently, return 'both'; else return source."""
    prior = peek_prior_source(key, ttl_sec=ttl_sec)
    src = str(source or "").strip() or "unknown"
    if prior and prior != src:
        return "both"
    return src


def face_dedupe_key(
    camera_id: str,
    event_type: str,
    *,
    zone_id: str = "",
    frigate_event_id: str = "",
    track_id: int | None = None,
) -> str:
    tid = str(track_id) if track_id is not None and int(track_id) >= 0 else ""
    fe = (frigate_event_id or "")[:24]
    if fe:
        return f"face:{camera_id}:{zone_id}:{event_type}:fe:{fe}"
    return f"face:{camera_id}:{zone_id}:{event_type}:tr:{tid}"


def plate_dedupe_key(camera_id: str, plate_text: str) -> str:
    return f"plate:{camera_id}:{plate_text}"
