#!/usr/bin/env python3
"""Bound Frigate event capture (no live Frigate poll loop)."""
from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

import cv2
import numpy as np

from citevision_ai.evidence.frigate_track_evidence import FrigateTrackEvidence


def _textured_frame() -> np.ndarray:
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    rng = np.random.default_rng(7)
    frame[100:200, 120:280] = rng.integers(40, 220, size=(100, 160, 3), dtype=np.uint8)
    return frame


class BoundFrigateCaptureTests(unittest.TestCase):
    @patch("citevision_ai.evidence.frigate_track_evidence.urllib.request.urlopen")
    @patch("citevision_ai.evidence.frigate_track_evidence.settings")
    def test_capture_uses_prebound_event_id(self, mock_settings: MagicMock, mock_urlopen: MagicMock) -> None:
        mock_settings.frigate_enabled = True
        mock_settings.frigate_evidence = True
        mock_settings.frigate_url = "http://127.0.0.1:5000"
        mock_settings.frigate_bind_min_iou = 0.12
        mock_settings.frigate_demo_accept_max_align_sec = 5.0
        mock_settings.frigate_accept_min_bbox_iou = 0.15
        mock_settings.frigate_correlate_wait_sec = 0.0
        mock_settings.frigate_event_media_wait_sec = 0.1
        mock_settings.frigate_event_media_poll_sec = 0.01
        mock_settings.frigate_snapshot_retries = 1
        mock_settings.frigate_snapshot_retry_delay = 0.01
        mock_settings.frigate_snapshot_quality = 90
        mock_settings.frigate_clip_retries = 1
        mock_settings.frigate_clip_retry_delay = 0.01
        mock_settings.frigate_clip_wait_if_missing = 0.0
        mock_settings.frigate_clip_min_bytes = 512
        mock_settings.frigate_clip_pad_before = 0.4
        mock_settings.frigate_clip_pad_after = 0.8
        mock_settings.frigate_evidence_frame_count = 2
        mock_settings.frigate_clip_frame_jpeg_q = 5
        mock_settings.ocr_url = ""

        frame = _textured_frame()
        _, jpg = cv2.imencode(".jpg", frame)
        clip = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 2000

        def fake_urlopen(req, timeout=12):
            url = req if isinstance(req, str) else req.full_url
            resp = MagicMock()
            if "/api/events?" in url:
                resp.read.return_value = b"[]"
            elif url.endswith("/clip.mp4"):
                resp.read.return_value = clip
            elif "/snapshot.jpg" in url:
                resp.read.return_value = jpg.tobytes()
            elif "/clean.png" in url or "/thumbnail.jpg" in url:
                resp.read.return_value = jpg.tobytes()
            else:
                payload = {
                    "id": "bound-ev-1",
                    "has_clip": True,
                    "has_snapshot": True,
                    "label": "car",
                    "start_time": 1783944000.0,
                    "data": {"box": [0.19, 0.21, 0.25, 0.18]},
                }
                resp.read.return_value = __import__("json").dumps(payload).encode()
            resp.__enter__ = lambda s: resp
            resp.__exit__ = MagicMock(return_value=False)
            return resp

        mock_urlopen.side_effect = fake_urlopen

        engine = FrigateTrackEvidence()
        evt = {
            "event_id": "ia-1",
            "frigate_event_id": "bound-ev-1",
            "track_id": 2,
            "class_name": "car",
            "bbox": {"x": 0.19, "y": 0.21, "width": 0.25, "height": 0.18},
            "bbox_ts": 1783944000.2,
            "metadata": {"frigate_bind_iou": 0.45, "frigate_bind_delta_sec": 0.2},
        }
        out = engine.capture({}, evt, org_id="org", camera_id="cam-1")
        self.assertIsNotNone(out)
        assert out is not None
        self.assertEqual(out["meta"]["capture_source"], "frigate_track")
        self.assertEqual(out["meta"]["bbox_source"], "frigate_mqtt")
        self.assertEqual(out["meta"]["frigate_event_id"], "bound-ev-1")


if __name__ == "__main__":
    unittest.main()
