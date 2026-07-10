"""Burn-in overlay drawing."""

import numpy as np

from citevision_ai.live.burn_in import draw_overlay_boxes


def test_draw_overlay_boxes():
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    dets = [
        {
            "track_id": 1,
            "class_name": "car",
            "confidence": 0.9,
            "bbox": {"x": 100, "y": 100, "width": 80, "height": 60},
        },
    ]
    out = draw_overlay_boxes(frame, dets)
    assert out.shape == frame.shape
    assert not np.array_equal(out, frame)
