from citevision_ai.tracking.bytetrack import ByteTracker


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
