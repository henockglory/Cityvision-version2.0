"""Collect Frigate / InsightFace / Gemini identity votes for a live crop."""

from __future__ import annotations

import json
import logging
import os
import urllib.request
from typing import Any, Callable

logger = logging.getLogger(__name__)


def parse_frigate_sub_label(after: dict[str, Any]) -> tuple[str | None, float | None]:
    """Extract (name, score) from Frigate MQTT after.sub_label."""
    raw = after.get("sub_label")
    if raw is None:
        return None, None
    if isinstance(raw, str):
        name = raw.strip()
        return (name or None), None
    if isinstance(raw, (list, tuple)) and raw:
        name = str(raw[0] or "").strip()
        score = None
        if len(raw) > 1:
            try:
                score = float(raw[1])
            except (TypeError, ValueError):
                score = None
        return (name or None), score
    if isinstance(raw, dict):
        name = str(raw.get("name") or raw.get("label") or "").strip()
        score = raw.get("score") or raw.get("confidence")
        try:
            score_f = float(score) if score is not None else None
        except (TypeError, ValueError):
            score_f = None
        return (name or None), score_f
    return None, None


def frigate_vote_from_after(
    after: dict[str, Any],
    watchlist: list[dict[str, Any]],
) -> dict[str, Any]:
    name, score = parse_frigate_sub_label(after)
    if not name:
        return {"match": False, "status": "no_sub_label", "source": "sub_label"}
    matched = _match_watchlist_label(name, watchlist)
    if not matched:
        return {
            "match": False,
            "label": name,
            "score": score,
            "status": "unknown_label",
            "source": "sub_label",
        }
    return {
        "match": True,
        "label": matched.get("label") or name,
        "identifier": matched.get("identifier"),
        "score": score,
        "status": "ok",
        "source": "sub_label",
    }


def frigate_recognize_vote(
    frigate_url: str,
    jpeg: bytes,
    watchlist: list[dict[str, Any]],
    *,
    timeout: float = 8.0,
) -> dict[str, Any]:
    """POST /api/faces/recognize — fail-closed on transport errors."""
    if not jpeg or not frigate_url:
        return {"match": False, "status": "skipped", "error": "no_input", "source": "recognize"}
    boundary = "----citevisionFaceBoundary"
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="face.jpg"\r\n'
        f"Content-Type: image/jpeg\r\n\r\n"
    ).encode("utf-8") + jpeg + f"\r\n--{boundary}--\r\n".encode("utf-8")
    url = frigate_url.rstrip("/") + "/api/faces/recognize"
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:  # noqa: BLE001 — fail-closed vote
        logger.info("frigate recognize failed: %s", exc)
        return {
            "match": False,
            "status": "error",
            "error": "recognize_failed",
            "source": "recognize",
        }

    name = ""
    score = None
    if isinstance(payload, dict):
        name = str(
            payload.get("name")
            or payload.get("label")
            or payload.get("sub_label")
            or ""
        ).strip()
        score = payload.get("score") or payload.get("confidence")
        # some versions nest under data
        data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
        if not name and data:
            name = str(data.get("name") or data.get("label") or "").strip()
            score = score if score is not None else data.get("score")
    try:
        score_f = float(score) if score is not None else None
    except (TypeError, ValueError):
        score_f = None
    if not name or name.lower() in ("unknown", "none", "null"):
        return {
            "match": False,
            "score": score_f,
            "status": "ok",
            "source": "recognize",
        }
    matched = _match_watchlist_label(name, watchlist)
    if not matched:
        return {
            "match": False,
            "label": name,
            "score": score_f,
            "status": "unknown_label",
            "source": "recognize",
        }
    return {
        "match": True,
        "label": matched.get("label") or name,
        "identifier": matched.get("identifier"),
        "score": score_f,
        "status": "ok",
        "source": "recognize",
    }


def collect_frigate_vote(
    frigate_url: str,
    jpeg: bytes,
    after: dict[str, Any],
    watchlist: list[dict[str, Any]],
) -> dict[str, Any]:
    sub = frigate_vote_from_after(after, watchlist)
    if sub.get("match"):
        return sub
    return frigate_recognize_vote(frigate_url, jpeg, watchlist)


def gemini_identity_vote(
    compare_fn: Callable[..., dict[str, Any]] | None,
    query_jpeg: bytes,
    references: list[tuple[str, bytes]],
) -> dict[str, Any]:
    if compare_fn is None:
        return {"match": False, "status": "skipped", "error": "no_client", "source": "gemini"}
    if not references:
        return {"match": False, "status": "skipped", "error": "no_references", "source": "gemini"}
    try:
        min_conf = float(os.environ.get("GEMINI_FACE_IDENTITY_MIN_CONF", "0.75") or 0.75)
        timeout = float(os.environ.get("GEMINI_FACE_IDENTITY_TIMEOUT", "12") or 12)
        return compare_fn(
            query_jpeg,
            references,
            min_confidence=min_conf,
            timeout=timeout,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("gemini identity vote failed")
        return {
            "match": False,
            "status": "error",
            "error": str(exc)[:120],
            "source": "gemini",
        }


def _match_watchlist_label(name: str, watchlist: list[dict[str, Any]]) -> dict[str, Any] | None:
    needle = name.strip().lower()
    if not needle:
        return None
    for entry in watchlist:
        label = str(entry.get("label") or "").strip()
        ident = str(entry.get("identifier") or "").strip()
        meta = entry.get("metadata") or {}
        frig = str(meta.get("frigate_name") or "").strip()
        for cand in (label, ident, frig):
            if cand and cand.lower() == needle:
                return {
                    "label": label or cand,
                    "identifier": ident or None,
                }
    return None
