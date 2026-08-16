"""Match events against synced rule evidence capture targets."""

from __future__ import annotations

import time
from typing import Any

from citevision_ai.detection.class_groups import matches_class_filter

_ROAD_POLICY = {
    "enabled": True,
    "clip_seconds": 6,
    "images": [
        {"role": "scene", "label": "Vue d'ensemble", "crop": "full"},
        {"role": "subject", "label": "Cible détectée", "crop": "bbox", "padding_pct": 12, "zoom": 1.0},
        {"role": "plate", "label": "Plaque", "crop": "plate_rear", "padding_pct": 6, "zoom": 1.8},
    ],
    "min_confidence": 0.0,
    "fail_closed": ["subject", "plate"],
}

_FACE_WATCHLIST_POLICY = {
    "enabled": True,
    "clip_seconds": 6,
    "images": [
        {"role": "scene", "label": "Vue d'ensemble", "crop": "full"},
        {"role": "face", "label": "Visage", "crop": "bbox", "padding_pct": 8, "zoom": 1.2},
        {"role": "subject", "label": "Cible détectée", "crop": "bbox", "padding_pct": 10, "zoom": 1.0},
        {"role": "reference", "label": "Référence watchlist", "crop": "full"},
    ],
    "min_confidence": 0.0,
    "fail_closed": ["face", "reference"],
}

_FACE_POLICY = {
    "enabled": True,
    "clip_seconds": 6,
    "images": [
        {"role": "scene", "label": "Vue d'ensemble", "crop": "full"},
        {"role": "face", "label": "Visage", "crop": "bbox", "padding_pct": 8, "zoom": 1.2},
        {"role": "subject", "label": "Cible détectée", "crop": "bbox", "padding_pct": 10, "zoom": 1.0},
    ],
    "min_confidence": 0.0,
    "fail_closed": ["face"],
}

_CABIN_POLICY = {
    "enabled": True,
    "clip_seconds": 0,
    "images": [
        {"role": "scene", "label": "Vue d'ensemble", "crop": "full"},
        {"role": "subject", "label": "Cible détectée", "crop": "bbox", "padding_pct": 10, "zoom": 1.0},
    ],
    "min_confidence": 0.0,
    "fail_closed": ["scene", "subject"],
}

_GEOMETRY_POLICY = {
    "enabled": True,
    "clip_seconds": 6,
    "images": [
        {"role": "scene", "label": "Vue d'ensemble", "crop": "full"},
        {"role": "subject", "label": "Cible détectée", "crop": "bbox", "padding_pct": 10, "zoom": 1.0},
    ],
    "min_confidence": 0.0,
    "fail_closed": ["subject"],
}

# Plate: longer clip with approach so the car is seen entering the zone.
_PLATE_POLICY = {
    "enabled": True,
    "clip_seconds": 10,
    "images": [
        {"role": "scene", "label": "Vue d'ensemble", "crop": "full"},
        {"role": "subject", "label": "Cible détectée", "crop": "bbox", "padding_pct": 12, "zoom": 1.0},
        {"role": "plate", "label": "Plaque", "crop": "plate_rear", "padding_pct": 6, "zoom": 1.8},
    ],
    "min_confidence": 0.0,
    "fail_closed": ["subject", "plate"],
}


def default_evidence_policy(archetype: str | None = None, event_type: str | None = None) -> dict[str, Any]:
    """Archetype-aware default evidence policy (aligned with orchestration contract)."""
    arch = (archetype or "").strip().lower()
    et = (event_type or "").strip().lower()
    if et in ("face_watchlist_match", "watchlist_match") or (
        arch == "face" and "watchlist" in et
    ):
        return {**_FACE_WATCHLIST_POLICY, "images": [dict(x) for x in _FACE_WATCHLIST_POLICY["images"]]}
    if arch == "face" or et in ("face_detected", "face_unknown"):
        return {**_FACE_POLICY, "images": [dict(x) for x in _FACE_POLICY["images"]]}
    if arch == "cabin" or et in ("seatbelt_violation", "phone_use_violation"):
        return {**_CABIN_POLICY, "images": [dict(x) for x in _CABIN_POLICY["images"]]}
    if arch == "plate" or "plate" in et:
        return {**_PLATE_POLICY, "images": [dict(x) for x in _PLATE_POLICY["images"]]}
    if arch == "geometry" and "parking" not in et and "plate" not in et:
        return {**_GEOMETRY_POLICY, "images": [dict(x) for x in _GEOMETRY_POLICY["images"]]}
    return {**_ROAD_POLICY, "images": [dict(x) for x in _ROAD_POLICY["images"]]}


def sanitize_policy_roles(policy: dict[str, Any] | None, archetype: str | None = None, event_type: str | None = None) -> dict[str, Any]:
    """Strip roles that do not belong to the archetype (e.g. plate on face)."""
    pol = dict(policy or default_evidence_policy(archetype, event_type))
    arch = (archetype or "").strip().lower()
    et = (event_type or "").strip().lower()
    images = list(pol.get("images") or [])
    roles = {str(s.get("role") or "").lower() for s in images if isinstance(s, dict)}
    if arch == "face" or et.startswith("face_") or "watchlist" in et:
        images = [s for s in images if str(s.get("role") or "").lower() != "plate"]
        if not any(str(s.get("role") or "").lower() == "face" for s in images):
            images.append({"role": "face", "crop": "bbox"})
    elif arch == "cabin" or et in ("seatbelt_violation", "phone_use_violation"):
        images = [s for s in images if str(s.get("role") or "").lower() not in ("plate", "reference")]
        pol["clip_seconds"] = float(pol.get("clip_seconds") or 0)
    elif arch == "plate" or "plate" in et:
        if not any(str(s.get("role") or "").lower() == "plate" for s in images):
            images.append({"role": "plate", "crop": "plate_rear", "padding_pct": 6, "zoom": 1.8})
        pol["clip_seconds"] = max(float(pol.get("clip_seconds") or 0), 10.0)
    elif "plate" not in roles and arch in ("plate", "measure"):
        images.append({"role": "plate", "crop": "plate_rear", "padding_pct": 6, "zoom": 1.8})
    pol["images"] = images
    return pol


def _norm(s: str | None) -> str:
    return (s or "").strip().lower()


class EvidenceCaptureGate:
    """Capture only when event matches an active rule target; dedupe bursts."""

    def __init__(self) -> None:
        self._rules_by_camera: dict[str, list[dict[str, Any]]] = {}
        self._dedup: dict[str, float] = {}
        self._dedup_ttl = 60.0

    def set_rules(self, camera_id: str, rules: list[dict[str, Any]] | None) -> None:
        self._rules_by_camera[camera_id] = list(rules or [])

    def clear_camera(self, camera_id: str) -> None:
        self._rules_by_camera.pop(camera_id, None)

    def _dedup_key(self, camera_id: str, evt: dict[str, Any], rule_id: str) -> str:
        return "|".join(
            [
                camera_id,
                rule_id,
                str(evt.get("event_type") or evt.get("event") or ""),
                str(evt.get("zone_id") or ""),
                str(evt.get("track_id") or ""),
            ]
        )

    def _dedup_ok(self, key: str) -> bool:
        now = time.monotonic()
        expired = [k for k, t in self._dedup.items() if now - t > self._dedup_ttl]
        for k in expired:
            del self._dedup[k]
        if key in self._dedup:
            return False
        self._dedup[key] = now
        return True

    def match_policy(self, camera_id: str, evt: dict[str, Any]) -> dict[str, Any] | None:
        rules = self._rules_by_camera.get(camera_id) or []
        if not rules:
            return None
        et = _norm(str(evt.get("event_type") or evt.get("event") or ""))
        zone = _norm(str(evt.get("zone_id") or ""))
        cls = _norm(str(evt.get("class_name") or ""))
        conf = float(evt.get("confidence") or 0)
        for rule in rules:
            if rule.get("enabled") is False:
                continue
            archetype = str(rule.get("archetype") or "")
            policy = rule.get("evidence")
            if not policy:
                policy = default_evidence_policy(archetype, et)
            else:
                policy = sanitize_policy_roles(policy, archetype, et)
            if policy.get("enabled") is False:
                continue
            want_et = _norm(str(rule.get("event_type") or ""))
            if want_et and want_et != et:
                continue
            want_zone = _norm(str(rule.get("zone_id") or ""))
            # Only scope by zone when the event carries zone_id (secondary ONNX often omits it).
            if want_zone and zone and want_zone != zone:
                continue
            want_class = _norm(str(rule.get("class_filter") or rule.get("class_name") or ""))
            if want_class and want_class not in ("any", "*") and cls and not matches_class_filter(cls, want_class):
                continue
            min_conf = float(policy.get("min_confidence") or 0)
            if conf > 0 and conf < min_conf:
                continue
            rule_id = str(rule.get("rule_id") or rule.get("id") or "")
            key = self._dedup_key(camera_id, evt, rule_id)
            if not self._dedup_ok(key):
                continue
            return policy
        return None
