"""In-process counters for 1-hit / Frigate→Gemini blocker diagnosis."""
from __future__ import annotations

import threading
import time
from collections import Counter, deque
from typing import Any


class RuleBlockers:
    """Thread-safe counters + recent structured events (no DB writes)."""

    def __init__(self, *, ring_size: int = 50) -> None:
        self._lock = threading.Lock()
        self._counters: Counter[str] = Counter()
        self._ring: deque[dict[str, Any]] = deque(maxlen=max(10, int(ring_size)))
        self._reject_reasons: Counter[str] = Counter()

    def inc(self, key: str, n: int = 1) -> None:
        with self._lock:
            self._counters[str(key)] += int(n)

    def note(self, kind: str, **fields: Any) -> None:
        entry = {"ts": time.time(), "kind": str(kind), **fields}
        with self._lock:
            self._ring.append(entry)
            self._counters[str(kind)] += 1
            reason = fields.get("reason_short") or fields.get("reason")
            if reason:
                self._reject_reasons[str(reason)[:120]] += 1

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "counters": dict(self._counters),
                "vlm_reject_reason_top": self._reject_reasons.most_common(15),
                "recent": list(self._ring),
            }

    def reset(self) -> None:
        with self._lock:
            self._counters.clear()
            self._ring.clear()
            self._reject_reasons.clear()


blockers = RuleBlockers()
