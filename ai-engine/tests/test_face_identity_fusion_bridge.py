"""Bridge _maybe_face fusion path with stubbed Frigate/IF/Gemini votes."""

from __future__ import annotations

from citevision_ai.frigate_bridge.bridge import FrigateEventBridge


def test_maybe_face_emits_fused_watchlist_match(monkeypatch):
    emitted: list[dict] = []

    bridge = FrigateEventBridge(
        frigate_url="http://127.0.0.1:5000",
        mqtt_host="127.0.0.1",
        mqtt_port=1884,
        spatial_resolver=lambda _c: {"zones": []},
        face_enabled=True,
        vlm_enabled=False,
        emit_event=emitted.append,
        watchlist_resolver=lambda: [
            {"identifier": "id-alice", "label": "Alice", "metadata": {"frigate_name": "Alice"}},
        ],
        face_match_vote=lambda _jpeg: {
            "match": False,
            "status": "ok",
            "face_clear": True,
            "source": "insightface",
        },
        face_reference_photos=lambda: [("Alice", b"\xff\xd8\xfffake")],
        face_gemini_compare=lambda *_a, **_k: {
            "match": True,
            "label": "Alice",
            "score": 0.91,
            "status": "ok",
            "source": "gemini",
        },
    )

    monkeypatch.setattr(
        "citevision_ai.frigate_bridge.bridge.fetch_subject_jpeg",
        lambda *_a, **_k: (b"\xff\xd8\xffcrop", {"x": 0.1, "y": 0.1, "width": 0.2, "height": 0.3}, {}),
    )
    monkeypatch.setattr(
        "citevision_ai.identity.votes.collect_frigate_vote",
        lambda *_a, **_k: {"match": False, "status": "no_sub_label", "source": "sub_label"},
    )

    bridge._maybe_face(
        "d2eb7076-c3b3-40fd-9b2c-0d119bb975c9",
        "evt-face-1",
        {"id": "evt-face-1", "label": "person", "camera": "cv_x"},
        {"zone_id": "Zone_Face", "behavior": "presence"},
    )

    types = [e.get("event_type") for e in emitted]
    assert "face_detected" in types
    assert "face_watchlist_match" in types
    match = next(e for e in emitted if e["event_type"] == "face_watchlist_match")
    votes = (match.get("metadata") or {}).get("identity_votes") or {}
    assert (match.get("metadata") or {}).get("identity_winner") == "gemini"
    assert votes.get("priority") == ["frigate", "insightface", "gemini"]
    assert votes.get("gemini", {}).get("match") is True


def test_maybe_face_frigate_priority_over_gemini(monkeypatch):
    emitted: list[dict] = []
    bridge = FrigateEventBridge(
        frigate_url="http://127.0.0.1:5000",
        mqtt_host="127.0.0.1",
        mqtt_port=1884,
        spatial_resolver=lambda _c: {"zones": []},
        face_enabled=True,
        emit_event=emitted.append,
        watchlist_resolver=lambda: [
            {"identifier": "id-bob", "label": "Bob", "metadata": {"frigate_name": "Bob"}},
        ],
        face_match_vote=lambda _jpeg: {
            "match": True,
            "label": "Other",
            "score": 0.99,
            "status": "ok",
            "face_clear": True,
        },
        face_reference_photos=lambda: [],
        face_gemini_compare=lambda *_a, **_k: {
            "match": True,
            "label": "Other",
            "score": 0.99,
            "status": "ok",
        },
    )
    monkeypatch.setattr(
        "citevision_ai.frigate_bridge.bridge.fetch_subject_jpeg",
        lambda *_a, **_k: (b"\xff\xd8\xffcrop", None, {}),
    )
    monkeypatch.setattr(
        "citevision_ai.identity.votes.collect_frigate_vote",
        lambda *_a, **_k: {
            "match": True,
            "label": "Bob",
            "score": 0.93,
            "status": "ok",
            "source": "sub_label",
        },
    )

    bridge._maybe_face(
        "cam1",
        "evt-face-2",
        {"id": "evt-face-2", "label": "person"},
        {"zone_id": "Z1", "behavior": "presence"},
    )
    match = next(e for e in emitted if e["event_type"] == "face_watchlist_match")
    assert (match.get("metadata") or {}).get("identity_winner") == "frigate"
    assert (match.get("metadata") or {}).get("label") == "Bob"
