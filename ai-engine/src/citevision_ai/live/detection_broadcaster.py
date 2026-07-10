from __future__ import annotations

import asyncio
import threading
from typing import Any


class DetectionBroadcaster:
    """Thread-safe fan-out of detection payloads to SSE subscribers."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._subscribers: dict[str, set[asyncio.Queue]] = {}
        self._loop: asyncio.AbstractEventLoop | None = None

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def subscribe(self, camera_id: str) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=32)
        with self._lock:
            self._subscribers.setdefault(camera_id, set()).add(q)
        return q

    def unsubscribe(self, camera_id: str, q: asyncio.Queue) -> None:
        with self._lock:
            subs = self._subscribers.get(camera_id)
            if not subs:
                return
            subs.discard(q)
            if not subs:
                del self._subscribers[camera_id]

    def publish(self, camera_id: str, payload: dict[str, Any]) -> None:
        loop = self._loop
        if loop is None or not loop.is_running():
            return
        with self._lock:
            subs = list(self._subscribers.get(camera_id, ()))
        for q in subs:
            loop.call_soon_threadsafe(self._enqueue, q, payload)

    @staticmethod
    def _enqueue(q: asyncio.Queue, payload: dict[str, Any]) -> None:
        try:
            q.put_nowait(payload)
        except asyncio.QueueFull:
            try:
                q.get_nowait()
            except asyncio.QueueEmpty:
                pass
            try:
                q.put_nowait(payload)
            except asyncio.QueueFull:
                pass
