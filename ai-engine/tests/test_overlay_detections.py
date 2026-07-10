"""Overlay detection filter — active tracks only, no Kalman ghosts."""

from citevision_ai.pipeline import build_overlay_detections


def test_overlay_excludes_coasting_tracks():
    tracks = [
        {
            "track_id": 1,
            "class_id": 2,
            "class_name": "car",
            "confidence": 0.9,
            "time_since_update": 0,
            "bbox": {"x": 100, "y": 100, "width": 200, "height": 120},
        },
        {
            "track_id": 2,
            "class_id": 0,
            "class_name": "person",
            "confidence": 0.85,
            "time_since_update": 3,
            "bbox": {"x": 300, "y": 300, "width": 80, "height": 160},
        },
    ]
    out = build_overlay_detections(tracks, 1920, 1080)
    assert len(out) == 1
    assert out[0]["track_id"] == 1


def test_overlay_allows_brief_coast():
    tracks = [
        {
            "track_id": 2,
            "class_id": 0,
            "class_name": "person",
            "confidence": 0.85,
            "time_since_update": 1,
            "bbox": {"x": 300, "y": 300, "width": 80, "height": 160},
        },
    ]
    assert len(build_overlay_detections(tracks, 1920, 1080, max_coast=0)) == 0
    assert len(build_overlay_detections(tracks, 1920, 1080, max_coast=2)) == 1


def test_overlay_min_confidence_and_area():
    tracks = [
        {
            "track_id": 1,
            "class_id": 0,
            "class_name": "person",
            "confidence": 0.3,
            "time_since_update": 0,
            "bbox": {"x": 10, "y": 10, "width": 50, "height": 80},
        },
        {
            "track_id": 2,
            "class_id": 2,
            "class_name": "car",
            "confidence": 0.75,
            "time_since_update": 0,
            "bbox": {"x": 500, "y": 400, "width": 180, "height": 100},
        },
    ]
    out = build_overlay_detections(tracks, 1920, 1080)
    assert len(out) == 1
    assert out[0]["track_id"] == 2
