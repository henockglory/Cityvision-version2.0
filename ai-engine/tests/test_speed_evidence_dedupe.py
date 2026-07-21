"""Speeding evidence: one Frigate attach per track within the dedupe window."""

from __future__ import annotations

import threading

from citevision_ai.evidence.service import EvidenceCaptureService


def _svc() -> EvidenceCaptureService:
    svc = EvidenceCaptureService.__new__(EvidenceCaptureService)
    svc._speed_evidence_dedupe = {}
    svc._speed_evidence_inflight = set()
    svc._speed_evidence_ok = {}
    svc._speed_evidence_last = {}
    svc._speed_evidence_lock = threading.Lock()
    return svc


def test_speed_evidence_per_track_not_per_camera():
    svc = _svc()
    evt_a = {"event_type": "speeding", "track_id": 42}
    evt_b = {"event_type": "speeding", "track_id": 99}
    assert svc._begin_speed_evidence("cam-a", evt_a) is True
    # Different track on same camera must NOT be blocked by inflight of another track.
    assert svc._begin_speed_evidence("cam-a", evt_b) is True
    # Same track blocked while in-flight.
    assert svc._begin_speed_evidence("cam-a", {"event_type": "speeding", "track_id": 42}) is False
    svc._finish_speed_evidence("cam-a", evt_a, success=False)
    svc._finish_speed_evidence("cam-a", evt_b, success=False)
    assert svc._begin_speed_evidence("cam-a", evt_a) is True
    pkg_a = {"package": {"metadata": {"capture_source": "frigate_track", "track_id": 42}}, "evidence_status": "complete"}
    svc._finish_speed_evidence("cam-a", evt_a, success=True, uploaded=pkg_a)
    # Same track gated after success.
    assert svc._begin_speed_evidence("cam-a", {"event_type": "speeding", "track_id": 42}) is False
    # Other track still allowed — this was the identical-scene bug.
    assert svc._begin_speed_evidence("cam-a", evt_b) is True
    pkg_b = {"package": {"metadata": {"capture_source": "frigate_track", "track_id": 99}}, "evidence_status": "complete"}
    svc._finish_speed_evidence("cam-a", evt_b, success=True, uploaded=pkg_b)
    assert svc._reuse_speed_evidence("cam-a", evt_a) is pkg_a
    assert svc._reuse_speed_evidence("cam-a", evt_b) is pkg_b
    # Must not cross-contaminate tracks.
    assert svc._reuse_speed_evidence("cam-a", {"event_type": "speeding", "track_id": 7}) is None


def test_non_speeding_not_gated():
    svc = _svc()
    assert svc._begin_speed_evidence("cam-a", {"event_type": "red_light"}) is True
    assert svc._should_skip_speed_evidence("cam-a", {"event_type": "red_light"}) is False
