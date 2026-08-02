"""Red-light vote strategies for Frigate bridge + local HSV synergy."""
from __future__ import annotations

import os
import threading
import time

_VALID_VOTE_MODES = frozenset({"strict_and", "lf_or_g"})
_LOCAL_EMIT_TTL_SEC = 60.0
_local_emit_lock = threading.Lock()
_local_emit_seen: dict[str, float] = {}


def red_light_vote_mode(default: str = "strict_and") -> str:
    raw = (os.environ.get("RED_LIGHT_VOTE_MODE") or default).strip().lower()
    return raw if raw in _VALID_VOTE_MODES else default


def local_frigate_would_emit(*, hsv_gate_red: bool, frigate_in_obs_zone: bool) -> bool:
    """True when local HSV gate is red and Frigate reports vehicle in observation zone."""
    if red_light_vote_mode() != "lf_or_g":
        return False
    return bool(hsv_gate_red and frigate_in_obs_zone)


def gemini_blocks_local_emit(*, gemini_violation: bool, gemini_confidence: float, block_threshold: float = 0.75) -> bool:
    """Q56 shadow hook: high-confidence Gemini infirmation can veto local-only path."""
    if red_light_vote_mode() != "lf_or_g":
        return False
    veto = str(os.environ.get("RED_LIGHT_GEMINI_VETO", "")).strip().lower() in ("1", "true", "yes")
    if not veto:
        return False
    return (not gemini_violation) and gemini_confidence >= block_threshold


def mark_local_emitted(frigate_event_id: str) -> None:
    key = str(frigate_event_id or "").strip()
    if not key:
        return
    now = time.time()
    with _local_emit_lock:
        _local_emit_seen[key] = now
        stale = [k for k, ts in _local_emit_seen.items() if now - ts > _LOCAL_EMIT_TTL_SEC]
        for k in stale:
            _local_emit_seen.pop(k, None)


def local_already_emitted(frigate_event_id: str) -> bool:
    key = str(frigate_event_id or "").strip()
    if not key:
        return False
    now = time.time()
    with _local_emit_lock:
        ts = _local_emit_seen.get(key)
        if ts is None:
            return False
        if now - ts > _LOCAL_EMIT_TTL_SEC:
            _local_emit_seen.pop(key, None)
            return False
        return True
