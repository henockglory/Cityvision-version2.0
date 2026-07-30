"""Catalog honesty: event_types removed from Frigate+Gemini honest catalog.

Any residual emit of these IDs is dropped before MQTT/rules publication.
"""
from __future__ import annotations

PURGED_EVENT_TYPES: frozenset[str] = frozenset(
    {
        "phone_driving",
        "fighting",
        "falling",
        "fight_detected",
        "traffic_light_state",
        "behavior_anomaly",
        "running",
        "crowd_panic",
        "crowd_gathering",
        "queue_forming",
        "erratic_motion",
        "wandering",
        "rapid_activity",
        "tailgating",
        "carry_detected",
        "climb_detected",
        "crouch_detected",
        "object_appeared",
    }
)


def is_purged_event_type(event_type: str | None) -> bool:
    return bool(event_type) and str(event_type) in PURGED_EVENT_TYPES
