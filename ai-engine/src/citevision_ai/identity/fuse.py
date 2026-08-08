"""Fuse Frigate / InsightFace / Gemini identity votes (priority order)."""

from __future__ import annotations

from typing import Any


PRIORITY = ("frigate", "insightface", "gemini")


def _as_vote(raw: dict[str, Any] | None, *, source: str) -> dict[str, Any]:
    v = dict(raw or {})
    match = bool(v.get("match"))
    label = str(v.get("label") or "").strip() or None
    score = v.get("score")
    try:
        score_f = float(score) if score is not None else None
    except (TypeError, ValueError):
        score_f = None
    status = str(v.get("status") or ("ok" if "match" in v else "skipped"))
    out: dict[str, Any] = {
        "match": match and bool(label),
        "label": label if match else None,
        "score": score_f,
        "status": status,
        "source": str(v.get("source") or source),
    }
    if v.get("identifier"):
        out["identifier"] = v.get("identifier")
    if v.get("error"):
        out["error"] = v.get("error")
    # Strict: match without label is not a match
    if out["match"] and not out["label"]:
        out["match"] = False
    return out


def fuse_identity_votes(
    *,
    frigate: dict[str, Any] | None = None,
    insightface: dict[str, Any] | None = None,
    gemini: dict[str, Any] | None = None,
    face_clear: bool = True,
) -> dict[str, Any]:
    """Return fused decision with full vote audit trail.

    Priority: Frigate > InsightFace > Gemini.
    Fail-closed: timeout/error/skipped votes never invent a match.
    """
    votes = {
        "frigate": _as_vote(frigate, source="frigate"),
        "insightface": _as_vote(insightface, source="insightface"),
        "gemini": _as_vote(gemini, source="gemini"),
        "priority": list(PRIORITY),
    }
    winner = None
    label = None
    identifier = None
    score = None
    for name in PRIORITY:
        v = votes[name]
        if v.get("match") and v.get("label"):
            winner = name
            label = v["label"]
            identifier = v.get("identifier")
            score = v.get("score")
            break

    if winner:
        event_type = "face_watchlist_match"
    elif face_clear:
        event_type = "face_unknown"
    else:
        event_type = "face_detected"

    return {
        "event_type": event_type,
        "winner": winner,
        "label": label,
        "identifier": identifier,
        "score": score,
        "identity_votes": votes,
        "face_clear": bool(face_clear),
    }
