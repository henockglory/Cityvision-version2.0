#!/usr/bin/env python3
"""Tests for proactive Frigate track binding."""
from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from citevision_ai.evidence.frigate_track_binder import FrigateTrackBinder


class FrigateTrackBinderTests(unittest.TestCase):
    def test_inject_event_sets_frigate_event_id(self) -> None:
        track = MagicMock()
        track.enabled.return_value = True
        binder = FrigateTrackBinder(track)
        binder._bindings[("cam-1", 7)] = type("B", (), {
            "frigate_event_id": "1783942846.01981-b55uqn",
            "align_delta": 0.4,
            "iou": 0.55,
            "bound_at": 1.0,
        })()
        evt: dict = {"track_id": 7, "event_type": "speeding", "metadata": {}}
        binder.inject_event("cam-1", evt)
        self.assertEqual(evt["frigate_event_id"], "1783942846.01981-b55uqn")
        self.assertAlmostEqual(evt["metadata"]["frigate_bind_iou"], 0.55)

    @patch("citevision_ai.evidence.frigate_track_binder.settings")
    def test_update_tracks_skips_when_disabled(self, mock_settings: MagicMock) -> None:
        mock_settings.frigate_track_binding_enabled = False
        track = MagicMock()
        track.enabled.return_value = True
        binder = FrigateTrackBinder(track)
        binder.update_tracks(
            "cam-1",
            [{"track_id": 1, "class_name": "car", "bbox": {"x": 10, "y": 10, "width": 50, "height": 40}}],
            frame_w=640,
            frame_h=480,
            wall_ts=1000.0,
        )
        track.list_events_for_camera.assert_not_called()

    @patch("citevision_ai.evidence.frigate_track_binder.settings")
    def test_update_tracks_reserves_on_iou_match(self, mock_settings: MagicMock) -> None:
        mock_settings.frigate_track_binding_enabled = True
        mock_settings.frigate_bind_every_n_frames = 1
        mock_settings.frigate_bind_min_iou = 0.12
        track = MagicMock()
        track.enabled.return_value = True
        track.frigate_camera_id.return_value = "cv_cam-1"
        track.list_events_for_camera.return_value = [{"id": "ev-1", "label": "car"}]
        track.match_track_to_event.return_value = (
            {"id": "ev-1", "label": "car"},
            0.5,
            0.42,
        )
        binder = FrigateTrackBinder(track)
        binder.update_tracks(
            "cam-1",
            [{"track_id": 3, "class_name": "car", "bbox": {"x": 100, "y": 80, "width": 120, "height": 90}}],
            frame_w=640,
            frame_h=480,
            wall_ts=1783944000.0,
        )
        got = binder.get("cam-1", 3)
        self.assertIsNotNone(got)
        assert got is not None
        self.assertEqual(got.frigate_event_id, "ev-1")
        self.assertAlmostEqual(got.iou, 0.42)


if __name__ == "__main__":
    unittest.main()
