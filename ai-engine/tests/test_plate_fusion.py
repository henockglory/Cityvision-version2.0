"""Unit tests for Gemini + PaddleOCR plate fusion."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from citevision_ai.identity.plate_fusion import (
    PlateReading,
    fuse_plate_readings,
    reading_from_gemini_verdict,
)


def test_fuse_prefers_higher_confidence():
    gemini = PlateReading(text="ABCD1234", confidence=0.55, source="gemini")
    paddle = PlateReading(text="WXYZ9876", confidence=0.82, source="paddle")
    winner, meta = fuse_plate_readings(gemini, paddle)
    assert winner is not None
    assert winner.text == "WXYZ9876"
    assert winner.source == "paddle"
    assert meta["ocr_winner"] == "paddle"


def test_fuse_same_text_boosts_confidence():
    gemini = PlateReading(text="ABCD1234", confidence=0.6, source="gemini")
    paddle = PlateReading(text="ABCD1234", confidence=0.75, source="paddle")
    winner, meta = fuse_plate_readings(gemini, paddle)
    assert winner is not None
    assert winner.text == "ABCD1234"
    assert winner.source == "both"
    assert winner.confidence == 0.75
    assert meta["ocr_winner"] == "both"


def test_fuse_gemini_only():
    gemini = PlateReading(text="ZZZZ9999", confidence=0.7, source="gemini")
    winner, meta = fuse_plate_readings(gemini, None)
    assert winner is not None
    assert winner.text == "ZZZZ9999"
    assert meta["ocr_gemini"] == "ZZZZ9999"
    assert meta["ocr_paddle"] == ""


def test_fuse_empty_returns_none():
    winner, meta = fuse_plate_readings(None, None)
    assert winner is None
    assert meta["ocr_winner"] == ""


def test_reading_from_gemini_verdict():
    verdict = SimpleNamespace(
        plate_text=" ab-12 cd ",
        confidence=0.66,
        readable=True,
    )
    reading = reading_from_gemini_verdict(verdict)
    assert reading is not None
    assert reading.text == "AB12CD"
    assert reading.source == "gemini"


def test_run_paddle_on_jpeg_returns_none_when_backend_unloaded():
    from citevision_ai.identity import plate_fusion

    backend = MagicMock()
    backend.is_loaded = False
    with patch.object(plate_fusion, "get_paddle_backend", return_value=backend):
        assert plate_fusion.run_paddle_on_jpeg(b"\xff\xd8\xff") is None


def test_matches_composition_standard_and_custom():
    from citevision_ai.identity.plate_fusion import (
        matches_composition,
        set_plate_patterns,
        resolve_zone_plate_pattern,
    )

    assert matches_composition("AB12CD")
    assert not matches_composition("AB")
    fr = r"^[A-Z]{2}[0-9]{4}[A-Z]{2}$"
    assert matches_composition("AB1234CD", fr)
    assert not matches_composition("AB12CD", fr)

    set_plate_patterns(
        [
            {
                "id": "p1",
                "name": "FR",
                "mode": "custom",
                "regex": fr,
                "is_default": True,
            }
        ]
    )
    # Empty zone → org default
    assert resolve_zone_plate_pattern({}).pattern == fr
    # Explicit standard ignores org default
    assert (
        resolve_zone_plate_pattern(
            {"behavior_config": {"config": {"plate_pattern_id": "standard"}}}
        )
        is None
    )
    set_plate_patterns([])
