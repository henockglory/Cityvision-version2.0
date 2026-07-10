"""Live evidence alignment — bbox and frame must come from the same instant.

Covers the handoff checklist (docs/HANDOFF-EVIDENCE-ALIGNMENT.md §9/§10):
- B3: aligned frame resolution (live frame vs ring-buffer lookup by bbox_ts)
- C4: bbox_region_has_content rejects uniform road
- C5: empty-bbox capture never reports evidence_status=complete
"""

from __future__ import annotations

import cv2
import numpy as np

from citevision_ai.evidence.buffer import BufferedFrame, FrameRingBuffer
from citevision_ai.evidence.capture import resolve_emission_track_bbox, subject_jpeg_texture
from citevision_ai.evidence.service import EvidenceCaptureService, SUBJECT_MIN_TEXTURE


def _road_frame(w: int = 640, h: int = 480) -> np.ndarray:
    """Uniform gray road — no vehicle anywhere."""
    return np.full((h, w, 3), 128, dtype=np.uint8)


def _vehicle_frame(w: int = 640, h: int = 480) -> np.ndarray:
    """Road with a textured 'vehicle' patch at norm bbox (0.3, 0.3, 0.35, 0.35)."""
    img = np.full((h, w, 3), 128, dtype=np.uint8)
    cv2.rectangle(img, (200, 150), (420, 320), (30, 30, 190), -1)
    cv2.rectangle(img, (240, 190), (380, 280), (220, 220, 220), 3)
    cv2.circle(img, (260, 300), 18, (10, 10, 10), -1)
    cv2.circle(img, (360, 300), 18, (10, 10, 10), -1)
    return img


VEHICLE_BBOX = {"x": 0.3, "y": 0.3, "width": 0.35, "height": 0.36}


def _ring_with(frames: list[tuple[np.ndarray, float]]) -> FrameRingBuffer:
    ring = FrameRingBuffer(max_seconds=12, fps=12)
    for img, ts in frames:
        ok, enc = cv2.imencode(".jpg", img)
        assert ok
        ring._frames.append(BufferedFrame(jpeg=enc.tobytes(), ts=ts))
    if frames:
        ring._last_bgr = frames[-1][0]
    return ring


# --- resolve_emission_track_bbox: current track on emission frame wins ---------

def test_emission_track_bbox_wins_over_event_historical_bbox():
    """Current YOLO track on the inference frame must beat evt bbox from an earlier instant."""
    evt = {
        "track_id": 7,
        "bbox": {"x": 0.3, "y": 0.3, "width": 0.1, "height": 0.1},
        "bbox_ts": 1000.0,
    }
    tracks = [{"track_id": 7, "bbox": {"x": 0.7, "y": 0.7, "width": 0.2, "height": 0.2}}]
    bb, ts, src = resolve_emission_track_bbox(evt, tracks, 1920, 1080, 1003.0)
    assert src == "emission_track"
    assert bb is not None
    assert abs(bb["x"] - 0.7) < 1e-6
    assert ts == 1003.0


def test_event_fallback_bbox_gets_frame_ts():
    evt = {"track_id": 3, "bbox": {"x": 0.4, "y": 0.4, "width": 0.1, "height": 0.1}}
    bb, ts, src = resolve_emission_track_bbox(evt, [], 1920, 1080, 555.5)
    assert src == "event_fallback"
    assert bb is not None
    assert ts == 555.5


def test_invalid_event_bbox_falls_back_to_current_track():
    evt = {"track_id": 4, "bbox": {}, "bbox_ts": None}
    tracks = [{"track_id": 4, "bbox": {"x": 0.2, "y": 0.2, "width": 0.15, "height": 0.15}}]
    bb, ts, src = resolve_emission_track_bbox(evt, tracks, 1920, 1080, 777.0)
    assert src == "emission_track"
    assert bb is not None
    assert ts == 777.0


def test_no_bbox_anywhere_returns_none():
    evt = {"track_id": 9}
    bb, ts, src = resolve_emission_track_bbox(evt, [], 1920, 1080, 1.0)
    assert src == "none"
    assert bb is None
    assert ts is None

def test_resolve_aligned_frame_emission_skips_ring_lookup():
    """Co-emission events use the inference frame directly — no ring-buffer retry."""
    svc = EvidenceCaptureService()
    empty = _road_frame()
    good = _vehicle_frame()
    svc._buffers["cam-co"] = _ring_with([(good, 99.9), (empty, 100.4)])
    evt = {
        "event_id": "e-co",
        "bbox": VEHICLE_BBOX,
        "bbox_ts": 100.0,
        "bbox_source": "emission_track",
    }
    out, ok = svc.resolve_aligned_frame("cam-co", evt, empty, frame_ts=100.0)
    assert out is empty
    assert ok is False


def test_capture_and_attach_partial_when_subject_texture_low(monkeypatch):
    svc = EvidenceCaptureService()
    uploads: list[dict] = []

    def fake_upload(org_id, camera_id, event_id, scene, subject, clip, meta, plate_jpeg=None):
        uploads.append(meta)
        return {"package": {"metadata": meta}}

    monkeypatch.setattr(svc._uploader, "upload", fake_upload)
    empty = _road_frame()
    svc._buffers["cam-subj"] = _ring_with([(empty, 100.0 + i * 0.1) for i in range(-30, 31)])
    evt = {
        "event_id": "e-subj",
        "bbox": VEHICLE_BBOX,
        "bbox_ts": 100.0,
        "bbox_source": "emission_track",
    }
    from citevision_ai.evidence.gate import default_evidence_policy

    svc._capture_and_attach(
        "cam-subj", "org-1", evt, empty, default_evidence_policy(), frame_ts=100.0,
    )
    assert uploads
    meta = uploads[0]
    assert meta["subject_quality_ok"] is False
    assert meta["subject_texture"] is not None
    assert meta["subject_texture"] < SUBJECT_MIN_TEXTURE
    assert meta["evidence_status"] == "partial"


def test_resolve_aligned_frame_accepts_frame_with_vehicle():
    svc = EvidenceCaptureService()
    frame = _vehicle_frame()
    evt = {"event_id": "e1", "bbox": VEHICLE_BBOX, "bbox_ts": 100.0}
    out, ok = svc.resolve_aligned_frame("cam-a", evt, frame, frame_ts=100.0)
    assert ok is True
    assert out is frame


def test_resolve_aligned_frame_retries_ring_neighbors_on_empty_bbox():
    """Live frame has empty bbox region → the neighbor frame in the ring buffer
    at bbox_ts (where the vehicle actually was) must be used instead."""
    svc = EvidenceCaptureService()
    empty = _road_frame()
    good = _vehicle_frame()
    svc._buffers["cam-b"] = _ring_with([(good, 99.9), (empty, 100.4)])
    evt = {"event_id": "e2", "bbox": VEHICLE_BBOX, "bbox_ts": 100.0}
    # frame_ts matches bbox_ts so _resolve_capture_frame keeps the (empty) live
    # frame; the quality guard must then recover the textured neighbor.
    out, ok = svc.resolve_aligned_frame("cam-b", evt, empty, frame_ts=100.0)
    assert ok is True
    assert out is not empty
    # Recovered frame contains the vehicle patch (dark red pixels present).
    assert int(out[220, 300, 2]) > 150


def test_resolve_aligned_frame_flags_unrecoverable_empty_bbox():
    svc = EvidenceCaptureService()
    empty1, empty2 = _road_frame(), _road_frame()
    svc._buffers["cam-c"] = _ring_with([(empty1, 99.8), (empty2, 100.3)])
    evt = {"event_id": "e3", "bbox": VEHICLE_BBOX, "bbox_ts": 100.0}
    out, ok = svc.resolve_aligned_frame("cam-c", evt, empty2, frame_ts=100.0)
    assert ok is False
    assert out is not None


def test_resolve_aligned_frame_no_bbox_is_trivially_ok():
    svc = EvidenceCaptureService()
    evt = {"event_id": "e4"}
    frame = _road_frame()
    out, ok = svc.resolve_aligned_frame("cam-d", evt, frame, frame_ts=None)
    assert ok is True
    assert out is frame


# --- ring buffer neighbor lookup ---------------------------------------------

def test_get_frames_near_ts_orders_by_proximity():
    a, b, c = _road_frame(), _vehicle_frame(), _road_frame()
    ring = _ring_with([(a, 10.0), (b, 11.0), (c, 12.0)])
    out = ring.get_frames_near_ts(11.1, max_frames=3)
    assert len(out) == 3
    assert out[0][1] == 11.0
    assert {ts for _, ts in out} == {10.0, 11.0, 12.0}


def test_get_frames_near_ts_empty_ring():
    ring = FrameRingBuffer(max_seconds=12, fps=12)
    assert ring.get_frames_near_ts(5.0) == []


# --- evidence_status must stay honest (C5) ------------------------------------

def test_capture_and_attach_partial_when_bbox_quality_bad(monkeypatch):
    svc = EvidenceCaptureService()
    uploads: list[dict] = []

    def fake_upload(org_id, camera_id, event_id, scene, subject, clip, meta, plate_jpeg=None):
        uploads.append(meta)
        return {"package": {"metadata": meta}}

    monkeypatch.setattr(svc._uploader, "upload", fake_upload)
    empty = _road_frame()
    svc._buffers["cam-e"] = _ring_with([(empty, 100.0)])
    evt = {"event_id": "e5", "bbox": VEHICLE_BBOX, "bbox_ts": 100.0}
    from citevision_ai.evidence.gate import default_evidence_policy

    svc._capture_and_attach(
        "cam-e", "org-1", evt, empty, default_evidence_policy(), frame_ts=100.0,
    )
    assert uploads, "upload must still happen (partial evidence beats none)"
    meta = uploads[0]
    assert meta["bbox_quality_ok"] is False
    assert meta["evidence_status"] == "partial"
    assert meta["capture_source"] == "live"
    assert evt["evidence_status"] == "partial"


def test_capture_and_attach_complete_when_quality_good(monkeypatch):
    svc = EvidenceCaptureService()
    uploads: list[dict] = []

    def fake_upload(org_id, camera_id, event_id, scene, subject, clip, meta, plate_jpeg=None):
        uploads.append(meta)
        return {"package": {"metadata": meta}}

    monkeypatch.setattr(svc._uploader, "upload", fake_upload)

    good = _vehicle_frame()
    svc._buffers["cam-f"] = _ring_with(
        [(good, 100.0 + i * 0.1) for i in range(-30, 31)]
    )
    evt = {"event_id": "e6", "bbox": VEHICLE_BBOX, "bbox_ts": 100.0}
    from citevision_ai.evidence.gate import default_evidence_policy

    svc._capture_and_attach(
        "cam-f", "org-1", evt, good, default_evidence_policy(), frame_ts=100.0,
    )
    assert uploads
    meta = uploads[0]
    assert meta["bbox_quality_ok"] is True
    assert meta["capture_source"] == "live"
    # scene/subject présents ; complete dépend du clip (ffmpeg dispo ou non),
    # mais le statut ne doit jamais être "complete" avec bbox_quality_ok=False.
    assert meta["evidence_status"] in ("complete", "partial")
