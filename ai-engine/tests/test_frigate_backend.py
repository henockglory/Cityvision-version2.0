#!/usr/bin/env python3
"""Unit tests for Frigate track evidence (no live Frigate required)."""
from __future__ import annotations

import json
import os
import tempfile
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


def _traffic_light_frame(colour_bgr: tuple[int, int, int]) -> np.ndarray:
    frame = _textured_frame_for_bbox()
    frame[40:90, 40:90] = colour_bgr
    return frame


def _mp4_bytes(frames: list[np.ndarray], fps: float = 5.0) -> bytes:
    tmp = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
    tmp.close()
    try:
        h, w = frames[0].shape[:2]
        writer = cv2.VideoWriter(tmp.name, cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h))
        if not writer.isOpened():
            raise unittest.SkipTest("OpenCV mp4 writer unavailable")
        for frame in frames:
            writer.write(frame)
        writer.release()
        with open(tmp.name, "rb") as fh:
            return fh.read()
    finally:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass


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

    @patch("citevision_ai.evidence.frigate_track_evidence.settings")
    def test_red_light_anchor_frame_selects_red_scene_and_subject(self, mock_settings: MagicMock) -> None:
        mock_settings.frigate_demo_timeline_align = False
        mock_settings.frigate_clip_pad_before = 0.0
        mock_settings.frigate_clip_pad_after = 0.0
        engine = FrigateTrackEvidence()
        clip = _mp4_bytes([
            _traffic_light_frame((0, 255, 0)),
            _traffic_light_frame((0, 0, 255)),
            _traffic_light_frame((0, 255, 0)),
        ])
        evt = {
            "bbox_ts": 100.2,
            "metadata": {
                "light_zone_polygon": [
                    {"x": 40 / 640, "y": 40 / 480},
                    {"x": 90 / 640, "y": 40 / 480},
                    {"x": 90 / 640, "y": 90 / 480},
                    {"x": 40 / 640, "y": 90 / 480},
                ],
                "violation_instant_ts": 100.2,
            },
        }
        matched = {"start_time": 100.0, "end_time": 100.6}
        norm_bbox = {"x": 0.2, "y": 0.3, "width": 0.2, "height": 0.2, "norm": True}
        out = engine._red_light_frame_from_clip_at_anchor(
            clip, matched, evt, "cam-1", 100.2, norm_bbox, default_evidence_policy(),
        )
        self.assertIsNotNone(out)
        assert out is not None
        scene, subject, _plate, _bbox, capture_ts, capture_pts = out
        self.assertEqual(engine._scene_light_state(scene, evt), "red")
        self.assertIsNotNone(subject)
        self.assertIsNotNone(capture_ts)
        self.assertIsNotNone(capture_pts)

    @patch("citevision_ai.evidence.frigate_track_evidence.settings")
    def test_red_light_anchor_frame_recenters_to_path_data(self, mock_settings: MagicMock) -> None:
        mock_settings.frigate_demo_timeline_align = False
        mock_settings.frigate_clip_pad_before = 0.0
        mock_settings.frigate_clip_pad_after = 0.0
        engine = FrigateTrackEvidence()
        clip = _mp4_bytes([
            _traffic_light_frame((0, 255, 0)),
            _traffic_light_frame((0, 0, 255)),
            _traffic_light_frame((0, 255, 0)),
        ])
        evt = {
            "bbox_ts": 500.0,
            "metadata": {
                "light_zone_polygon": [
                    {"x": 40 / 640, "y": 40 / 480},
                    {"x": 90 / 640, "y": 40 / 480},
                    {"x": 90 / 640, "y": 90 / 480},
                    {"x": 40 / 640, "y": 90 / 480},
                ],
                "violation_instant_ts": 500.0,
            },
        }
        matched = {
            "start_time": 100.0,
            "end_time": 100.6,
            "data": {"path_data": [[[0.3, 0.4], 100.2]]},
        }
        norm_bbox = {"x": 0.2, "y": 0.3, "width": 0.2, "height": 0.2, "norm": True}
        out = engine._red_light_frame_from_clip_at_anchor(
            clip, matched, evt, "cam-1", 500.0, norm_bbox, default_evidence_policy(),
        )
        self.assertIsNotNone(out)
        assert out is not None
        scene, _subject, _plate, _bbox, capture_ts, capture_pts = out
        self.assertEqual(engine._scene_light_state(scene, evt), "red")
        self.assertAlmostEqual(float(capture_ts or 0), 100.2, places=1)
        self.assertAlmostEqual(float(capture_pts or 0), 0.2, places=1)

    @patch("citevision_ai.evidence.frigate_track_evidence.settings")
    def test_red_light_anchor_frame_rejects_green_scene(self, mock_settings: MagicMock) -> None:
        mock_settings.frigate_demo_timeline_align = False
        mock_settings.frigate_clip_pad_before = 0.0
        mock_settings.frigate_clip_pad_after = 0.0
        engine = FrigateTrackEvidence()
        clip = _mp4_bytes([
            _traffic_light_frame((0, 255, 0)),
            _traffic_light_frame((0, 255, 0)),
            _traffic_light_frame((0, 255, 0)),
        ])
        evt = {
            "bbox_ts": 100.2,
            "metadata": {
                "light_zone_polygon": [
                    {"x": 40 / 640, "y": 40 / 480},
                    {"x": 90 / 640, "y": 40 / 480},
                    {"x": 90 / 640, "y": 90 / 480},
                    {"x": 40 / 640, "y": 90 / 480},
                ],
                "violation_instant_ts": 100.2,
            },
        }
        matched = {"start_time": 100.0, "end_time": 100.6}
        norm_bbox = {"x": 0.2, "y": 0.3, "width": 0.2, "height": 0.2, "norm": True}
        out = engine._red_light_frame_from_clip_at_anchor(
            clip, matched, evt, "cam-1", 100.2, norm_bbox, default_evidence_policy(),
        )
        self.assertIsNone(out)

    @patch("citevision_ai.evidence.frigate_track_evidence.settings")
    def test_red_light_anchor_skips_offset_for_bridge_sourced_event(self, mock_settings: MagicMock) -> None:
        """bbox_ts from the Frigate bridge is already Frigate-native: re-applying
        the learned wall-clock<->Frigate offset would double-correct it and push
        the anchor outside the track window (bug 2 in the temporal alignment fix).
        """
        mock_settings.frigate_demo_timeline_align = True
        mock_settings.frigate_clip_pad_before = 0.0
        mock_settings.frigate_clip_pad_after = 0.0
        engine = FrigateTrackEvidence()
        engine._demo_clock_offset["cam-1"] = 5.0
        matched = {"start_time": 100.0, "end_time": 110.0}

        bridge_evt = {
            "bbox_ts": 105.0,
            "metadata": {"bridge_source": "frigate", "violation_instant_ts": 105.0},
        }
        _pts, _duration, _clip_start, debug = engine._red_light_anchor_pts(
            "no-such-clip.mp4", matched, bridge_evt, "cam-1", 105.0,
        )
        self.assertEqual(debug["anchor_aligned"], 105.0)
        self.assertEqual(debug["anchor_used"], 105.0)
        self.assertFalse(debug["anchor_recentered"])

        non_bridge_evt = {
            "bbox_ts": 105.0,
            "metadata": {"violation_instant_ts": 105.0},
        }
        _pts2, _duration2, _clip_start2, debug2 = engine._red_light_anchor_pts(
            "no-such-clip.mp4", matched, non_bridge_evt, "cam-1", 105.0,
        )
        self.assertEqual(debug2["anchor_aligned"], 100.0)
        self.assertEqual(debug2["anchor_used"], 100.0)

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

    def test_red_light_candidate_loop_falls_back_to_valid_candidate(self) -> None:
        engine = FrigateTrackEvidence()
        evt = {
            "event_type": "red_light_violation",
            "bbox_ts": 100.0,
            "bbox": {"x": 0.1, "y": 0.1, "width": 0.1, "height": 0.1},
            "metadata": {
                "bridge_source": "frigate",
                "frigate_candidate_events": [
                    {
                        "id": "primary",
                        "bbox": {"x": 0.1, "y": 0.1, "width": 0.1, "height": 0.1},
                        "bbox_ts": 100.0,
                        "score": 9.0,
                    },
                    {
                        "id": "fallback",
                        "bbox": {"x": 0.2, "y": 0.3, "width": 0.2, "height": 0.2},
                        "bbox_ts": 101.0,
                        "score": 8.0,
                    },
                ],
            },
        }
        missing = {"status": "missing", "meta": {"abort_reason": "subject_empty", "red_frames": 0}}
        success = {
            "status": "complete",
            "meta": {
                "scene_light_state": "red",
                "bbox_source": "frigate_mqtt",
                "subject_vehicle_ok": True,
            },
        }

        with patch.object(engine, "fetch_event", side_effect=lambda eid: {"id": eid, "start_time": 100.0}):
            with patch.object(engine, "_compose_from_matched", side_effect=[missing, success]) as compose:
                out = engine._compose_bridge_red_light_candidates(
                    bound_id="primary",
                    policy=default_evidence_policy(),
                    evt=evt,
                    camera_id="cam",
                    org_id="org",
                )

        self.assertIsNotNone(out)
        assert out is not None
        self.assertEqual(out["meta"]["frigate_candidate_selected"], "fallback")
        self.assertEqual(out["meta"]["frigate_candidate_rank"], 1)
        fallback_evt = compose.call_args_list[1].args[3]
        self.assertEqual(fallback_evt["frigate_event_id"], "fallback")
        self.assertEqual(fallback_evt["bbox"], {"x": 0.2, "y": 0.3, "width": 0.2, "height": 0.2})
        self.assertEqual(fallback_evt["metadata"]["violation_instant_ts"], 101.0)

    def test_red_light_candidate_loop_returns_explicit_abort_when_all_invalid(self) -> None:
        engine = FrigateTrackEvidence()
        evt = {
            "event_type": "red_light_violation",
            "bbox_ts": 100.0,
            "bbox": {"x": 0.1, "y": 0.1, "width": 0.1, "height": 0.1},
            "metadata": {
                "bridge_source": "frigate",
                "frigate_candidate_events": [
                    {"id": "primary", "bbox": {"x": 0.1, "y": 0.1, "width": 0.1, "height": 0.1}, "bbox_ts": 100.0},
                    {"id": "fallback", "bbox": {"x": 0.2, "y": 0.3, "width": 0.2, "height": 0.2}, "bbox_ts": 101.0},
                ],
            },
        }
        missing = {
            "status": "missing",
            "meta": {
                "abort_reason": "subject_empty",
                "red_frames": 0,
                "content_frames": 0,
                "best_texture": None,
                "target_pts": 0.4,
            },
        }

        with patch.object(engine, "fetch_event", side_effect=lambda eid: {"id": eid, "start_time": 100.0}):
            with patch.object(engine, "_compose_from_matched", return_value=missing):
                out = engine._compose_bridge_red_light_candidates(
                    bound_id="primary",
                    policy=default_evidence_policy(),
                    evt=evt,
                    camera_id="cam",
                    org_id="org",
                )

        self.assertIsNotNone(out)
        assert out is not None
        self.assertEqual(out["status"], "missing")
        self.assertEqual(out["meta"]["abort_reason"], "no_candidate_with_red_frame")
        self.assertEqual(out["meta"]["frigate_candidate_count"], 2)
        self.assertEqual(len(out["meta"]["frigate_candidate_attempts"]), 2)
        self.assertEqual(out["meta"]["frigate_candidate_attempts"][0]["red_frames"], 0)

    def test_red_light_candidate_loop_rejects_non_frigate_bbox_source(self) -> None:
        engine = FrigateTrackEvidence()
        evt = {
            "event_type": "red_light_violation",
            "bbox_ts": 100.0,
            "bbox": {"x": 0.1, "y": 0.1, "width": 0.1, "height": 0.1},
            "metadata": {"bridge_source": "frigate"},
        }
        bad_source = {
            "status": "complete",
            "meta": {
                "scene_light_state": "red",
                "bbox_source": "ia_overlay",
                "subject_vehicle_ok": True,
            },
        }

        with patch.object(engine, "fetch_event", return_value={"id": "primary", "start_time": 100.0}):
            with patch.object(engine, "_compose_from_matched", return_value=bad_source):
                out = engine._compose_bridge_red_light_candidates(
                    bound_id="primary",
                    policy=default_evidence_policy(),
                    evt=evt,
                    camera_id="cam",
                    org_id="org",
                )

        self.assertIsNotNone(out)
        assert out is not None
        self.assertEqual(out["status"], "missing")
        self.assertEqual(out["meta"]["abort_reason"], "no_candidate_with_red_frame")
        self.assertEqual(out["meta"]["frigate_candidate_attempts"][0]["bbox_source"], "ia_overlay")


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
