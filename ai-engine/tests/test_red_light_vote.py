"""Tests for red-light vote strategies."""
from citevision_ai.road_enforcement.red_light_vote import (
    local_already_emitted,
    local_frigate_would_emit,
    mark_local_emitted,
    red_light_vote_mode,
)


def test_strict_and_no_local_emit(monkeypatch):
    monkeypatch.setenv("RED_LIGHT_VOTE_MODE", "strict_and")
    assert red_light_vote_mode() == "strict_and"
    assert not local_frigate_would_emit(hsv_gate_red=True, frigate_in_obs_zone=True)


def test_lf_or_g_local_path(monkeypatch):
    monkeypatch.setenv("RED_LIGHT_VOTE_MODE", "lf_or_g")
    assert local_frigate_would_emit(hsv_gate_red=True, frigate_in_obs_zone=True)
    assert not local_frigate_would_emit(hsv_gate_red=False, frigate_in_obs_zone=True)


def test_local_emit_dedupe(monkeypatch):
    monkeypatch.setenv("RED_LIGHT_VOTE_MODE", "lf_or_g")
    mark_local_emitted("evt-123")
    assert local_already_emitted("evt-123")
    assert not local_already_emitted("evt-other")
