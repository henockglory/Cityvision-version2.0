"""Unit tests for Gemini VLM client + queue (mocked HTTP — no network in CI)."""
from __future__ import annotations

import json
import threading
import time
from unittest.mock import MagicMock, patch

import pytest

from citevision_ai.vlm.gemini_client import (
    GeminiClient,
    GeminiVerdict,
    _extract_json_object,
    should_emit,
)
from citevision_ai.vlm.queue import VlmJob, VlmQueue


def test_extract_json_object_plain():
    data = _extract_json_object('{"violation": true, "rule": "seatbelt_violation"}')
    assert data is not None
    assert data["violation"] is True


def test_extract_json_object_fenced():
    data = _extract_json_object('```json\n{"violation": false, "rule": "x"}\n```')
    assert data is not None
    assert data["violation"] is False


def test_should_emit_cabin_ignores_visible_and_unclear():
    """Cabine: oui/non sur violation + confiance — pas de gate visible/unclear."""
    assert should_emit(
        GeminiVerdict(
            violation=True, rule="seatbelt_violation", confidence=0.9,
            visible=False, reason_short="ok", signals=[], latency_ms=10, raw_ok=True,
        ),
        min_confidence=0.45,
    )
    assert should_emit(
        GeminiVerdict(
            violation=True, rule="phone_use_violation", confidence=0.8,
            visible=False, reason_short="ok", signals=["unclear"], latency_ms=10, raw_ok=True,
        ),
        min_confidence=0.45,
    )
    assert not should_emit(
        GeminiVerdict(
            violation=False, rule="seatbelt_violation", confidence=0.9,
            visible=True, reason_short="ok", signals=[], latency_ms=10, raw_ok=True,
        ),
        min_confidence=0.45,
    )
    assert not should_emit(
        GeminiVerdict(
            violation=True, rule="seatbelt_violation", confidence=0.2,
            visible=True, reason_short="ok", signals=[], latency_ms=10, raw_ok=True,
        ),
        min_confidence=0.45,
    )
    assert not should_emit(
        GeminiVerdict(
            violation=True, rule="seatbelt_violation", confidence=0.9,
            visible=True, reason_short="ok", signals=[], latency_ms=10, raw_ok=False,
            error="http",
        ),
        min_confidence=0.45,
    )


def test_should_emit_fail_closed_non_cabin():
    """Feu/plaque/face: gate visible + unclear inchangé."""
    assert not should_emit(
        GeminiVerdict(
            violation=True, rule="red_light_violation", confidence=0.9,
            visible=False, reason_short="", signals=[], latency_ms=1, raw_ok=True,
        ),
        min_confidence=0.45,
    )
    assert not should_emit(
        GeminiVerdict(
            violation=True, rule="red_light_violation", confidence=0.9,
            visible=True, reason_short="", signals=["unclear"], latency_ms=1, raw_ok=True,
        ),
        min_confidence=0.45,
    )


def test_judge_jpeg_parses_mock_response():
    client = GeminiClient("fake-key", model="gemini-3.6-flash", timeout=5.0)
    payload = {
        "candidates": [
            {
                "content": {
                    "parts": [
                        {
                            "text": json.dumps(
                                {
                                    "violation": True,
                                    "rule": "seatbelt_violation",
                                    "confidence": 0.88,
                                    "visible": True,
                                    "reason_short": "no belt",
                                    "signals": ["seatbelt_not_visible"],
                                }
                            )
                        }
                    ]
                }
            }
        ]
    }

    class _Resp:
        def read(self):
            return json.dumps(payload).encode()

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    with patch("urllib.request.urlopen", return_value=_Resp()):
        v = client.judge_jpeg(b"\xff\xd8fakejpeg", rule="seatbelt_violation")
    assert v.raw_ok
    assert v.violation is True
    assert v.confidence == pytest.approx(0.88)
    assert should_emit(v, min_confidence=0.45)


def test_judge_jpeg_http_error_fail_closed():
    client = GeminiClient("fake-key")
    with patch("urllib.request.urlopen", side_effect=TimeoutError("boom")):
        v = client.judge_jpeg(b"jpeg", rule="phone_use_violation")
    assert not v.raw_ok
    assert not should_emit(v, min_confidence=0.1)


def test_vlm_queue_emits_on_positive_verdict():
    client = MagicMock()
    client.configured = True
    client.model = "gemini-3.6-flash"
    client.judge_jpeg.return_value = GeminiVerdict(
        True, "seatbelt_violation", 0.91, True, "x", ["a"], 12.0, True,
    )
    emitted: list[dict] = []
    done = threading.Event()

    def _emit(evt):
        emitted.append(evt)
        done.set()

    q = VlmQueue(client, maxsize=8, max_age_sec=30.0)
    q.set_emit_callback(_emit)
    q.start()
    ok = q.try_enqueue(
        VlmJob(
            jpeg=b"abc",
            rule="seatbelt_violation",
            min_confidence=0.45,
            event_skeleton={
                "event_id": "e1",
                "camera_id": "cam",
                "event_type": "seatbelt_violation",
                "metadata": {},
            },
        )
    )
    assert ok
    assert done.wait(timeout=3.0)
    q.stop()
    assert len(emitted) == 1
    assert emitted[0]["metadata"]["detection_method"] == "gemini_vlm"
    assert emitted[0]["confidence"] == pytest.approx(0.91)


def test_vlm_queue_plate_fusion_emits_paddle_winner():
    client = MagicMock()
    client.configured = True
    client.model = "gemini-3.1-flash-lite"
    client.judge_jpeg.return_value = GeminiVerdict(
        violation=False,
        rule="plate_ocr",
        confidence=0.2,
        visible=False,
        reason_short="unreadable",
        signals=["unclear"],
        latency_ms=12.0,
        raw_ok=True,
        plate_text="",
        readable=False,
    )
    emitted: list[dict] = []
    done = threading.Event()

    def _emit(evt):
        emitted.append(evt)
        done.set()

    q = VlmQueue(client, maxsize=8, max_age_sec=30.0, min_interval_sec=0.0)
    q.set_emit_callback(_emit)
    q.start()
    ok = q.try_enqueue(
        VlmJob(
            jpeg=b"abc",
            rule="plate_ocr",
            min_confidence=0.35,
            event_skeleton={
                "event_id": "e2",
                "camera_id": "cam",
                "event_type": "plate_detected",
                "metadata": {},
            },
            paddle_plate_text="ABCD1234",
            paddle_plate_confidence=0.88,
        )
    )
    assert ok
    assert done.wait(timeout=3.0)
    q.stop()
    assert len(emitted) == 1
    assert emitted[0]["plate_number"] == "ABCD1234"
    assert emitted[0]["metadata"]["detection_method"] == "gemini_paddle_fusion"
    assert emitted[0]["metadata"]["ocr_winner"] == "paddle"


def test_vlm_queue_drops_when_full():
    client = MagicMock()
    client.configured = True
    client.model = "m"
    # Never consume — fill queue
    q = VlmQueue(client, maxsize=2, max_age_sec=30.0)
    # Do not start worker
    job = VlmJob(b"x", "seatbelt_violation", 0.45, {"metadata": {}})
    assert q.try_enqueue(job)
    assert q.try_enqueue(job)
    assert not q.try_enqueue(job)
    assert q.stats()["dropped_full"] == 1
