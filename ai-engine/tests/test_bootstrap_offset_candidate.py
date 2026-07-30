"""Tests for bootstrap offset candidate buffering (frigate_timeline.py).

Covers the fix for the offset=none deadlock: a large IA↔Frigate skew must
never be promoted into _demo_clock_offset from a single IoU match — it needs
several mutually-consistent observations first.
"""
from __future__ import annotations

import pytest

from citevision_ai.evidence.frigate_timeline import (
    _BOOTSTRAP_CANDIDATE_TTL_SEC,
    _BOOTSTRAP_MIN_OBSERVATIONS,
    _BOOTSTRAP_TOLERANCE_SEC,
    clear_bootstrap_candidates,
    register_bootstrap_candidate,
)


@pytest.fixture
def candidates() -> dict:
    return {}


class TestRegisterBootstrapCandidate:
    def test_single_observation_not_confirmed(self, candidates):
        """One sample is never enough — must wait for min_observations."""
        result = register_bootstrap_candidate(candidates, "cam1", 350.0)
        assert result is None
        assert len(candidates["cam1"]) == 1

    def test_two_consistent_observations_not_yet_confirmed(self, candidates):
        """Two consistent samples still short of the 3-observation floor."""
        r1 = register_bootstrap_candidate(candidates, "cam1", 350.0)
        r2 = register_bootstrap_candidate(candidates, "cam1", 351.0)
        assert r1 is None
        assert r2 is None
        assert len(candidates["cam1"]) == 2

    def test_three_consistent_observations_confirms(self, candidates):
        """Three samples within tolerance of each other → promoted, buffer cleared."""
        register_bootstrap_candidate(candidates, "cam1", 350.0)
        register_bootstrap_candidate(candidates, "cam1", 351.0)
        confirmed = register_bootstrap_candidate(candidates, "cam1", 349.5)

        assert confirmed is not None
        assert confirmed == pytest.approx((350.0 + 351.0 + 349.5) / 3.0, abs=1e-6)
        # Buffer must be cleared after promotion — no leftover state.
        assert candidates["cam1"] == []

    def test_two_consistent_then_one_divergent_resets_buffer(self, candidates):
        """A jump beyond tolerance means the earlier pair likely matched a
        different loop cycle — the buffer resets to just the new sample,
        it is not silently dropped.
        """
        r1 = register_bootstrap_candidate(candidates, "cam1", 350.0)
        r2 = register_bootstrap_candidate(candidates, "cam1", 351.0)
        assert r1 is None and r2 is None
        assert len(candidates["cam1"]) == 2

        # Divergent sample: ~300s away from the running reference (351.0).
        r3 = register_bootstrap_candidate(candidates, "cam1", 650.0)

        assert r3 is None  # not confirmed — buffer restarted, only 1 sample now
        assert len(candidates["cam1"]) == 1
        assert candidates["cam1"][0][0] == 650.0

    def test_divergent_reset_then_needs_fresh_three_to_confirm(self, candidates):
        """After a reset, confirmation requires a fresh run of 3 consistent
        samples — the discarded ones must not count toward the new total.
        """
        register_bootstrap_candidate(candidates, "cam1", 350.0)
        register_bootstrap_candidate(candidates, "cam1", 351.0)
        register_bootstrap_candidate(candidates, "cam1", 650.0)  # divergent → reset

        r4 = register_bootstrap_candidate(candidates, "cam1", 651.0)
        r5 = register_bootstrap_candidate(candidates, "cam1", 649.5)

        assert r4 is None
        assert r5 is not None
        assert r5 == pytest.approx((650.0 + 651.0 + 649.5) / 3.0, abs=1e-6)

    def test_tolerance_boundary_is_inclusive_consistent(self, candidates):
        """A sample exactly at the tolerance boundary counts as consistent."""
        register_bootstrap_candidate(candidates, "cam1", 100.0)
        # Exactly _BOOTSTRAP_TOLERANCE_SEC away from the reference.
        r2 = register_bootstrap_candidate(
            candidates, "cam1", 100.0 + _BOOTSTRAP_TOLERANCE_SEC,
        )
        assert len(candidates["cam1"]) == 2
        r3 = register_bootstrap_candidate(candidates, "cam1", 100.5)
        assert r3 is not None

    def test_tolerance_boundary_exceeded_resets(self, candidates):
        """Just over the tolerance triggers a reset, not a silent accept."""
        register_bootstrap_candidate(candidates, "cam1", 100.0)
        register_bootstrap_candidate(candidates, "cam1", 100.5)
        r3 = register_bootstrap_candidate(
            candidates, "cam1", 100.0 + _BOOTSTRAP_TOLERANCE_SEC + 0.5,
        )
        assert r3 is None
        assert len(candidates["cam1"]) == 1  # reset to just this sample

    def test_cameras_are_independent(self, candidates):
        """A divergent sample on cam2 must not affect cam1's buffer."""
        register_bootstrap_candidate(candidates, "cam1", 350.0)
        register_bootstrap_candidate(candidates, "cam1", 351.0)
        register_bootstrap_candidate(candidates, "cam2", 999.0)

        confirmed = register_bootstrap_candidate(candidates, "cam1", 349.5)
        assert confirmed is not None
        assert len(candidates["cam2"]) == 1

    def test_custom_min_observations(self, candidates):
        """min_observations overrides the module default for callers that
        want a stricter/looser bootstrap (e.g. tests, or a future per-camera
        override)."""
        r1 = register_bootstrap_candidate(
            candidates, "cam1", 350.0, min_observations=2,
        )
        r2 = register_bootstrap_candidate(
            candidates, "cam1", 350.5, min_observations=2,
        )
        assert r1 is None
        assert r2 is not None

    def test_custom_tolerance(self, candidates):
        """A wider tolerance accepts a sample that the default would reset on."""
        register_bootstrap_candidate(
            candidates, "cam1", 350.0, tolerance_sec=10.0,
        )
        r2 = register_bootstrap_candidate(
            candidates, "cam1", 355.0, tolerance_sec=10.0,
        )
        assert len(candidates["cam1"]) == 2  # not reset — within widened tolerance


class TestClearBootstrapCandidates:
    def test_clear_removes_camera_bucket(self, candidates):
        register_bootstrap_candidate(candidates, "cam1", 350.0)
        clear_bootstrap_candidates(candidates, "cam1")
        assert "cam1" not in candidates

    def test_clear_on_absent_camera_is_noop(self, candidates):
        clear_bootstrap_candidates(candidates, "cam_never_seen")
        assert candidates == {}

    def test_clear_empty_camera_id_is_noop(self, candidates):
        register_bootstrap_candidate(candidates, "cam1", 350.0)
        clear_bootstrap_candidates(candidates, "")
        assert "cam1" in candidates  # untouched


class TestBootstrapIouGateIntegration:
    """These exercise the IoU/class gate that sits *before* a sample is even
    handed to register_bootstrap_candidate, inside _correlate_event's Pass 2b.
    A weak match must never reach the candidate buffer at all.
    """

    @staticmethod
    def _bootstrap_gate_passes(
        bootstrap_iou: float,
        class_ok: bool,
        start_candidate,
        *,
        min_bbox_iou: float = 0.12,
    ) -> bool:
        """Mirrors the gate added in _correlate_event Pass 2b before calling
        register_bootstrap_candidate — kept here as a small pure predicate so
        the threshold logic is unit-testable without the full pipeline.
        """
        return (
            bootstrap_iou >= min_bbox_iou
            and class_ok
            and isinstance(start_candidate, (int, float))
        )

    def test_iou_below_bootstrap_floor_never_counted(self, candidates):
        """IoU 0.06 (the loose ranking floor used just to pick *a* candidate
        out of the pool) must NOT be enough to register a bootstrap sample —
        only the real 0.12 floor promotes.
        """
        gate_ok = self._bootstrap_gate_passes(
            bootstrap_iou=0.06, class_ok=True, start_candidate=1000.0,
        )
        assert gate_ok is False
        # register_bootstrap_candidate must never be called in this branch;
        # simulate the pipeline's guard directly.
        if gate_ok:
            register_bootstrap_candidate(candidates, "cam1", 350.0)
        assert candidates == {}

    def test_iou_at_floor_is_accepted(self, candidates):
        gate_ok = self._bootstrap_gate_passes(
            bootstrap_iou=0.12, class_ok=True, start_candidate=1000.0,
        )
        assert gate_ok is True

    def test_class_mismatch_never_counted_even_with_high_iou(self, candidates):
        """A geometrically strong match on the wrong class (e.g. person vs
        car) must not seed the offset buffer."""
        gate_ok = self._bootstrap_gate_passes(
            bootstrap_iou=0.9, class_ok=False, start_candidate=1000.0,
        )
        assert gate_ok is False

    def test_missing_start_time_never_counted(self, candidates):
        """No usable Frigate timestamp on the matched event → nothing to
        learn an offset from, regardless of IoU."""
        gate_ok = self._bootstrap_gate_passes(
            bootstrap_iou=0.5, class_ok=True, start_candidate=None,
        )
        assert gate_ok is False


class TestMaybeLearnOffsetBootstrapVerified:
    """Integration-style tests against FrigateTrackEvidence._maybe_learn_offset
    to confirm the bootstrap_verified path bypasses the hard-align gate only
    when explicitly told to, and never regresses the Pass 1 (small-skew) path.
    """

    @pytest.fixture
    def evidence(self, monkeypatch):
        from citevision_ai.evidence.frigate_track_evidence import FrigateTrackEvidence
        from citevision_ai.config import settings as real_settings

        monkeypatch.setattr(real_settings, "frigate_demo_timeline_align", True, raising=False)
        monkeypatch.setattr(real_settings, "frigate_demo_max_align_sec", 10.0, raising=False)
        fte = FrigateTrackEvidence()
        return fte

    def test_small_skew_learns_directly_unchanged(self, evidence):
        """Pass 1 behaviour (delta within max_align) must be untouched by
        this patch — no bootstrap_verified needed, no regression."""
        # Wall-clock Frigate timestamps (>= 1e9) — matches live demo epochs.
        anchor = 1_700_000_010.0
        frigate_ev = {"start_time": 1_700_000_005.0}  # delta = 5s, within 10s max_align

        evidence._maybe_learn_offset("cam1", anchor, frigate_ev)

        assert "cam1" in evidence._demo_clock_offset
        assert evidence._demo_clock_offset["cam1"] == pytest.approx(5.0, abs=0.5)

    def test_large_skew_without_bootstrap_verified_is_not_learned(self, evidence):
        """A 400s skew must NOT be learned from a single unverified call —
        this is exactly the deadlock the patch closes."""
        anchor = 1_700_000_400.0
        frigate_ev = {"start_time": 1_700_000_000.0}  # delta = 400s

        evidence._maybe_learn_offset("cam1", anchor, frigate_ev)

        assert "cam1" not in evidence._demo_clock_offset

    def test_large_skew_with_bootstrap_verified_is_learned(self, evidence):
        """Once the caller asserts bootstrap_verified=True (i.e. the buffer
        already confirmed 3 consistent samples), the large offset is
        learned directly, bypassing the hard-align short-circuit."""
        anchor = 1_700_000_400.0
        frigate_ev = {"start_time": 1_700_000_000.0}  # delta = 400s

        evidence._maybe_learn_offset(
            "cam1", anchor, frigate_ev, bootstrap_verified=True,
        )

        assert "cam1" in evidence._demo_clock_offset
        assert evidence._demo_clock_offset["cam1"] == pytest.approx(400.0, abs=0.5)

    def test_reset_demo_offset_also_clears_bootstrap_candidates(self, evidence):
        """reset_demo_offset must wipe both the confirmed offset AND any
        in-progress bootstrap candidates — otherwise stale candidates from
        before a demo source switch could wrongly seed the new offset."""
        from citevision_ai.evidence.frigate_timeline import register_bootstrap_candidate

        register_bootstrap_candidate(evidence._demo_offset_candidates, "cam1", 350.0)
        register_bootstrap_candidate(evidence._demo_offset_candidates, "cam1", 351.0)
        evidence._demo_clock_offset["cam1"] = 123.0

        evidence.reset_demo_offset("cam1")

        assert "cam1" not in evidence._demo_clock_offset
        assert "cam1" not in evidence._demo_offset_candidates
