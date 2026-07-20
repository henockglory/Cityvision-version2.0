"""Speeding evidence: one Frigate attach per camera within the dedupe window."""

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


def test_speed_evidence_inflight_and_success_gate():
    svc = _svc()
    evt = {"event_type": "speeding", "track_id": 42}
    assert svc._begin_speed_evidence("cam-a", evt) is True
    # Second attempt blocked while in-flight.
    assert svc._begin_speed_evidence("cam-a", {"event_type": "speeding", "track_id": 99}) is False
    svc._finish_speed_evidence("cam-a", evt, success=False)
    # Failure clears inflight → retry allowed.
    assert svc._begin_speed_evidence("cam-a", evt) is True
    pkg = {"package": {"metadata": {"capture_source": "frigate_track"}}, "evidence_status": "complete"}
    svc._finish_speed_evidence("cam-a", evt, success=True, uploaded=pkg)
    # Success gates further attempts on this camera.
    assert svc._begin_speed_evidence("cam-a", {"event_type": "speeding", "track_id": 7}) is False
    assert svc._reuse_speed_evidence("cam-a") is pkg
    assert svc._begin_speed_evidence("cam-b", evt) is True


def test_non_speeding_not_gated():
    svc = _svc()
    assert svc._begin_speed_evidence("cam-a", {"event_type": "red_light"}) is True
    assert svc._should_skip_speed_evidence("cam-a", {"event_type": "red_light"}) is False
