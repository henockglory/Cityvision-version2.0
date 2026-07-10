"""E2E synthétique : zone_speed → événement speeding → preuve alignée.

Sans caméra 108 (handoff §9.5) : un véhicule synthétique traverse une zone
speed_measurement sur plusieurs frames ; on vérifie que :
- l'événement speeding porte bbox + bbox_ts de l'instant in-zone (B1, B2)
- la sélection pipeline conserve la bbox source (B4)
- la frame de preuve résolue contient le véhicule (C1, C2)
- le crop subject n'est pas de la route vide (C4)
- le clip est exporté centré sur bbox_ts si ffmpeg présent (D1)
"""

from __future__ import annotations

import shutil

import cv2
import numpy as np
import pytest

from citevision_ai.analytics.zone_speed import ZoneSpeedEngine
from citevision_ai.evidence.buffer import BufferedFrame, FrameRingBuffer
from citevision_ai.evidence.capture import (
    bbox_region_has_content,
    normalize_bbox,
    resolve_emission_track_bbox,
    subject_jpeg_texture,
)
from citevision_ai.evidence.gate import default_evidence_policy
from citevision_ai.evidence.service import EvidenceCaptureService

FW, FH = 1280, 720
T0 = 2000.0

ZONES = [
    {
        "zone_id": "z-speed",
        "behavior": "speed_measurement",
        "behavior_config": {
            "speed_limit_kmh": 5,
            "class_filter": "car",
            "distance_m": 10,
        },
        "polygon": [
            {"x": 0.2, "y": 0.4},
            {"x": 0.8, "y": 0.4},
            {"x": 0.8, "y": 0.8},
            {"x": 0.2, "y": 0.8},
        ],
    }
]


def _draw_vehicle(img: np.ndarray, x_px: int, y_px: int, w: int = 160, h: int = 100) -> None:
    cv2.rectangle(img, (x_px, y_px), (x_px + w, y_px + h), (40, 40, 200), -1)
    cv2.rectangle(img, (x_px + 20, y_px + 15), (x_px + w - 20, y_px + h - 40), (230, 230, 230), 3)
    cv2.circle(img, (x_px + 30, y_px + h - 8), 14, (15, 15, 15), -1)
    cv2.circle(img, (x_px + w - 30, y_px + h - 8), 14, (15, 15, 15), -1)


def _frame_with_vehicle_at(x_norm: float, y_norm: float) -> tuple[np.ndarray, dict]:
    """Route grise uniforme + véhicule ; bbox normalisée retournée."""
    img = np.full((FH, FW, 3), 120, dtype=np.uint8)
    w_px, h_px = 160, 100
    x_px = int(x_norm * FW)
    y_px = int(y_norm * FH)
    _draw_vehicle(img, x_px, y_px, w_px, h_px)
    bbox = {"x": x_px, "y": y_px, "width": w_px, "height": h_px}
    return img, bbox


def _crossing_scenario() -> tuple[list[tuple[np.ndarray, dict, float]], int]:
    """Véhicule traversant la zone en 0.6 s (rapide → speeding sûr)."""
    steps = []
    xs = [0.10, 0.30, 0.45, 0.60, 0.90]  # entre à l'étape 1, sort à l'étape 4
    for i, x in enumerate(xs):
        img, bbox = _frame_with_vehicle_at(x, 0.55)
        steps.append((img, bbox, T0 + i * 0.15))
    return steps, 4


def _run_crossing(engine: ZoneSpeedEngine) -> tuple[list[dict], list[tuple[np.ndarray, dict, float]]]:
    steps, _ = _crossing_scenario()
    events: list[dict] = []
    for img, bbox, ts in steps:
        track = {"track_id": 11, "class_name": "car", "bbox": bbox}
        events.extend(
            engine.process_frame(
                "cam-e2e", [track], ZONES, FW, FH, ts, "2026-07-08T15:00:00Z",
                frame_wall_ts=ts,
            )
        )
    return events, steps


def test_speeding_event_has_emission_frame_bbox_and_ts():
    engine = ZoneSpeedEngine()
    events, steps = _run_crossing(engine)
    speeding = [e for e in events if e.get("event_type") == "speeding"]
    assert speeding, f"aucun speeding émis, events={[e.get('event_type') for e in events]}"
    evt = speeding[0]
    last_ts = steps[-1][2]
    assert isinstance(evt.get("bbox_ts"), (int, float))
    assert evt["bbox_ts"] == last_ts
    bb = normalize_bbox(evt["bbox"], FW, FH)
    assert bb is not None
    last_img = steps[-1][0]
    assert bbox_region_has_content(last_img, bb), "bbox événement doit encadrer le véhicule sur la frame d'émission"


def test_pipeline_selection_uses_emission_track_bbox():
    engine = ZoneSpeedEngine()
    events, steps = _run_crossing(engine)
    evt = next(e for e in events if e.get("event_type") == "speeding")

    # Pipeline co-emission: current track on finalize frame wins.
    last_img, last_bbox, frame_wall_ts = steps[-1]
    tracks = [{"track_id": 11, "bbox": last_bbox}]
    noise_history = [
        {"bbox": {"x": 0.0, "y": 0.0, "width": 0.5, "height": 0.5}, "ts": T0 - 5.0},
    ]
    bb, bbox_ts, src = resolve_emission_track_bbox(
        evt, tracks, FW, FH, frame_wall_ts, last_bbox_fallback=noise_history[-1],
    )
    assert src == "emission_track"
    assert bb is not None
    assert bbox_ts == frame_wall_ts

    norm = normalize_bbox(bb, FW, FH)
    assert bbox_region_has_content(last_img, norm), "emission frame must contain vehicle in track bbox"


def test_full_evidence_capture_from_crossing(monkeypatch):
    engine = ZoneSpeedEngine()
    events, steps = _run_crossing(engine)
    evt = dict(next(e for e in events if e.get("event_type") == "speeding"))
    evt["event_id"] = "e2e-1"
    evt["bbox_source"] = "emission_track"

    svc = EvidenceCaptureService()
    ring = FrameRingBuffer(max_seconds=12, fps=12)
    for img, _, ts in steps:
        ok, enc = cv2.imencode(".jpg", img)
        assert ok
        ring._frames.append(BufferedFrame(jpeg=enc.tobytes(), ts=ts))
    ring._last_bgr = steps[-1][0]
    svc._buffers["cam-e2e"] = ring

    captured: dict = {}

    def fake_upload(org_id, camera_id, event_id, scene, subject, clip, meta, plate_jpeg=None):
        captured.update(
            scene=scene, subject=subject, clip=clip, meta=meta, plate=plate_jpeg,
        )
        return {"package": {"metadata": meta}}

    monkeypatch.setattr(svc._uploader, "upload", fake_upload)

    emission_frame, emission_bbox, emission_ts = steps[-1]
    evt["bbox"] = normalize_bbox(emission_bbox, FW, FH)
    evt["bbox_ts"] = emission_ts
    svc._capture_and_attach(
        "cam-e2e", "org-e2e", evt, emission_frame,
        default_evidence_policy(), frame_ts=emission_ts,
    )

    assert captured, "upload jamais appelé"
    meta = captured["meta"]
    assert meta["bbox_quality_ok"] is True
    assert meta["subject_quality_ok"] is True
    assert meta["bbox_source"] == "emission_track"
    assert meta["capture_source"] == "live"
    assert meta["bbox_ts"] == emission_ts
    assert meta["capture_frame_ts"] == emission_ts

    # C2 : le crop subject contient le véhicule (texture forte, pas route vide)
    subject = captured["subject"]
    assert subject
    tex = subject_jpeg_texture(subject)
    assert tex is not None and tex >= 50.0, f"subject sans texture (Laplacian={tex}) — route vide ?"
    arr = np.frombuffer(subject, dtype=np.uint8)
    crop = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    assert crop is not None and crop.size > 0
    # Le véhicule est rouge foncé : le crop doit contenir des pixels dominante rouge.
    red_pixels = int(((crop[:, :, 2] > 150) & (crop[:, :, 0] < 90)).sum())
    assert red_pixels > 200, f"véhicule absent du crop subject (red_pixels={red_pixels})"

    # C1 : scene = pleine frame, contient aussi le véhicule
    scene = captured["scene"]
    arr = np.frombuffer(scene, dtype=np.uint8)
    scene_img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    assert scene_img.shape[0] == FH and scene_img.shape[1] == FW

    # D1 : clip exporté si ffmpeg dispo
    if shutil.which("ffmpeg"):
        clip = captured["clip"]
        assert clip is not None and len(clip) >= 1024
        assert b"ftyp" in clip[:64]
        assert meta["evidence_status"] == "complete" or "plate" in meta.get("missing_roles", [])
    else:
        pytest.skip("ffmpeg absent — clip non vérifié")
