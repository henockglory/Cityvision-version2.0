from citevision_ai.tracking.bytetrack import ByteTracker, KalmanBox, _KalmanCV1D


def _det(x, y, conf=0.9, cid=0, name="person", w=50, h=100):
    return {
        "class_id": cid,
        "class_name": name,
        "confidence": conf,
        "bbox": {"x": x, "y": y, "width": w, "height": h},
    }


def test_bytetrack_assigns_ids():
    tracker = ByteTracker(min_hits=1)
    dets = [
        {
            "class_id": 0,
            "class_name": "person",
            "confidence": 0.9,
            "bbox": {"x": 10, "y": 10, "width": 50, "height": 100},
        }
    ]
    tracks = tracker.update(dets)
    assert len(tracks) >= 1
    assert tracks[0].track_id >= 1


def test_bytetrack_persists_track():
    tracker = ByteTracker(min_hits=1, iou_threshold=0.1)
    dets = [
        {
            "class_id": 0,
            "class_name": "person",
            "confidence": 0.9,
            "bbox": {"x": 10, "y": 10, "width": 50, "height": 100},
        }
    ]
    t1 = tracker.update(dets)
    t2 = tracker.update(dets)
    assert t1[0].track_id == t2[0].track_id


def test_kalman_1d_tracks_constant_velocity():
    kf = _KalmanCV1D(0.0)
    # Feed a steadily moving measurement; the filter should learn velocity and
    # its prediction should track the trend rather than lag arbitrarily.
    for i in range(1, 15):
        kf.predict()
        kf.update(float(i * 10))
    nxt = kf.predict()
    assert 130 < nxt < 170  # ~ next step around 150


def test_kalmanbox_predict_update_roundtrip():
    box = KalmanBox({"x": 10, "y": 20, "width": 40, "height": 60})
    box.predict()
    out = box.update({"x": 12, "y": 22, "width": 40, "height": 60})
    assert out["width"] > 0 and out["height"] > 0
    assert 9 < out["x"] < 13


def test_two_stage_recovers_low_confidence():
    # High-confidence first frame creates the track; a subsequent low-confidence
    # detection (below high_thresh, above low_thresh) should still update it
    # instead of being dropped or spawning a duplicate.
    tracker = ByteTracker(min_hits=1, high_thresh=0.5, low_thresh=0.1, iou_threshold=0.1)
    t1 = tracker.update([_det(10, 10, conf=0.9)])
    tid = t1[0].track_id
    t2 = tracker.update([_det(12, 11, conf=0.3)])  # low confidence
    ids = [t.track_id for t in t2]
    assert tid in ids
    assert len([t for t in t2 if t.track_id == tid]) == 1


def test_low_confidence_does_not_spawn_track():
    tracker = ByteTracker(min_hits=1, high_thresh=0.5, low_thresh=0.1)
    tracks = tracker.update([_det(10, 10, conf=0.3)])  # only low-confidence
    assert tracks == []
