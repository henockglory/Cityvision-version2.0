"""Kalman peek_predict for overlay between inference frames."""

from citevision_ai.tracking.bytetrack import ByteTracker, KalmanBox


def test_peek_predict_does_not_mutate_state():
    kf = KalmanBox({"x": 10, "y": 20, "width": 40, "height": 30})
    kf.cx.v = 2.0
    before = kf.cx.x
    peek = kf.peek_predict(1.0)
    assert kf.cx.x == before
    assert peek["x"] > 10


def test_overlay_snapshot_includes_coasting():
    tracker = ByteTracker(min_hits=1, max_age=5)
    tracker.update([
        {
            "bbox": {"x": 100, "y": 100, "width": 50, "height": 80},
            "class_id": 2,
            "class_name": "car",
            "confidence": 0.9,
        },
    ])
    snap = tracker.overlay_snapshot(max_coast=2)
    assert len(snap) == 1
    assert snap[0]["class_name"] == "car"
