"""Match events against synced rule evidence capture targets."""

from __future__ import annotations

import time
from typing import Any

from citevision_ai.detection.class_groups import matches_class_filter

def default_evidence_policy() -> dict[str, Any]:
    return {
        "enabled": True,
        "clip_seconds": 6,
        "images": [
            {"role": "scene", "label": "Vue d'ensemble", "crop": "full"},
            {"role": "subject", "label": "Cible détectée", "crop": "bbox", "padding_pct": 10, "zoom": 1.0},
        ],
        "min_confidence": 0.0,
    }


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
            policy = rule.get("evidence") or default_evidence_policy()
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
