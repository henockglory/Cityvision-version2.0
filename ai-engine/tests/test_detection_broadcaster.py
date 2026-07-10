"""DetectionBroadcaster fan-out for SSE."""

import asyncio

import pytest

from citevision_ai.live.detection_broadcaster import DetectionBroadcaster


@pytest.mark.asyncio
async def test_broadcaster_publish_to_subscriber():
    bc = DetectionBroadcaster()
    loop = asyncio.get_running_loop()
    bc.bind_loop(loop)
    q = bc.subscribe("cam-1")
    payload = {"camera_id": "cam-1", "frame_id": 7}
    bc.publish("cam-1", payload)
    received = await asyncio.wait_for(q.get(), timeout=1.0)
    assert received["frame_id"] == 7
    bc.unsubscribe("cam-1", q)
