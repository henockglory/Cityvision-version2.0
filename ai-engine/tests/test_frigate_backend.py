#!/usr/bin/env python3
"""Unit tests for Frigate evidence backend (no live Frigate required)."""
from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

import numpy as np

from citevision_ai.evidence.frigate_backend import FrigateEvidenceBackend


class FrigateBackendTests(unittest.TestCase):
    @patch("citevision_ai.evidence.frigate_backend.settings")
    def test_disabled_when_flags_off(self, mock_settings: MagicMock) -> None:
        mock_settings.frigate_enabled = False
        mock_settings.frigate_evidence = False
        mock_settings.frigate_url = "http://127.0.0.1:5000"
        mock_settings.frigate_plate_ocr = False
        backend = FrigateEvidenceBackend()
        self.assertFalse(backend.enabled())
        self.assertIsNone(
            backend.capture({}, {"event_id": "e1"}, org_id="o", camera_id="cam"),
        )

    @patch("citevision_ai.evidence.frigate_backend.urllib.request.urlopen")
    @patch("citevision_ai.evidence.frigate_backend.settings")
    def test_capture_builds_package_fields(self, mock_settings: MagicMock, mock_urlopen: MagicMock) -> None:
        mock_settings.frigate_enabled = True
        mock_settings.frigate_evidence = True
        mock_settings.frigate_url = "http://127.0.0.1:5000"
        mock_settings.frigate_plate_ocr = False

        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        import cv2

        _, jpg = cv2.imencode(".jpg", frame)
        clip = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 2000

        def fake_open(req, timeout=0):
            url = req.full_url if hasattr(req, "full_url") else str(req)
            body = clip if "clip.mp4" in url else jpg.tobytes()
            resp = MagicMock()
            resp.read.return_value = body
            resp.__enter__.return_value = resp
            return resp

        mock_urlopen.side_effect = fake_open
        backend = FrigateEvidenceBackend()
        backend._plate = MagicMock()
        backend._plate.is_loaded = False

        evt = {
            "event_id": "ev-1",
            "bbox_ts": 1_700_000_000.0,
            "bbox": {"x": 0.2, "y": 0.3, "width": 0.2, "height": 0.2},
        }
        policy = {
            "clip_seconds": 6,
            "images": [
                {"role": "scene", "crop": "full"},
                {"role": "subject", "crop": "bbox"},
            ],
        }
        out = backend.capture(policy, evt, org_id="org", camera_id="abc")
        self.assertIsNotNone(out)
        assert out is not None
        self.assertEqual(out["meta"]["capture_source"], "frigate")
        self.assertEqual(out["meta"]["frigate_camera_id"], "cv_abc")
        self.assertTrue(out["scene"])
        self.assertTrue(out["clip_bytes"])


if __name__ == "__main__":
    unittest.main()
