"""Sprint 1 — abort_stats + deferred red_light missing packages."""
from __future__ import annotations

from citevision_ai.evidence import abort_stats
from citevision_ai.evidence.frigate_track_evidence import FrigateTrackEvidence


def test_abort_stats_record_and_snapshot():
    abort_stats.reset()
    abort_stats.record_abort(
        abort_stats.ABORT_SCENE_GREEN,
        camera_id="aabbccdd-1111",
        event_type="red_light_violation",
        event_id="frigate-evt-1",
    )
    abort_stats.record_abort(
        abort_stats.ABORT_SCENE_GREEN,
        camera_id="aabbccdd-1111",
        event_type="red_light_violation",
        event_id="frigate-evt-2",
    )
    abort_stats.record_abort(
        abort_stats.ABORT_ALIGN_TOO_WIDE,
        camera_id="zzzzzzzz-2222",
        event_type="red_light_violation",
    )
    snap = abort_stats.snapshot()
    assert snap["total"] == 3
    assert snap["by_event_type"]["red_light_violation"]["scene_green"] == 2
    assert snap["by_event_type"]["red_light_violation"]["align_too_wide"] == 1
    assert snap["by_camera"]["aabbccdd"]["scene_green"] == 2
    abort_stats.reset()
    assert abort_stats.snapshot()["total"] == 0


def test_missing_package_structure():
    abort_stats.reset()
    ft = FrigateTrackEvidence()
    out = ft._missing(
        abort_stats.ABORT_CLIP_NOT_READY_TIMEOUT,
        camera_id="cam-12345678",
        evt={"event_type": "red_light_violation", "bbox_ts": 1.0, "track_id": 9},
        event_id="evt-abc",
        extra={"waited_sec": 30},
    )
    assert out["status"] == "missing"
    assert out["scene"] is None
    assert out["clip_bytes"] is None
    assert out["meta"]["evidence_status"] == "missing"
    assert out["meta"]["abort_reason"] == abort_stats.ABORT_CLIP_NOT_READY_TIMEOUT
    assert out["meta"]["waited_sec"] == 30
    snap = abort_stats.snapshot()
    assert snap["by_event_type"]["red_light_violation"]["clip_not_ready_timeout"] == 1
    abort_stats.reset()


def test_compose_red_light_waits_end_time_before_align_guard(monkeypatch):
    """Active Frigate events lack path_data — compose must wait for end_time and
    recompute align_delta instead of aborting align_too_wide with 1e18."""
    abort_stats.reset()
    ft = FrigateTrackEvidence()
    calls = {"n": 0}

    def fake_meta(_eid):
        calls["n"] += 1
        if calls["n"] < 2:
            return {"id": "e1", "start_time": 100.0, "data": {"box": [0.1, 0.1, 0.2, 0.2]}}
        return {
            "id": "e1",
            "start_time": 100.0,
            "end_time": 106.0,
            "data": {
                "box": [0.1, 0.1, 0.2, 0.2],
                "path_data": [[(0.15, 0.15), 100.5]],
            },
            "has_clip": True,
            "has_snapshot": True,
        }

    monkeypatch.setattr(ft, "_event_meta", fake_meta)
    monkeypatch.setattr(
        "citevision_ai.evidence.frigate_track_evidence.time.sleep",
        lambda _s: None,
    )
    from citevision_ai import config as cfg

    monkeypatch.setattr(cfg.settings, "frigate_red_light_end_time_wait_sec", 5.0, raising=False)
    monkeypatch.setattr(cfg.settings, "frigate_red_light_end_time_backoff_initial", 0.01, raising=False)
    monkeypatch.setattr(cfg.settings, "frigate_red_light_end_time_backoff_max", 0.01, raising=False)
    monkeypatch.setattr(cfg.settings, "demo_mode", False, raising=False)
    monkeypatch.setattr(ft, "_download_event_clip", lambda *_a, **_k: b"")
    monkeypatch.setattr(ft, "_red_light_frame_from_clip_at_anchor", lambda *_a, **_k: None)

    # Stale align_delta=1e18 as if fetch_event had no timestamps yet.
    out = ft._compose_from_matched(
        {"id": "e1", "start_time": 100.0, "data": {"box": [0.1, 0.1, 0.2, 0.2]}},
        align_delta=1e18,
        policy={"clip_seconds": 6, "images": []},
        evt={
            "event_type": "red_light_violation",
            "bbox_ts": 100.5,
            "metadata": {"hsv_light_state": "red", "bridge_source": "frigate"},
        },
        camera_id="camera-uuid-aaaa",
        org_id="org",
    )
    assert calls["n"] >= 2
    assert out is not None
    assert out["meta"]["abort_reason"] != abort_stats.ABORT_ALIGN_TOO_WIDE
    abort_stats.reset()


def test_compose_aborts_align_too_wide(monkeypatch):
    abort_stats.reset()
    ft = FrigateTrackEvidence()
    monkeypatch.setattr(ft, "_event_meta", lambda _eid: {"id": "e1", "end_time": 1.0})
    out = ft._compose_from_matched(
        {"id": "e1", "data": {"box": [0.1, 0.1, 0.2, 0.2]}},
        align_delta=20.0,
        policy={"clip_seconds": 6, "images": []},
        evt={"event_type": "red_light_violation", "bbox_ts": 100.0},
        camera_id="camera-uuid-aaaa",
        org_id="org",
    )
    assert out is not None
    assert out["status"] == "missing"
    assert out["meta"]["abort_reason"] == abort_stats.ABORT_ALIGN_TOO_WIDE
    abort_stats.reset()


def test_wait_until_end_time_ready(monkeypatch):
    ft = FrigateTrackEvidence()
    calls = {"n": 0}

    def fake_meta(_eid):
        calls["n"] += 1
        if calls["n"] < 2:
            return {"id": "e1", "has_clip": False}
        return {"id": "e1", "end_time": 123.4, "has_clip": True}

    monkeypatch.setattr(ft, "_event_meta", fake_meta)
    monkeypatch.setattr(
        "citevision_ai.evidence.frigate_track_evidence.time.sleep",
        lambda _s: None,
    )
    from citevision_ai import config as cfg

    monkeypatch.setattr(cfg.settings, "frigate_red_light_end_time_wait_sec", 5.0, raising=False)
    monkeypatch.setattr(cfg.settings, "frigate_red_light_end_time_backoff_initial", 0.01, raising=False)
    monkeypatch.setattr(cfg.settings, "frigate_red_light_end_time_backoff_max", 0.01, raising=False)

    meta = ft._wait_until_end_time("e1")
    assert meta is not None
    assert meta.get("end_time") == 123.4
    assert calls["n"] >= 2
