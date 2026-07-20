#!/usr/bin/env python3
"""Unit tests for Frigate track evidence (no live Frigate required)."""
from __future__ import annotations

import json
import unittest
from unittest.mock import MagicMock, patch

import numpy as np

import cv2

from citevision_ai.evidence.frigate_backend import FrigateEvidenceBackend
from citevision_ai.evidence.frigate_timeline import learn_clock_offset, min_time_delta
from citevision_ai.evidence.frigate_track_evidence import FrigateTrackEvidence
from citevision_ai.evidence.gate import default_evidence_policy


def _textured_frame_for_bbox(x: float = 0.2, y: float = 0.3, w: float = 0.2, h: float = 0.2) -> np.ndarray:
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    x1 = int(x * 640)
    y1 = int(y * 480)
    x2 = int((x + w) * 640)
    y2 = int((y + h) * 480)
    rng = np.random.default_rng(42)
    frame[y1:y2, x1:x2] = rng.integers(40, 220, size=(y2 - y1, x2 - x1, 3), dtype=np.uint8)
    return frame


class FrigateTrackEvidenceTests(unittest.TestCase):
    @patch("citevision_ai.evidence.frigate_track_evidence.settings")
    def test_disabled_when_flags_off(self, mock_settings: MagicMock) -> None:
        mock_settings.frigate_enabled = False
        mock_settings.frigate_evidence = False
        mock_settings.frigate_url = "http://127.0.0.1:5000"
        mock_settings.ocr_url = ""
        engine = FrigateTrackEvidence()
        self.assertFalse(engine.enabled())
        self.assertIsNone(
            engine.capture({}, {"event_id": "e1"}, org_id="o", camera_id="cam"),
        )

    @patch("citevision_ai.evidence.frigate_track_evidence.urllib.request.urlopen")
    @patch("citevision_ai.evidence.frigate_track_evidence.settings")
    def test_capture_uses_frigate_track_metadata(self, mock_settings: MagicMock, mock_urlopen: MagicMock) -> None:
        mock_settings.frigate_enabled = True
        mock_settings.frigate_evidence = True
        mock_settings.frigate_url = "http://127.0.0.1:5000"
        mock_settings.frigate_event_match_sec = 12.0
        mock_settings.frigate_demo_timeline_align = True
        mock_settings.frigate_demo_max_align_sec = 20.0
        mock_settings.frigate_demo_loose_match_sec = 20.0
        mock_settings.frigate_demo_bootstrap_max_sec = 18.0
        mock_settings.frigate_demo_min_bbox_iou = 0.12
        mock_settings.frigate_demo_time_only_max_sec = 15.0
        mock_settings.frigate_demo_time_only_min_iou = 0.08
        mock_settings.frigate_demo_accept_max_align_sec = 4.0
        mock_settings.frigate_accept_min_bbox_iou = 0.15
        mock_settings.frigate_demo_events_limit = 40
        mock_settings.frigate_correlate_wait_sec = 0.0
        mock_settings.frigate_snapshot_retries = 2
        mock_settings.frigate_snapshot_retry_delay = 0.01
        mock_settings.frigate_snapshot_quality = 90
        mock_settings.frigate_clip_retries = 2
        mock_settings.frigate_clip_retry_delay = 0.01
        mock_settings.frigate_clip_wait_if_missing = 0.0
        mock_settings.frigate_clip_min_bytes = 512
        mock_settings.frigate_clip_pad_before = 0.4
        mock_settings.frigate_clip_pad_after = 0.8
        mock_settings.frigate_event_media_wait_sec = 0.1
        mock_settings.frigate_event_media_poll_sec = 0.01
        mock_settings.frigate_correlate_wait_sec = 0.0
        mock_settings.frigate_correlate_wait_sec = 0.0
        mock_settings.frigate_evidence_frame_count = 2
        mock_settings.frigate_clip_frame_jpeg_q = 5
        mock_settings.ocr_url = ""

        frame = _textured_frame_for_bbox()
        _, jpg = cv2.imencode(".jpg", frame)
        clip = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 2000
        anchor = 1_700_000_000.0
        events = [{
            "id": "frigate-evt-1",
            "start_time": anchor,
            "label": "car",
            "has_snapshot": True,
            "has_clip": True,
            "camera": "cv_abc",
            "data": {"box": [0.2, 0.3, 0.2, 0.2]},
        }]

        def fake_open(req, timeout=0):
            url = req.full_url if hasattr(req, "full_url") else str(req)
            if "/api/events?" in url:
                body = json.dumps(events).encode()
            elif "/api/events/frigate-evt-1" in url and "clip" not in url and "snapshot" not in url:
                body = json.dumps(events[0]).encode()
            elif "clip.mp4" in url:
                body = clip
            else:
                body = jpg.tobytes()
            resp = MagicMock()
            resp.read.return_value = body
            resp.__enter__.return_value = resp
            return resp

        mock_urlopen.side_effect = fake_open
        engine = FrigateTrackEvidence()
        evt = {
            "event_id": "ev-1",
            "bbox_ts": anchor,
            "class_name": "car",
            "bbox": {"x": 0.2, "y": 0.3, "width": 0.2, "height": 0.2},
        }
        policy = {
            "clip_seconds": 6,
            "images": [
                {"role": "scene", "crop": "full"},
                {"role": "subject", "crop": "bbox"},
            ],
        }
        out = engine.capture(policy, evt, org_id="org", camera_id="abc")
        self.assertIsNotNone(out)
        assert out is not None
        self.assertEqual(out["meta"]["capture_source"], "frigate_track")
        self.assertEqual(out["meta"]["frigate_event_id"], "frigate-evt-1")
        self.assertEqual(out["meta"]["bbox_source"], "frigate_mqtt")
        self.assertTrue(out["scene"])
        self.assertTrue(out["clip_bytes"])

    @patch("citevision_ai.evidence.frigate_track_evidence.urllib.request.urlopen")
    @patch("citevision_ai.evidence.frigate_track_evidence.settings")
    def test_demo_loop_offset_correlates_via_iou_fallback(
        self, mock_settings: MagicMock, mock_urlopen: MagicMock,
    ) -> None:
        """Looped go2rtc: Frigate start_time lags wall bbox_ts by ~25 min."""
        mock_settings.frigate_enabled = True
        mock_settings.frigate_evidence = True
        mock_settings.frigate_url = "http://127.0.0.1:5000"
        mock_settings.frigate_event_match_sec = 12.0
        mock_settings.frigate_demo_timeline_align = True
        mock_settings.frigate_demo_max_align_sec = 20.0
        mock_settings.frigate_demo_loose_match_sec = 20.0
        mock_settings.frigate_demo_bootstrap_max_sec = 18.0
        mock_settings.frigate_demo_min_bbox_iou = 0.12
        mock_settings.frigate_demo_time_only_max_sec = 15.0
        mock_settings.frigate_demo_time_only_min_iou = 0.08
        mock_settings.frigate_demo_accept_max_align_sec = 4.0
        mock_settings.frigate_accept_min_bbox_iou = 0.15
        mock_settings.frigate_demo_events_limit = 40
        mock_settings.frigate_correlate_wait_sec = 0.0
        mock_settings.frigate_snapshot_retries = 1
        mock_settings.frigate_snapshot_retry_delay = 0.01
        mock_settings.frigate_snapshot_quality = 90
        mock_settings.frigate_clip_retries = 1
        mock_settings.frigate_clip_retry_delay = 0.01
        mock_settings.frigate_clip_wait_if_missing = 0.0
        mock_settings.frigate_clip_min_bytes = 512
        mock_settings.frigate_clip_pad_before = 0.4
        mock_settings.frigate_clip_pad_after = 0.8
        mock_settings.frigate_event_media_wait_sec = 0.1
        mock_settings.frigate_event_media_poll_sec = 0.01
        mock_settings.frigate_correlate_wait_sec = 0.0
        mock_settings.frigate_evidence_frame_count = 1
        mock_settings.frigate_clip_frame_jpeg_q = 5
        mock_settings.ocr_url = ""

        frame = _textured_frame_for_bbox()
        _, jpg = cv2.imencode(".jpg", frame)
        clip = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 2000
        wall_anchor = 1_700_000_000.0
        loop_offset = 6.0
        frigate_start = wall_anchor - loop_offset
        events = [{
            "id": "frigate-loop-1",
            "start_time": frigate_start,
            "end_time": frigate_start + 4.0,
            "label": "car",
            "has_snapshot": True,
            "has_clip": True,
            "camera": "cv_demo",
            "data": {"box": [0.2, 0.3, 0.2, 0.2]},
        }]

        def fake_open(req, timeout=0):
            url = req.full_url if hasattr(req, "full_url") else str(req)
            if "/api/events?" in url:
                body = json.dumps(events).encode()
            elif "/api/events/frigate-loop-1" in url and "clip" not in url and "snapshot" not in url:
                body = json.dumps(events[0]).encode()
            elif "clip.mp4" in url:
                body = clip
            else:
                body = jpg.tobytes()
            resp = MagicMock()
            resp.read.return_value = body
            resp.__enter__.return_value = resp
            return resp

        mock_urlopen.side_effect = fake_open
        engine = FrigateTrackEvidence()
        evt = {
            "event_id": "ev-loop",
            "bbox_ts": wall_anchor,
            "class_name": "car",
            "bbox": {"x": 0.2, "y": 0.3, "width": 0.2, "height": 0.2},
        }
        policy = {"clip_seconds": 6, "images": [{"role": "scene", "crop": "full"}]}
        out = engine.capture(policy, evt, org_id="org", camera_id="demo-cam")
        self.assertIsNotNone(out)
        assert out is not None
        self.assertEqual(out["meta"]["capture_source"], "frigate_track")
        self.assertAlmostEqual(engine._demo_clock_offset["demo-cam"], loop_offset, delta=1.0)

    def test_min_time_delta_uses_path_data(self) -> None:
        ev = {
            "start_time": 100.0,
            "end_time": 110.0,
            "data": {"path_data": [[(0.5, 0.5), 105.5]]},
        }
        self.assertAlmostEqual(min_time_delta(105.0, ev), 0.5)

    def test_learn_clock_offset_ema(self) -> None:
        offsets: dict[str, float] = {}
        learn_clock_offset(offsets, "cam", 1000.0, 400.0)
        self.assertAlmostEqual(offsets["cam"], 600.0)
        learn_clock_offset(offsets, "cam", 1010.0, 420.0)
        self.assertAlmostEqual(offsets["cam"], 596.5)

    def test_time_only_rejects_zero_iou(self) -> None:
        engine = FrigateTrackEvidence()
        events = [{
            "start_time": 1000.0,
            "label": "car",
            "data": {"box": [0.7, 0.7, 0.1, 0.1]},
        }]
        evt = {
            "class_name": "car",
            "bbox": {"x": 0.1, "y": 0.1, "width": 0.2, "height": 0.2},
        }
        matched, _ = engine._pick_correlated(
            events, 1005.0, "car", evt["bbox"], 15.0, time_only=True,
            min_iou=0.08,
        )
        self.assertIsNone(matched)

    def test_time_only_picks_when_iou_meets_floor(self) -> None:
        engine = FrigateTrackEvidence()
        events = [{
            "start_time": 1000.0,
            "label": "car",
            "data": {"box": [0.2, 0.2, 0.15, 0.15]},
        }]
        evt = {
            "class_name": "car",
            "bbox": {"x": 0.1, "y": 0.1, "width": 0.2, "height": 0.2},
        }
        matched, delta = engine._pick_correlated(
            events, 1005.0, "car", evt["bbox"], 15.0, time_only=True,
            min_iou=0.08,
        )
        self.assertIsNotNone(matched)
        self.assertAlmostEqual(delta, 5.0)

    def test_rejects_stale_event_beyond_demo_window(self) -> None:
        engine = FrigateTrackEvidence()
        anchor = 1_700_000_000.0
        events = [{
            "id": "stale",
            "start_time": anchor - 194.0,
            "label": "car",
            "data": {"box": [0.2, 0.3, 0.2, 0.2]},
        }]
        evt = {
            "class_name": "car",
            "bbox": {"x": 0.2, "y": 0.3, "width": 0.2, "height": 0.2},
            "bbox_ts": anchor,
        }
        with patch.object(engine, "_list_events", return_value=events):
            with patch("citevision_ai.evidence.frigate_track_evidence.settings") as mock_settings:
                mock_settings.frigate_event_match_sec = 12.0
                mock_settings.frigate_demo_timeline_align = True
                mock_settings.frigate_demo_max_align_sec = 20.0
                mock_settings.frigate_demo_loose_match_sec = 20.0
                mock_settings.frigate_demo_bootstrap_max_sec = 18.0
                mock_settings.frigate_demo_min_bbox_iou = 0.12
                mock_settings.frigate_demo_time_only_max_sec = 15.0
                mock_settings.frigate_demo_time_only_min_iou = 0.08
                mock_settings.frigate_demo_events_limit = 40
                matched, delta = engine._correlate_event(
                    "cv_demo", anchor, evt, camera_id="demo-cam",
                )
        self.assertIsNone(matched)

    @patch("citevision_ai.evidence.frigate_track_evidence.recognize_plate_jpeg")
    @patch("citevision_ai.evidence.frigate_track_evidence.settings")
    def test_ocr_plate_uses_rear_bbox_crop_only(
        self, mock_settings: MagicMock, mock_ocr: MagicMock,
    ) -> None:
        mock_settings.ocr_url = "http://127.0.0.1:8181/ocr"
        mock_settings.ocr_timeout = 2.0
        mock_settings.plate_min_conf = 0.5
        engine = FrigateTrackEvidence()
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        norm_bbox = {"x": 0.2, "y": 0.3, "width": 0.4, "height": 0.3}
        crop = engine._plate_rear_crop_jpeg(frame, norm_bbox, default_evidence_policy()["images"])
        self.assertIsNotNone(crop)
        mock_ocr.return_value = ("AB123CD", 0.9, "rear")
        plate_jpeg, plate, conf = engine._ocr_plate(crop, {})
        mock_ocr.assert_called_once()
        self.assertEqual(plate, "AB123CD")
        self.assertEqual(conf, 0.9)
        self.assertEqual(plate_jpeg, crop)

    @patch("citevision_ai.evidence.frigate_track_evidence.recognize_plate_jpeg")
    @patch("citevision_ai.evidence.frigate_track_evidence.settings")
    def test_ocr_plate_skips_when_crop_missing(
        self, mock_settings: MagicMock, mock_ocr: MagicMock,
    ) -> None:
        mock_settings.ocr_url = "http://127.0.0.1:8181/ocr"
        engine = FrigateTrackEvidence()
        plate_jpeg, plate, conf = engine._ocr_plate(None, {})
        mock_ocr.assert_not_called()
        self.assertIsNone(plate_jpeg)

    @patch("citevision_ai.evidence.frigate_track_evidence.settings")
    def test_accept_correlation_rejects_high_align_delta(
        self, mock_settings: MagicMock,
    ) -> None:
        mock_settings.demo_loop_guard = True
        mock_settings.demo_mode = False
        mock_settings.demo_relaxed_evidence = lambda: False
        mock_settings.frigate_demo_accept_max_align_sec = 4.0
        mock_settings.frigate_accept_min_bbox_iou = 0.15
        engine = FrigateTrackEvidence()
        evt = {"class_name": "car", "bbox": {"x": 0.2, "y": 0.3, "width": 0.2, "height": 0.2}}
        matched = {"id": "e1", "label": "car", "data": {"box": [0.2, 0.3, 0.2, 0.2]}}
        self.assertFalse(engine._accept_correlation(evt, matched, 9.7, "cam1"))

    @patch("citevision_ai.evidence.frigate_track_evidence.settings")
    def test_accept_correlation_rejects_low_iou(
        self, mock_settings: MagicMock,
    ) -> None:
        mock_settings.demo_loop_guard = True
        mock_settings.demo_mode = False
        mock_settings.demo_relaxed_evidence = lambda: False
        mock_settings.frigate_demo_accept_max_align_sec = 4.0
        mock_settings.frigate_accept_min_bbox_iou = 0.15
        mock_settings.frigate_demo_timeline_align = False
        engine = FrigateTrackEvidence()
        evt = {"class_name": "car", "bbox": {"x": 0.1, "y": 0.1, "width": 0.2, "height": 0.2}}
        matched = {"id": "e1", "label": "car", "data": {"box": [0.7, 0.7, 0.1, 0.1]}}
        self.assertFalse(engine._accept_correlation(evt, matched, 1.0, "cam1"))

    @patch("citevision_ai.evidence.frigate_track_evidence.settings")
    def test_accept_correlation_accepts_tight_match(
        self, mock_settings: MagicMock,
    ) -> None:
        mock_settings.demo_loop_guard = True
        mock_settings.demo_mode = False
        mock_settings.demo_relaxed_evidence = lambda: False
        mock_settings.frigate_demo_accept_max_align_sec = 4.0
        mock_settings.frigate_accept_min_bbox_iou = 0.15
        mock_settings.frigate_demo_timeline_align = False
        engine = FrigateTrackEvidence()
        evt = {"class_name": "car", "bbox": {"x": 0.2, "y": 0.3, "width": 0.2, "height": 0.2}}
        matched = {"id": "e1", "label": "car", "data": {"box": [0.2, 0.3, 0.2, 0.2]}}
        self.assertTrue(engine._accept_correlation(evt, matched, 0.4, "cam1"))


class FrigateBackendWrapperTests(unittest.TestCase):
    @patch("citevision_ai.evidence.frigate_backend.settings")
    def test_wrapper_delegates(self, mock_settings: MagicMock) -> None:
        mock_settings.evidence_backend = "frigate"
        backend = FrigateEvidenceBackend()
        backend._track = MagicMock()
        backend._track.enabled.return_value = True
        backend._track.capture.return_value = {"meta": {"capture_source": "frigate_track"}, "status": "partial"}
        out = backend.capture({}, {"event_id": "e"}, org_id="o", camera_id="c")
        backend._track.capture.assert_called_once()
        self.assertEqual(out["meta"]["capture_source"], "frigate_track")


if __name__ == "__main__":
    unittest.main()
