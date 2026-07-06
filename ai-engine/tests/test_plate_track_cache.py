"""Plate per-track cache and violation linking."""

from __future__ import annotations

import time

from citevision_ai.identity.plate import PlateIdentityEngine
from citevision_ai.pipeline import PipelineService


def test_remember_and_retrieve_plate_by_track() -> None:
    engine = PlateIdentityEngine(backend=object())  # type: ignore[arg-type]
    engine._remember_plate("cam-1", 7, "AB123CD", 0.91)
    got = engine.get_last_plate("cam-1", 7)
    assert got == ("AB123CD", 0.91)
    assert engine.get_last_plate("cam-1", 8) is None
    assert engine.get_last_plate("cam-2", 7) is None


def test_plate_cache_expires() -> None:
    engine = PlateIdentityEngine(backend=object())  # type: ignore[arg-type]
    engine._last_plate[("cam-1", 3)] = ("XY999ZZ", 0.8, 100.0)

    orig = time.monotonic
    try:
        time.monotonic = lambda: 200.0  # type: ignore[assignment]
        assert engine.get_last_plate("cam-1", 3, max_age_sec=45.0) is None
    finally:
        time.monotonic = orig  # type: ignore[assignment]


def test_link_speeding_uses_cached_plate_from_earlier_frame() -> None:
    linker = type("Linker", (), {})()
    linker.plate_engine = PlateIdentityEngine(backend=object())  # type: ignore[arg-type]
    linker.plate_engine._remember_plate("cam-1", 42, "FR123AB", 0.88)

    events = [
        {
            "event_type": "speeding",
            "track_id": 42,
            "camera_id": "cam-1",
            "metadata": {},
        },
    ]
    PipelineService._link_plates_to_violations(linker, "cam-1", events)

    assert events[0]["plate_number"] == "FR123AB"
    assert events[0]["plate_confidence"] == 0.88
    assert events[0]["metadata"]["plate_number"] == "FR123AB"


def test_same_frame_plate_still_preferred_over_cache() -> None:
    linker = type("Linker", (), {})()
    linker.plate_engine = PlateIdentityEngine(backend=object())  # type: ignore[arg-type]
    linker.plate_engine._remember_plate("cam-1", 5, "OLDPLATE", 0.5)

    events = [
        {
            "event_type": "plate_detected",
            "track_id": 5,
            "plate_number": "NEWPLATE",
            "plate_confidence": 0.95,
        },
        {
            "event_type": "speeding",
            "track_id": 5,
            "metadata": {},
        },
    ]
    PipelineService._link_plates_to_violations(linker, "cam-1", events)

    assert events[1]["plate_number"] == "NEWPLATE"
