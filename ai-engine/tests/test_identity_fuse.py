"""Unit tests for face identity vote fusion (Frigate > InsightFace > Gemini)."""

from citevision_ai.identity.fuse import fuse_identity_votes
from citevision_ai.identity.votes import frigate_vote_from_after, parse_frigate_sub_label


def test_fuse_priority_frigate_wins():
    out = fuse_identity_votes(
        frigate={"match": True, "label": "Alice", "score": 0.95, "status": "ok"},
        insightface={"match": True, "label": "Bob", "score": 0.99, "status": "ok"},
        gemini={"match": True, "label": "Carol", "score": 0.99, "status": "ok"},
        face_clear=True,
    )
    assert out["event_type"] == "face_watchlist_match"
    assert out["winner"] == "frigate"
    assert out["label"] == "Alice"


def test_fuse_insightface_when_frigate_abstains():
    out = fuse_identity_votes(
        frigate={"match": False, "status": "no_sub_label"},
        insightface={"match": True, "label": "Bob", "score": 0.72, "status": "ok"},
        gemini={"match": True, "label": "Carol", "score": 0.9, "status": "ok"},
        face_clear=True,
    )
    assert out["winner"] == "insightface"
    assert out["label"] == "Bob"


def test_fuse_gemini_only_when_others_abstain():
    out = fuse_identity_votes(
        frigate={"match": False, "status": "ok"},
        insightface={"match": False, "status": "ok", "face_clear": True},
        gemini={"match": True, "label": "Dana", "score": 0.88, "status": "ok"},
        face_clear=True,
    )
    assert out["winner"] == "gemini"
    assert out["label"] == "Dana"


def test_fuse_timeout_gemini_not_match():
    out = fuse_identity_votes(
        frigate={"match": False, "status": "ok"},
        insightface={"match": False, "status": "ok"},
        gemini={"match": False, "status": "timeout", "error": "timeout"},
        face_clear=True,
    )
    assert out["event_type"] == "face_unknown"
    assert out["winner"] is None


def test_fuse_no_face_clear():
    out = fuse_identity_votes(
        frigate={"match": False, "status": "skipped"},
        insightface={"match": False, "status": "no_face"},
        gemini={"match": False, "status": "skipped"},
        face_clear=False,
    )
    assert out["event_type"] == "face_detected"


def test_parse_sub_label_list():
    name, score = parse_frigate_sub_label({"sub_label": ["Eve", 0.91]})
    assert name == "Eve"
    assert abs(score - 0.91) < 1e-6


def test_frigate_vote_matches_watchlist_frigate_name():
    after = {"sub_label": "Eve Dupont"}
    wl = [{
        "identifier": "id1",
        "label": "Eve",
        "metadata": {"frigate_name": "Eve Dupont"},
    }]
    vote = frigate_vote_from_after(after, wl)
    assert vote["match"] is True
    assert vote["label"] == "Eve"
