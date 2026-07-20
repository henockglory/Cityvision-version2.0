"""Evidence image role assignment (scene / subject / plate)."""

from __future__ import annotations

import cv2
import numpy as np

from citevision_ai.evidence.capture import capture_images_from_policy, draw_bbox_on_frame
from citevision_ai.evidence.gate import default_evidence_policy


def _frame(w: int = 640, h: int = 480) -> np.ndarray:
    img = np.full((h, w, 3), 90, dtype=np.uint8)
    cv2.rectangle(img, (200, 150), (420, 320), (40, 40, 200), -1)
    return img


def test_draw_bbox_on_scene_only_not_subject():
    frame = _frame()
    bbox = {"x": 0.3125, "y": 0.3125, "width": 0.34375, "height": 0.354}
    spec = default_evidence_policy()["images"]
    scene_on, subject_on, _ = capture_images_from_policy(frame, bbox, spec, quality=80, draw_bbox=True)
    scene_off, subject_off, _ = capture_images_from_policy(frame, bbox, spec, quality=80, draw_bbox=False)

    assert scene_on != scene_off
    assert subject_on == subject_off


def test_subject_crop_differs_from_scene_when_bbox_present():
    frame = _frame()
    bbox = {"x": 0.3125, "y": 0.3125, "width": 0.34375, "height": 0.354}
    spec = default_evidence_policy()["images"]
    scene, subject, extras = capture_images_from_policy(frame, bbox, spec, quality=80, draw_bbox=True)

    assert scene is not None
    assert subject is not None
    assert scene != subject

    decoded_scene = cv2.imdecode(np.frombuffer(scene, np.uint8), cv2.IMREAD_COLOR)
    decoded_subject = cv2.imdecode(np.frombuffer(subject, np.uint8), cv2.IMREAD_COLOR)
    assert decoded_scene.shape[:2] == frame.shape[:2]
    assert decoded_subject.shape[0] < frame.shape[0]
    assert decoded_subject.shape[1] < frame.shape[1]

    assert len(extras) == 1 and extras[0] is not None


def test_plate_not_full_scene_when_bbox_missing():
    frame = _frame()
    spec = default_evidence_policy()["images"]
    scene, subject, extras = capture_images_from_policy(frame, None, spec, quality=80)
    assert scene is not None
    assert subject is not None
    assert extras == []


def test_draw_bbox_on_frame_adds_rectangle():
    frame = _frame()
    bbox = {"x": 0.3125, "y": 0.3125, "width": 0.34375, "height": 0.354}
    out = draw_bbox_on_frame(frame, bbox)
    assert not np.array_equal(out, frame)


def test_tiny_bbox_ignored_for_draw_and_pick():
    from citevision_ai.evidence.capture import pick_best_bbox

    tiny = {"x": 0.5, "y": 0.5, "width": 0.001, "height": 0.001}
    good = {"x": 100, "y": 80, "width": 220, "height": 140}
    frame = _frame()
    assert np.array_equal(draw_bbox_on_frame(frame, tiny), frame)
    best = pick_best_bbox([tiny, good], 640, 480, min_frac=0.02)
    assert best is not None
    assert best["width"] >= 0.02


def test_pick_best_bbox_with_ts_returns_source_frame_timestamp():
    """The winning bbox's own timestamp must be returned, not an arbitrary one —
    evidence capture relies on this to fetch the exact frame that produced it."""
    from citevision_ai.evidence.capture import pick_best_bbox_with_ts

    small_recent = ({"x": 0.5, "y": 0.5, "width": 0.03, "height": 0.03}, 10.0)
    large_old = ({"x": 0.2, "y": 0.2, "width": 0.3, "height": 0.3}, 5.0)
    tiny_glitch = ({"x": 0.9, "y": 0.9, "width": 0.001, "height": 0.001}, 10.5)

    best, ts = pick_best_bbox_with_ts(
        [small_recent, large_old, tiny_glitch], 640, 480, min_frac=0.02
    )
    assert best is not None
    assert best["width"] == 0.3
    assert ts == 5.0


def test_pick_best_bbox_with_ts_no_valid_candidates_returns_none():
    from citevision_ai.evidence.capture import pick_best_bbox_with_ts

    best, ts = pick_best_bbox_with_ts(
        [(None, 1.0), ({"x": 0, "y": 0, "width": 0.001, "height": 0.001}, 2.0)],
        640,
        480,
        min_frac=0.02,
    )
    assert best is None
    assert ts is None


def test_pick_best_bbox_rejects_exit_glitch_prefers_vehicle_bbox():
    """Oversized partial-off-screen bboxes at zone exit must not beat a real vehicle box."""
    from citevision_ai.evidence.capture import pick_best_bbox_with_ts

    glitch_exit = (
        {"x": 0.0, "y": 0.64, "width": 0.55, "height": 0.62},
        100.0,
    )
    vehicle = (
        {"x": 0.18, "y": 0.42, "width": 0.22, "height": 0.18},
        99.5,
    )
    best, ts = pick_best_bbox_with_ts([glitch_exit, vehicle], 1920, 1080, min_frac=0.02)
    assert best is not None
    assert abs(best["width"] - 0.22) < 0.01
    assert ts == 99.5


def test_capture_retroactive_uses_bbox_ts_not_event_ts():
    from citevision_ai.evidence.buffer import BufferedFrame, FrameRingBuffer
    from citevision_ai.evidence.service import EvidenceCaptureService

    svc = EvidenceCaptureService()
    camera_id = "cam-retro"
    ring = FrameRingBuffer(max_seconds=8, fps=6)
    frame_bbox = np.full((480, 640, 3), 42, dtype=np.uint8)
    frame_event = np.full((480, 640, 3), 99, dtype=np.uint8)
    ok1, enc1 = cv2.imencode(".jpg", frame_bbox)
    ok2, enc2 = cv2.imencode(".jpg", frame_event)
    ring._frames.append(BufferedFrame(jpeg=enc1.tobytes(), ts=1000.0))
    ring._frames.append(BufferedFrame(jpeg=enc2.tobytes(), ts=1000.4))
    svc._buffers[camera_id] = ring

    evt = {
        "event_id": "evt-retro",
        "timestamp": "2026-07-08T07:00:00.400Z",
        "bbox_ts": 1000.0,
        "bbox": {"x": 0.2, "y": 0.2, "width": 0.2, "height": 0.2},
    }
    resolved = svc._resolve_capture_frame(camera_id, evt, frame_event, frame_ts=None)
    assert int(resolved[0, 0, 0]) == 42


def test_resolve_capture_frame_uses_live_frame_when_aligned():
    """When the live frame's timestamp matches the bbox's source timestamp
    (the common case), evidence capture should use it directly and never touch
    the (coarser, lossy-JPEG) ring buffer."""
    from citevision_ai.evidence.buffer import BufferedFrame, FrameRingBuffer
    from citevision_ai.evidence.service import EvidenceCaptureService

    svc = EvidenceCaptureService()
    camera_id = "cam-aligned"
    ring = FrameRingBuffer(max_seconds=8, fps=6)
    other_jpeg_frame = np.full((480, 640, 3), 1, dtype=np.uint8)
    ok, enc = cv2.imencode(".jpg", other_jpeg_frame)
    assert ok
    ring._frames.append(BufferedFrame(jpeg=enc.tobytes(), ts=500.0))
    ring._last_bgr = other_jpeg_frame
    svc._buffers[camera_id] = ring

    live_frame = np.full((480, 640, 3), 77, dtype=np.uint8)
    evt = {
        "event_id": "evt-aligned",
        "timestamp": "2026-07-07T10:00:00Z",
        "bbox_ts": 500.0,
        "bbox": {"x": 0.3, "y": 0.3, "width": 0.2, "height": 0.2},
    }
    resolved = svc._resolve_capture_frame(camera_id, evt, live_frame, frame_ts=500.05)
    assert resolved is live_frame
    assert int(resolved[0, 0, 0]) == 77


def test_resolve_capture_frame_falls_back_to_ring_buffer_by_bbox_ts_when_stale():
    """When the live frame in hand is *not* the one that produced the bbox
    (e.g. capture happens on a later tick), fetch the ring-buffer frame closest
    to bbox_ts — not the event-emission timestamp, which would land on a frame
    where the vehicle has already moved (the original 'blue box on empty road' bug)."""
    from citevision_ai.evidence.buffer import BufferedFrame, FrameRingBuffer
    from citevision_ai.evidence.service import EvidenceCaptureService

    svc = EvidenceCaptureService()
    camera_id = "cam-stale"
    ring = FrameRingBuffer(max_seconds=8, fps=6)

    frame_at_bbox = np.full((480, 640, 3), 10, dtype=np.uint8)
    frame_at_emission = np.full((480, 640, 3), 200, dtype=np.uint8)
    ok1, enc1 = cv2.imencode(".jpg", frame_at_bbox)
    ok2, enc2 = cv2.imencode(".jpg", frame_at_emission)
    assert ok1 and ok2
    ring._frames.append(BufferedFrame(jpeg=enc1.tobytes(), ts=1000.0))
    ring._frames.append(BufferedFrame(jpeg=enc2.tobytes(), ts=1000.3))
    ring._last_bgr = frame_at_emission
    svc._buffers[camera_id] = ring

    stale_live_frame = np.full((480, 640, 3), 255, dtype=np.uint8)
    evt = {
        "event_id": "evt-stale",
        "timestamp": "2026-07-07T10:00:00.300000+00:00",
        "bbox_ts": 1000.0,
        "bbox": {"x": 0.3, "y": 0.3, "width": 0.2, "height": 0.2},
    }
    resolved = svc._resolve_capture_frame(camera_id, evt, stale_live_frame, frame_ts=1000.3)
    assert resolved is not None
    assert int(resolved[0, 0, 0]) == 10
