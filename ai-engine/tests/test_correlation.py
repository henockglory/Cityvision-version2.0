from citevision_ai.analytics.correlation import CorrelationEngine


def test_correlation_match():
    engine = CorrelationEngine(default_window_seconds=60)
    engine.record_exit("cam-a", 1, "person", "2026-06-12T12:00:00+00:00")
    matches = engine.find_matches(
        "cam-b",
        2,
        "person",
        source_camera_id="cam-a",
        timestamp="2026-06-12T12:00:30+00:00",
    )
    assert len(matches) == 1
    assert matches[0]["event_type"] == "correlation_match"


def test_correlate_entry_multi_cam():
    engine = CorrelationEngine(default_window_seconds=60)
    engine.record_exit("cam-a", 1, "person", "2026-06-12T12:00:00+00:00")
    matches = engine.correlate_entry(
        "cam-b",
        2,
        "person",
        timestamp="2026-06-12T12:00:30+00:00",
    )
    assert len(matches) == 1
    assert matches[0]["metadata"]["source_camera_id"] == "cam-a"
