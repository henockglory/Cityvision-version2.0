"""Frigate camera/zone id helpers (must match backend/internal/frigate/config.go)."""
from __future__ import annotations


def frigate_camera_id(camera_uuid: str) -> str:
    return f"cv_{camera_uuid}"


def frigate_zone_id(zone_uuid: str) -> str:
    return f"cv_zone_{zone_uuid}"


def parse_camera_uuid(frigate_cam: str) -> str | None:
    raw = (frigate_cam or "").strip()
    if raw.startswith("cv_") and len(raw) > 3:
        return raw[3:]
    return None


def parse_zone_uuid(frigate_zone: str) -> str | None:
    raw = (frigate_zone or "").strip()
    if raw.startswith("cv_zone_") and len(raw) > 8:
        return raw[8:]
    return None
