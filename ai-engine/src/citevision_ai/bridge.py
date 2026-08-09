"""Frigate MQTT event bridge → Gemini VLM / speeding emits."""
from __future__ import annotations

import json
import logging
import os
import threading
import time
import uuid
import urllib.request
from datetime import datetime, timezone
from typing import Any, Callable

import paho.mqtt.client as mqtt

from citevision_ai.frigate_bridge.ids import parse_camera_uuid, parse_zone_uuid
from citevision_ai.frigate_bridge.snapshot import (
    classify_snapshot_light_state,
    download_snapshot_jpeg,
    fetch_cabin_jpeg,
    fetch_red_light_jpeg,
    fetch_subject_jpeg,
    wait_snapshot_ready,
)

logger = logging.getLogger(__name__)

EmitCallback = Callable[[dict[str, Any]], None]
SpatialResolver = Callable[[str], dict[str, Any] | None]
LightStateResolver = Callable[[str], str]
LightDebugResolver = Callable[[str], dict[str, Any]]
CameraIdsResolver = Callable[[], list[str]]

_CABIN_BEHAVIORS = frozenset({"seatbelt", "phone_use", "driver_cabin"})
_BEHAVIOR_TO_RULES: dict[str, list[str]] = {
    "seatbelt": ["seatbelt_violation"],
    "phone_use": ["phone_use_violation"],
    "driver_cabin": ["seatbelt_violation", "phone_use_violation"],
}
_VEHICLE_LABELS = frozenset({
    "car", "truck", "bus", "motorcycle", "motorbike", "van", "vehicle",
})
_FACE_SKIP_BEHAVIORS = frozenset({
    "speed_measurement",
    "red_light_observation",
    "traffic_light_color",
    "plate_ocr",
    "count_crossings",
    "seatbelt",
    "phone_use",
    "driver_cabin",
})
_GEOMETRY_ENTER_BEHAVIORS = frozenset({
    "", "presence", "perimeter", "loitering", "parking", "abandoned_object",
})
_GEOMETRY_EXIT_BEHAVIORS = frozenset({"controlled_exit"})
_DWELL_BEHAVIOR_EVENTS = {
    "presence": ("zone_presence", "person"),
    "loitering": ("loitering", "person"),
    "parking": ("vehicle_stopped", "vehicle"),
}
_VEHICLE_LABELS_GEOM = frozenset({
    "car", "truck", "bus", "motorcycle", "motorbike", "van", "vehicle",
})
_PERSON_LABELS = frozenset({"person"})
_OBJECT_LIKE_LABELS = frozenset({
    "backpack", "handbag", "suitcase", "umbrella", "bottle", "cup",
    "sports ball", "bag", "package", "box",
})
_TRAFFIC_ZONE_BEHAVIORS = frozenset({
    "speed_measurement", "parking", "red_light_observation",
})


class FrigateEventBridge:
    """Subscribe to frigate/events; enqueue Gemini jobs or emit speeding."""

    def __init__(
        self,
        *,
        frigate_url: str,
        mqtt_host: str,
        mqtt_port: int,
        spatial_resolver: SpatialResolver,
        vlm_queue: Any | None = None,
        emit_event: EmitCallback | None = None,
        vlm_enabled: bool = False,
        speed_enabled: bool = False,
        face_enabled: bool = False,
        plate_enabled: bool = False,
        geometry_enabled: bool = False,
        mqtt_user: str = "",
        mqtt_password: str = "",
        snapshot_wait_sec: float = 25.0,
        watchlist_resolver: Callable[[], list[dict[str, Any]]] | None = None,
        light_state_resolver: LightStateResolver | None = None,
        light_debug_resolver: LightDebugResolver | None = None,
        camera_ids_resolver: CameraIdsResolver | None = None,
        face_match_jpeg: Callable[[bytes], list[dict[str, Any]]] | None = None,
    ) -> None:
        self._frigate_url = (frigate_url or "http://127.0.0.1:5000").rstrip("/")
        self._mqtt_host = mqtt_host
        self._mqtt_port = int(mqtt_port)
        self._mqtt_user = mqtt_user or ""
        self._mqtt_password = mqtt_password or ""
        self._spatial = spatial_resolver
        self._vlm_queue = vlm_queue
        self._emit = emit_event
        self._vlm_enabled = bool(vlm_enabled) and vlm_queue is not None
        self._speed_enabled = bool(speed_enabled)
        self._face_enabled = bool(face_enabled) and vlm_queue is not None
        self._plate_enabled = bool(plate_enabled) and vlm_queue is not None
        self._geometry_enabled = bool(geometry_enabled)
        self._snapshot_wait = float(snapshot_wait_sec)
        self._watchlist_resolver = watchlist_resolver
        self._light_state = light_state_resolver
        self._light_debug = light_debug_resolver
        self._camera_ids = camera_ids_resolver
        self._face_match_jpeg = face_match_jpeg
        self._client: mqtt.Client | None = None
        self._stop = threading.Event()
        self._seen: dict[str, float] = {}
        self._red_light_active: dict[str, tuple[float, dict[str, Any], dict[str, Any], dict[str, dict[str, Any]]]] = {}
        self._seen_lock = threading.Lock()
        # dwell: key = f"{event_id}:{zone_uuid}:{rule}" → first_seen_monotonic
        self._dwell_since: dict[str, float] = {}
        # zone occupancy for absence: key = f"{camera_id}:{zone_uuid}" → last_seen_monotonic
        self._zone_last_seen: dict[str, float] = {}
        # proximity: last emit per pair
        self._proximity_seen: dict[str, float] = {}
        # count snapshots for density
        self._zone_track_counts: dict[str, set[str]] = {}
        self._stats: dict[str, Any] = {
            "mqtt_messages": 0,
            "cabin_enqueued": 0,
            "cabin_snapshot_fail": 0,
            "cabin_skipped_too_small": 0,
            "face_enqueued": 0,
            "plate_enqueued": 0,
            "geometry_emitted": 0,
            "dwell_emitted": 0,
            "absence_emitted": 0,
            "count_emitted": 0,
            "proximity_emitted": 0,
            "slow_emitted": 0,
            "sudden_stop_emitted": 0,
            "abandoned_emitted": 0,
            "red_light_enqueued": 0,
            "red_light_skipped_not_red": 0,
            "red_light_skipped_unknown": 0,
            "red_light_skipped_stable_not_red": 0,
            "red_light_skipped_frigate_snapshot_not_red": 0,
            "red_light_snapshot_fail": 0,
            "red_light_gate_grace": 0,
            "red_light_cached_retries": 0,
            "red_light_skipped_bbox_outside_zone": 0,
            "red_light_skipped_stale_bbox": 0,
            "red_light_poll_events": 0,
            "red_light_memory_candidates": 0,
            "red_light_memory_enqueued": 0,
            "red_light_memory_expired": 0,
            "red_light_memory_outside_zone": 0,
            "lf_or_g_would_emit": 0,
            "lf_or_g_emitted": 0,
            "lf_or_g_shadow": 0,
            "speed_emitted": 0,
            "speed_below_limit": 0,
            "speed_no_estimate": 0,
            "speed_shadow_max": 0,
            "dropped_dedupe": 0,
            "snapshot_fail": 0,
            "mqtt_by_camera": {},
        }
        self._stats_lock = threading.Lock()
        self._speed_peak: dict[str, float] = {}
        # Frigate detect resolution per camera (cv_-prefixed name) — MQTT boxes
        # are detect-resolution pixels, NOT 1920x1080.
        self._detect_wh_cache: dict[str, tuple[float, float]] = {}

    @property
    def enabled(self) -> bool:
        return (
            self._vlm_enabled
            or self._speed_enabled
            or self._face_enabled
            or self._plate_enabled
            or self._geometry_enabled
        )

    def stats(self) -> dict[str, Any]:
        with self._stats_lock:
            out = {k: v for k, v in self._stats.items() if k != "mqtt_by_camera"}
            out["mqtt_by_camera"] = dict(self._stats.get("mqtt_by_camera") or {})
            return out

    def start(self) -> None:
        if not self.enabled:
            return
        if self._client is not None:
            return
        self._stop.clear()
        client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id=f"citevision-frigate-bridge-{int(time.time()) % 100000}",
        )
        if self._mqtt_user:
            client.username_pw_set(self._mqtt_user, self._mqtt_password or None)
        client.on_connect = self._on_connect
        client.on_message = self._on_message
        self._client = client
        try:
            client.connect(self._mqtt_host, self._mqtt_port, keepalive=60)
            client.loop_start()
            logger.info(
                "frigate_bridge started host=%s:%s vlm=%s speed=%s face=%s plate=%s",
                self._mqtt_host,
                self._mqtt_port,
                self._vlm_enabled,
                self._speed_enabled,
                self._face_enabled,
                self._plate_enabled,
            )
            poll_enabled = str(os.environ.get("FRIGATE_RED_LIGHT_POLL_ENABLE", "1")).strip().lower() in (
                "1", "true", "yes", "on",
            )
            if poll_enabled and self._vlm_enabled and self._camera_ids is not None:
                threading.Thread(
                    target=self._poll_red_light_events_loop,
                    name="frigate-bridge-red-poll",
                    daemon=True,
                ).start()
        except Exception:
            logger.exception("frigate_bridge mqtt connect failed")
            self._client = None

    def stop(self) -> None:
        self._stop.set()
        c = self._client
        self._client = None
        if c is not None:
            try:
                c.loop_stop()
                c.disconnect()
            except Exception:
                pass

    def _on_connect(self, client: mqtt.Client, *_args: Any) -> None:
        client.subscribe("frigate/events", qos=0)

    def _on_message(self, _client: mqtt.Client, _userdata: Any, msg: mqtt.MQTTMessage) -> None:
        with self._stats_lock:
            self._stats["mqtt_messages"] += 1
        try:
            payload = json.loads(msg.payload.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return
        if not isinstance(payload, dict):
            return
        after = payload.get("after")
        before = payload.get("before")
        if not isinstance(after, dict):
            return
        threading.Thread(
            target=self._handle_event,
            args=(after, before if isinstance(before, dict) else {}),
            name="frigate-bridge-evt",
            daemon=True,
        ).start()

    def _poll_red_light_events_loop(self) -> None:
        try:
            poll_sec = float(os.environ.get("FRIGATE_RED_LIGHT_POLL_SEC", "2.0") or 2.0)
        except (TypeError, ValueError):
            poll_sec = 2.0
        poll_sec = max(1.0, poll_sec)
        while not self._stop.wait(poll_sec):
            try:
                camera_ids = list(self._camera_ids() if self._camera_ids is not None else [])
            except Exception:
                logger.exception("frigate_bridge red_light poll camera resolver failed")
                continue
            for camera_id in camera_ids:
                try:
                    self._poll_red_light_camera(camera_id)
                except Exception:
                    logger.exception("frigate_bridge red_light poll failed camera=%s", camera_id[:8])

    def _poll_red_light_camera(self, camera_id: str) -> None:
        spatial = self._spatial(camera_id) or {}
        zones = spatial.get("zones") if isinstance(spatial.get("zones"), list) else []
        if not any(
            FrigateEventBridge._zone_behavior(z) == "red_light_observation"
            for z in zones
            if isinstance(z, dict)
        ):
            return
        gate_red = self._red_light_gate_is_red(camera_id)
        zone_by_uuid = self._index_zones(zones)
        memory_sec = self._red_light_memory_sec()
        cam_f = f"cv_{camera_id}"
        url = f"{self._frigate_url}/api/events?camera={cam_f}&limit=20"
        with urllib.request.urlopen(url, timeout=8.0) as resp:
            events = json.loads(resp.read().decode("utf-8"))
        if not isinstance(events, list):
            return
        now = time.time()
        candidates: list[tuple[float, dict[str, Any]]] = []
        for ev in events:
            if not isinstance(ev, dict):
                continue
            label = str(ev.get("label") or "").lower().strip()
            if label not in _VEHICLE_LABELS:
                continue
            end_time = ev.get("end_time")
            if end_time is not None:
                try:
                    if now - float(end_time) > memory_sec:
                        continue
                except (TypeError, ValueError):
                    continue
            bbox_ts = self._bbox_ts_from_after(ev, now)
            demo_loop = str(os.environ.get("DEMO_MODE", "")).strip().lower() in ("1", "true", "yes")
            if not demo_loop and abs(now - bbox_ts) > memory_sec:
                with self._stats_lock:
                    self._stats["red_light_skipped_stale_bbox"] = int(
                        self._stats.get("red_light_skipped_stale_bbox") or 0
                    ) + 1
                continue
            if not ev.get("camera"):
                ev = {**ev, "camera": cam_f}
            obs_zinfo = self._red_light_obs_zone_for_bbox(ev, zone_by_uuid)
            if obs_zinfo is None:
                with self._stats_lock:
                    self._stats["red_light_memory_outside_zone"] = int(
                        self._stats.get("red_light_memory_outside_zone") or 0
                    ) + 1
                continue
            score = self._red_light_event_score(ev, zone_by_uuid=zone_by_uuid, now=now)
            if score <= 0:
                continue
            # Only remember this track as a red-light candidate when the vehicle was
            # actually observed while the gate was already red — retrying it later
            # against a *future* red phase would falsely tie a green/amber crossing
            # to an unrelated red window (never finds a red frame in its own clip).
            if gate_red:
                self._remember_red_light_track(str(ev.get("id") or ""), ev, obs_zinfo, zone_by_uuid)
            candidates.append((score, ev))
        if candidates:
            with self._stats_lock:
                self._stats["red_light_poll_events"] = int(self._stats.get("red_light_poll_events") or 0) + len(candidates)
                self._stats["red_light_memory_candidates"] = int(
                    self._stats.get("red_light_memory_candidates") or 0
                ) + len(candidates)
        if gate_red:
            self._retry_cached_red_light_tracks(camera_id=camera_id)

    def _handle_event(self, after: dict[str, Any], before: dict[str, Any]) -> None:
        cam_f = str(after.get("camera") or "")
        camera_id = parse_camera_uuid(cam_f)
        if not camera_id:
            return
        with self._stats_lock:
            by_cam = self._stats.setdefault("mqtt_by_camera", {})
            if not isinstance(by_cam, dict):
                by_cam = {}
                self._stats["mqtt_by_camera"] = by_cam
            by_cam[camera_id] = int(by_cam.get(camera_id) or 0) + 1
        spatial = self._spatial(camera_id) or {}
        zones = spatial.get("zones") if isinstance(spatial.get("zones"), list) else []
        zone_by_uuid = self._index_zones(zones)
        label = str(after.get("label") or "").lower().strip()
        event_id = str(after.get("id") or "")
        if not event_id:
            return

        current = set(self._zone_list(after.get("current_zones")))
        entered = set(self._zone_list(after.get("entered_zones")))
        before_zones = set(self._zone_list(before.get("current_zones"))) if before else set()
        exited = before_zones - current

        # Red light / cabin / face / plate: use Frigate MQTT zones when present, and
        # infer them from the Frigate bbox when Frigate emits current_zones=[].
        active_zone_ids = (
            self._active_frigate_zones(after)
            | entered
            | current
            | self._infer_active_zones_from_bbox(after, zone_by_uuid)
        )
        for fz in active_zone_ids:
            zuuid = parse_zone_uuid(fz)
            if not zuuid:
                continue
            zinfo = zone_by_uuid.get(zuuid)
            if not zinfo:
                # One-shot debug when spatial has zones but MQTT zone never resolves
                if zone_by_uuid and self._stats.get("mqtt_messages", 0) < 20:
                    logger.info(
                        "frigate_bridge zone_miss fz=%s known=%s",
                        fz, list(zone_by_uuid.keys())[:6],
                    )
                continue
            behavior = str(zinfo.get("behavior") or zinfo.get("zone_kind") or "")
            bcfg = zinfo.get("behavior_config")
            if not behavior and isinstance(bcfg, dict):
                behavior = str(bcfg.get("behavior") or "")
            # Cabin: Frigate vehicle bbox → Gemini (no local YOLO crop).
            if (
                self._vlm_enabled
                and behavior in _CABIN_BEHAVIORS
                and self._label_allowed(label, zinfo, allow_person_default=True)
            ):
                self._maybe_cabin(camera_id, event_id, after, zinfo, behavior)
            if self._vlm_enabled and self._label_allowed(label, zinfo) and behavior == "red_light_observation":
                # Only cache this track as a red-light candidate when the gate is
                # already red at detection time (see _poll_red_light_camera for why).
                if self._red_light_gate_is_red(camera_id):
                    self._remember_red_light_track(event_id, after, zinfo, zone_by_uuid)
                self._maybe_red_light(camera_id, event_id, after, zinfo, zone_by_uuid)
            if self._face_enabled and label == "person" and behavior not in _FACE_SKIP_BEHAVIORS:
                self._maybe_face(camera_id, event_id, after, zinfo)
            if self._plate_enabled and self._label_allowed(label, zinfo) and behavior == "plate_ocr":
                self._maybe_plate(camera_id, event_id, after, zinfo)
            if self._geometry_enabled and self._label_allowed(
                label, zinfo, allow_person_default=(behavior in ("presence", "perimeter", "loitering", "")),
            ):
                self._maybe_geometry_active(camera_id, event_id, after, zinfo, behavior, label)
                self._maybe_pedestrian_in_traffic(camera_id, event_id, after, zinfo, behavior, label)
                if behavior == "abandoned_object" or label in _OBJECT_LIKE_LABELS:
                    self._maybe_abandoned_active(camera_id, event_id, after, zinfo, behavior, label)

        # Geometry: zone exit emits (controlled_exit / zone_exit)
        if self._geometry_enabled:
            for fz in exited:
                zuuid = parse_zone_uuid(fz)
                if not zuuid:
                    continue
                zinfo = zone_by_uuid.get(zuuid)
                if not zinfo:
                    continue
                behavior = str(zinfo.get("behavior") or zinfo.get("zone_kind") or "")
                if not self._label_allowed(label, zinfo, allow_person_default=True):
                    continue
                self._maybe_geometry_exit(camera_id, event_id, after, zinfo, behavior, label)
                if behavior == "abandoned_object" or label in _OBJECT_LIKE_LABELS:
                    self._maybe_object_removed(camera_id, event_id, after, zinfo, behavior, label)

        # Speed: peak tracking in-zone (shadow / diagnostics only when exit mode).
        # Label filtering is per-zone via _label_allowed (track_objects config,
        # vehicle default) so speed zones can watch any Frigate label.
        if self._speed_enabled:
            in_speed_zones = active_zone_ids | entered | current
            for fz in in_speed_zones:
                zuuid = parse_zone_uuid(fz)
                if not zuuid:
                    continue
                zinfo = zone_by_uuid.get(zuuid)
                if not zinfo or str(zinfo.get("behavior") or "") != "speed_measurement":
                    continue
                if not self._label_allowed(label, zinfo):
                    continue
                self._maybe_speed_in_zone(camera_id, event_id, after, before, zinfo)

        # Speed: tracked object left a speed_measurement zone with estimate
        if self._speed_enabled:
            for fz in exited:
                zuuid = parse_zone_uuid(fz)
                if not zuuid:
                    continue
                zinfo = zone_by_uuid.get(zuuid)
                if not zinfo or str(zinfo.get("behavior") or "") != "speed_measurement":
                    continue
                if not self._label_allowed(label, zinfo):
                    continue
                self._maybe_speed(camera_id, event_id, after, before, zinfo)
                self._maybe_slow_vehicle(camera_id, event_id, after, before, zinfo)
                self._maybe_sudden_stop(camera_id, event_id, after, before, zinfo)

        if self._geometry_enabled:
            self._maybe_proximity(camera_id, event_id, after, zone_by_uuid, label)
            self._maybe_zone_absence(camera_id, zone_by_uuid)
            self._maybe_zone_counts(camera_id, zone_by_uuid)

        self._retry_cached_red_light_tracks(skip_event_id=event_id)

    def _index_zones(self, zones: list[Any]) -> dict[str, dict[str, Any]]:
        """Index by DB uuid so Frigate ``cv_zone_<uuid>`` resolves via parse_zone_uuid."""
        out: dict[str, dict[str, Any]] = {}
        for z in zones:
            if not isinstance(z, dict):
                continue
            for key in ("id", "uuid", "zone_uuid"):
                zid = str(z.get(key) or "").strip()
                if zid:
                    out[zid] = z
            # Some payloads only carry zone_id as the UUID string.
            alt = str(z.get("zone_id") or "").strip()
            if alt and len(alt) >= 32 and alt.count("-") >= 4 and alt not in out:
                out[alt] = z
        return out

    @staticmethod
    def _zone_list(raw: Any) -> list[str]:
        if isinstance(raw, list):
            return [str(x) for x in raw if x]
        return []

    @staticmethod
    def _active_frigate_zones(after: dict[str, Any]) -> set[str]:
        """Union of zone name lists Frigate may put on the MQTT after payload."""
        names: set[str] = set()
        for key in ("current_zones", "entered_zones", "zones"):
            names.update(FrigateEventBridge._zone_list(after.get(key)))
        data = after.get("data") if isinstance(after.get("data"), dict) else {}
        for key in ("current_zones", "entered_zones", "zones"):
            names.update(FrigateEventBridge._zone_list(data.get(key)))
        return names

    def _red_light_gate_is_red(self, camera_id: str) -> bool:
        """Track-memorization gate: requires BOTH the raw (this-frame) and the
        stable (majority-vote) HSV state to be red, regardless of
        RED_LIGHT_GATE_MODE — a single noisy/misdecoded frame (e.g. transient
        phase skew between the AI engine's own ingest and Frigate's separate
        encode of the same looping demo video) must not be enough to cache a
        track whose Frigate clip may never show red. This gate only guards
        _remember_red_light_track (poll + handle_event); the immediate VLM
        enqueue path in _maybe_red_light has its own gate_mode logic plus
        Gemini confirmation downstream and is unaffected."""
        try:
            if self._light_debug is not None:
                dbg = dict(self._light_debug(camera_id) or {})
                return (
                    str(dbg.get("raw") or "").lower().strip() == "red"
                    and str(dbg.get("stable") or "").lower().strip() == "red"
                )
            if self._light_state is not None:
                return str(self._light_state(camera_id) or "").lower().strip() == "red"
        except Exception:
            logger.exception("frigate_bridge red_light gate probe failed camera=%s", camera_id[:8])
        return False

    def _red_light_event_score(
        self,
        ev: dict[str, Any],
        *,
        zone_by_uuid: dict[str, dict[str, Any]],
        now: float,
    ) -> float:
        """Score Frigate candidates; positive score means vehicle bbox is in observation."""
        box = self._vehicle_bbox_norm(ev)
        if not box:
            return 0.0
        in_obs = False
        for zinfo in zone_by_uuid.values():
            if self._zone_behavior(zinfo) != "red_light_observation":
                continue
            if self._bbox_center_in_zone(box, zinfo):
                in_obs = True
                break
        if not in_obs:
            return 0.0
        try:
            area = float(box.get("width") or 0) * float(box.get("height") or 0)
        except (TypeError, ValueError):
            area = 0.0
        bbox_ts = self._bbox_ts_from_after(ev, now)
        recency = max(0.0, 12.0 - abs(now - bbox_ts))
        active_bonus = 5.0 if ev.get("end_time") is None else 0.0
        return 100.0 + active_bonus + recency + min(area * 100.0, 8.0)

    @staticmethod
    def _red_light_memory_sec() -> float:
        try:
            return max(3.0, float(os.environ.get("FRIGATE_RED_LIGHT_TRACK_MEMORY_SEC", "15") or 15))
        except (TypeError, ValueError):
            return 15.0

    def _red_light_obs_zone_for_bbox(
        self,
        after: dict[str, Any],
        zone_by_uuid: dict[str, dict[str, Any]],
    ) -> dict[str, Any] | None:
        box = self._vehicle_bbox_norm(after)
        if not box:
            return None
        best: dict[str, Any] | None = None
        for zinfo in zone_by_uuid.values():
            if self._zone_behavior(zinfo) != "red_light_observation":
                continue
            if self._bbox_center_in_zone(box, zinfo):
                best = zinfo
                break
        return best

    def _infer_active_zones_from_bbox(
        self,
        after: dict[str, Any],
        zone_by_uuid: dict[str, dict[str, Any]],
    ) -> set[str]:
        box = self._vehicle_bbox_norm(after)
        if not box:
            return set()
        out: set[str] = set()
        for zuuid, zinfo in zone_by_uuid.items():
            if FrigateEventBridge._bbox_center_in_zone(box, zinfo):
                out.add(f"cv_zone_{zuuid}")
        return out

    def _detect_wh(self, camera: str) -> tuple[float, float]:
        """Frigate detect resolution for a camera (accepts cv_-name or uuid)."""
        key = camera if camera.startswith("cv_") else f"cv_{camera}"
        wh = self._detect_wh_cache.get(key)
        if wh:
            return wh
        try:
            with urllib.request.urlopen(f"{self._frigate_url}/api/config", timeout=8.0) as resp:
                cfg = json.loads(resp.read().decode("utf-8"))
            for name, cam_cfg in (cfg.get("cameras") or {}).items():
                if not isinstance(cam_cfg, dict):
                    continue
                det = cam_cfg.get("detect") if isinstance(cam_cfg.get("detect"), dict) else {}
                try:
                    w = float(det.get("width") or 0)
                    h = float(det.get("height") or 0)
                except (TypeError, ValueError):
                    continue
                if w > 0 and h > 0:
                    self._detect_wh_cache[str(name)] = (w, h)
        except Exception:
            logger.warning("frigate_bridge detect resolution fetch failed for %s", key[:16])
        return self._detect_wh_cache.get(key) or (1920.0, 1080.0)

    def _vehicle_bbox_norm(self, after: dict[str, Any]) -> dict[str, float] | None:
        """Vehicle bbox from an event payload, normalized with the camera's real
        detect resolution. MQTT boxes come as detect-resolution pixels; dividing
        them by a hardcoded 1920x1080 shifts every zone/bbox decision."""
        box = self._vehicle_bbox_from_after(after)
        if not box:
            return None
        try:
            vals = (
                float(box.get("x") or 0), float(box.get("y") or 0),
                float(box.get("width") or 0), float(box.get("height") or 0),
            )
        except (TypeError, ValueError):
            return None
        if box.get("norm") or max(vals) <= 1.5:
            return box
        w, h = self._detect_wh(str(after.get("camera") or ""))
        return {
            "x": vals[0] / w,
            "y": vals[1] / h,
            "width": vals[2] / w,
            "height": vals[3] / h,
            "norm": True,
        }

    @staticmethod
    def _vehicle_bbox_from_after(after: dict[str, Any]) -> dict[str, float] | None:
        data = after.get("data") if isinstance(after.get("data"), dict) else {}
        raw = after.get("box") or data.get("box")
        if isinstance(raw, dict):
            try:
                return {
                    "x": float(raw.get("x") or 0),
                    "y": float(raw.get("y") or 0),
                    "width": float(raw.get("width") or raw.get("w") or 0),
                    "height": float(raw.get("height") or raw.get("h") or 0),
                    "norm": bool(raw.get("norm", True)),
                }
            except (TypeError, ValueError):
                return None
        if isinstance(raw, (list, tuple)) and len(raw) >= 4:
            try:
                vals = [float(raw[i]) for i in range(4)]
            except (TypeError, ValueError):
                return None
            if max(vals) > 1.5 and vals[2] > vals[0] and vals[3] > vals[1]:
                return {
                    "x": vals[0],
                    "y": vals[1],
                    "width": vals[2] - vals[0],
                    "height": vals[3] - vals[1],
                }
            out: dict[str, float] = {
                "x": vals[0],
                "y": vals[1],
                "width": vals[2],
                "height": vals[3],
            }
            if max(vals) <= 1.5:
                out["norm"] = True
            return out
        return None

    @staticmethod
    def _bbox_ts_from_after(after: dict[str, Any], fallback: float) -> float:
        data = after.get("data") if isinstance(after.get("data"), dict) else {}
        snapshot = after.get("snapshot") if isinstance(after.get("snapshot"), dict) else {}
        candidates: list[Any] = [
            after.get("frame_time"),
            data.get("frame_time"),
            snapshot.get("frame_time"),
        ]
        path = data.get("path_data")
        if isinstance(path, list) and path:
            last = path[-1]
            if isinstance(last, (list, tuple)) and len(last) >= 2:
                candidates.append(last[1])
        candidates.extend([after.get("start_time"), data.get("start_time")])
        for raw in candidates:
            try:
                if raw is not None:
                    return float(raw)
            except (TypeError, ValueError):
                continue
        return fallback

    @staticmethod
    def _bbox_center_in_zone(bbox: dict[str, float] | None, zinfo: dict[str, Any]) -> bool:
        if not bbox:
            return False
        pts = FrigateEventBridge._zone_points(zinfo)
        if len(pts) < 3:
            return True
        try:
            x = float(bbox.get("x") or 0)
            y = float(bbox.get("y") or 0)
            w = float(bbox.get("width") or 0)
            h = float(bbox.get("height") or 0)
        except (TypeError, ValueError):
            return False
        if w <= 0 or h <= 0:
            return False
        if not bbox.get("norm") and max(x, y, w, h) > 1.5:
            x = x / 1920.0
            y = y / 1080.0
            w = w / 1920.0
            h = h / 1080.0
        px = x + w / 2.0
        py = y + h / 2.0
        inside = False
        j = len(pts) - 1
        for i, (xi, yi) in enumerate(pts):
            xj, yj = pts[j]
            if ((yi > py) != (yj > py)) and (
                px < (xj - xi) * (py - yi) / ((yj - yi) or 1e-9) + xi
            ):
                inside = not inside
            j = i
        return inside

    @staticmethod
    def _zone_behavior(zinfo: dict[str, Any]) -> str:
        behavior = str(zinfo.get("behavior") or zinfo.get("zone_kind") or "")
        if behavior:
            return behavior
        bcfg = zinfo.get("behavior_config")
        if isinstance(bcfg, dict):
            return str(bcfg.get("behavior") or "")
        return ""

    @staticmethod
    def _zone_points(zinfo: dict[str, Any]) -> list[tuple[float, float]]:
        raw = zinfo.get("polygon") or zinfo.get("points") or zinfo.get("coordinates") or []
        if isinstance(raw, str):
            stripped = raw.strip()
            if stripped.startswith("["):
                try:
                    raw = json.loads(stripped)
                except json.JSONDecodeError:
                    raw = []
            else:
                try:
                    vals = [float(x.strip()) for x in stripped.split(",") if x.strip()]
                except ValueError:
                    vals = []
                raw = list(zip(vals[0::2], vals[1::2]))
        pts: list[tuple[float, float]] = []
        if not isinstance(raw, list):
            return pts
        for p in raw:
            try:
                if isinstance(p, dict):
                    pts.append((float(p.get("x")), float(p.get("y"))))
                elif isinstance(p, (list, tuple)) and len(p) >= 2:
                    pts.append((float(p[0]), float(p[1])))
            except (TypeError, ValueError):
                continue
        return pts

    def _dedupe(self, key: str, ttl: float = 120.0) -> bool:
        """Return True if this key was already seen (should skip)."""
        now = time.time()
        with self._seen_lock:
            expired = [k for k, t in self._seen.items() if now - t > ttl]
            for k in expired:
                del self._seen[k]
            if key in self._seen:
                with self._stats_lock:
                    self._stats["dropped_dedupe"] += 1
                return True
            self._seen[key] = now
        return False

    def _remember_red_light_track(
        self,
        event_id: str,
        after: dict[str, Any],
        obs_zinfo: dict[str, Any],
        zone_by_uuid: dict[str, dict[str, Any]],
    ) -> None:
        if not event_id:
            return
        now = time.time()
        memory_sec = self._red_light_memory_sec()
        with self._seen_lock:
            self._red_light_active[event_id] = (
                now,
                dict(after),
                dict(obs_zinfo),
                {k: dict(v) for k, v in zone_by_uuid.items()},
            )
            expired = [
                eid for eid, (ts, *_rest) in self._red_light_active.items()
                if now - ts > memory_sec
            ]
            for eid in expired:
                self._red_light_active.pop(eid, None)
            if expired:
                with self._stats_lock:
                    self._stats["red_light_memory_expired"] = int(
                        self._stats.get("red_light_memory_expired") or 0
                    ) + len(expired)

    def _retry_cached_red_light_tracks(self, *, skip_event_id: str = "", camera_id: str = "") -> None:
        if not self._vlm_enabled:
            return
        now = time.time()
        memory_sec = self._red_light_memory_sec()
        with self._seen_lock:
            items = list(self._red_light_active.items())
        scored: list[tuple[float, str, float, dict[str, Any], dict[str, Any], dict[str, dict[str, Any]]]] = []
        for event_id, (ts, after, obs_zinfo, zone_by_uuid) in items:
            if event_id == skip_event_id:
                continue
            if now - ts > memory_sec:
                with self._seen_lock:
                    self._red_light_active.pop(event_id, None)
                with self._stats_lock:
                    self._stats["red_light_memory_expired"] = int(
                        self._stats.get("red_light_memory_expired") or 0
                    ) + 1
                continue
            ev_camera_id = parse_camera_uuid(str(after.get("camera") or ""))
            if not ev_camera_id:
                continue
            if camera_id and ev_camera_id != camera_id:
                continue
            score = self._red_light_event_score(after, zone_by_uuid=zone_by_uuid, now=now)
            if score <= 0:
                continue
            scored.append((score, event_id, ts, after, obs_zinfo, zone_by_uuid))
        sorted_scored = sorted(scored, key=lambda item: item[0], reverse=True)
        candidate_events = [
            payload for payload in (
                self._red_light_candidate_payload(
                    cand_event_id,
                    cand_after,
                    cand_obs_zinfo,
                    score=cand_score,
                    now=now,
                )
                for cand_score, cand_event_id, _cand_ts, cand_after, cand_obs_zinfo, _cand_zone_by_uuid in sorted_scored[:6]
            )
            if payload is not None
        ]
        for _score, event_id, _ts, after, obs_zinfo, zone_by_uuid in sorted_scored[:3]:
            ev_camera_id = parse_camera_uuid(str(after.get("camera") or ""))
            if not ev_camera_id:
                continue
            try:
                gate = "unknown"
                if self._light_debug is not None:
                    dbg = dict(self._light_debug(ev_camera_id) or {})
                    gate = str(dbg.get("gate") or gate).lower().strip()
                elif self._light_state is not None:
                    gate = str(self._light_state(ev_camera_id) or gate).lower().strip()
                if gate != "red":
                    continue
                with self._stats_lock:
                    self._stats["red_light_cached_retries"] = int(
                        self._stats.get("red_light_cached_retries") or 0
                    ) + 1
                    self._stats["red_light_memory_enqueued"] = int(
                        self._stats.get("red_light_memory_enqueued") or 0
                    ) + 1
                self._maybe_red_light(
                    ev_camera_id,
                    event_id,
                    after,
                    obs_zinfo,
                    zone_by_uuid,
                    candidate_events=candidate_events,
                )
            except Exception:
                logger.exception("frigate_bridge cached red_light retry failed event=%s", event_id[:12])

    def _red_light_candidate_payload(
        self,
        event_id: str,
        after: dict[str, Any],
        obs_zinfo: dict[str, Any],
        *,
        score: float | None,
        now: float,
    ) -> dict[str, Any] | None:
        box = self._vehicle_bbox_norm(after)
        if not event_id or not box:
            return None
        data = after.get("data") if isinstance(after.get("data"), dict) else {}
        return {
            "id": event_id,
            "bbox": box,
            "bbox_ts": self._bbox_ts_from_after(after, now),
            "start_time": after.get("start_time") or data.get("start_time"),
            "end_time": after.get("end_time") or data.get("end_time"),
            "frame_time": after.get("frame_time") or data.get("frame_time"),
            "score": round(float(score), 3) if isinstance(score, (int, float)) else None,
            "label": after.get("label"),
            "zone_id": obs_zinfo.get("zone_id") or obs_zinfo.get("name"),
        }

    def _red_light_candidate_events(
        self,
        camera_id: str,
        primary_event_id: str,
        *,
        limit: int = 6,
    ) -> list[dict[str, Any]]:
        now = time.time()
        memory_sec = self._red_light_memory_sec()
        with self._seen_lock:
            items = list(self._red_light_active.items())
        scored: list[tuple[bool, float, dict[str, Any]]] = []
        seen: set[str] = set()
        for event_id, (ts, after, obs_zinfo, zone_by_uuid) in items:
            if event_id in seen or now - ts > memory_sec:
                continue
            ev_camera_id = parse_camera_uuid(str(after.get("camera") or ""))
            if ev_camera_id != camera_id:
                continue
            score = self._red_light_event_score(after, zone_by_uuid=zone_by_uuid, now=now)
            if score <= 0:
                continue
            payload = self._red_light_candidate_payload(
                event_id,
                after,
                obs_zinfo,
                score=score,
                now=now,
            )
            if payload is None:
                continue
            seen.add(event_id)
            scored.append((event_id == primary_event_id, score, payload))
        scored.sort(key=lambda item: (not item[0], -item[1]))
        return [payload for _primary, _score, payload in scored[:max(1, limit)]]

    def _zone_conf(self, zinfo: dict[str, Any]) -> float:
        cfg = zinfo.get("behavior_config") or {}
        if not isinstance(cfg, dict):
            return 0.45
        try:
            return float(cfg.get("confidence", 0.45))
        except (TypeError, ValueError):
            return 0.45

    def _speed_limit(self, zinfo: dict[str, Any]) -> float:
        cfg = zinfo.get("behavior_config") or {}
        if not isinstance(cfg, dict):
            return 0.0
        try:
            return float(cfg.get("speed_limit_kmh", 0) or 0)
        except (TypeError, ValueError):
            return 0.0

    def _track_labels_for_zone(self, zinfo: dict[str, Any]) -> frozenset[str] | None:
        """Optional zone behavior_config.track_objects; None = default vehicle set."""
        cfg = zinfo.get("behavior_config") or {}
        if not isinstance(cfg, dict):
            return None
        raw = cfg.get("track_objects")
        if raw is None:
            return None
        labels: set[str] = set()
        items: list[Any]
        if isinstance(raw, str):
            items = [p.strip() for p in raw.split(",") if p.strip()]
        elif isinstance(raw, (list, tuple)):
            items = list(raw)
        else:
            return None
        for item in items:
            lab = str(item or "").strip().lower()
            if not lab:
                continue
            if lab == "motorbike":
                lab = "motorcycle"
            labels.add(lab)
        return frozenset(labels) if labels else None

    def _label_allowed(self, label: str, zinfo: dict[str, Any], *, allow_person_default: bool = False) -> bool:
        lab = (label or "").strip().lower()
        allowed = self._track_labels_for_zone(zinfo)
        if allowed is not None:
            if lab == "motorbike" and "motorcycle" in allowed:
                return True
            return lab in allowed
        if lab in _VEHICLE_LABELS:
            return True
        return bool(allow_person_default and lab == "person")

    def _maybe_cabin(
        self,
        camera_id: str,
        event_id: str,
        after: dict[str, Any],
        zinfo: dict[str, Any],
        behavior: str,
    ) -> None:
        rules = _BEHAVIOR_TO_RULES.get(behavior) or []
        if not rules:
            return
        # No size gate: every tracked vehicle in the zone is cropped and sent
        # to Gemini (zone + allowed label + per-event dedupe are the only gates).
        jpeg, box, _ev = fetch_cabin_jpeg(
            self._frigate_url,
            event_id,
            after,
            wait_sec=self._snapshot_wait,
            label=str(after.get("label") or ""),
        )
        if not jpeg:
            with self._stats_lock:
                if box is not None:
                    self._stats["cabin_skipped_too_small"] = int(
                        self._stats.get("cabin_skipped_too_small") or 0
                    ) + 1
                else:
                    self._stats["snapshot_fail"] += 1
                    self._stats["cabin_snapshot_fail"] = int(
                        self._stats.get("cabin_snapshot_fail") or 0
                    ) + 1
            logger.info(
                "frigate_bridge cabin_skip camera=%s event=%s box=%s",
                camera_id[:8], event_id[:12], bool(box),
            )
            return
        from citevision_ai.vlm.queue import VlmJob

        meta_crop_mode = "frigate_vehicle_bbox"
        zone_name = str(zinfo.get("zone_id") or zinfo.get("name") or "")
        try:
            dedupe_ttl = float(os.environ.get("FRIGATE_CABIN_DEDUPE_SEC", "60") or 60)
        except (TypeError, ValueError):
            dedupe_ttl = 60.0

        # Enqueue ALL rules for the zone (driver_cabin → seatbelt AND phone).
        # Dedupe only per Frigate event+rule (A.8): never pace whole camera so
        # successive vehicles keep producing alerts while the rule stays enabled.
        for rule in rules:
            dedupe_key = f"cabin:{event_id}:{rule}"
            if self._dedupe(dedupe_key, ttl=max(1.0, dedupe_ttl)):
                continue
            skeleton = {
                "event_id": str(uuid.uuid4()),
                "camera_id": camera_id,
                "event_type": rule,
                "event": rule,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "zone_id": zone_name,
                "track_id": event_id,
                "frigate_event_id": event_id,
                "bbox": box,
                "severity": "medium",
                "metadata": {
                    "detection_method": "gemini_vlm",
                    "bridge_source": "frigate",
                    "frigate_event_id": event_id,
                    "track_id": event_id,
                    "frigate_label": after.get("label"),
                    "zone_behavior": behavior,
                    "crop_mode": meta_crop_mode,
                    "vlm_prompt_rule": rule,
                },
            }
            ok = self._vlm_queue.try_enqueue(
                VlmJob(
                    jpeg=jpeg,
                    rule=rule,
                    min_confidence=self._zone_conf(zinfo),
                    event_skeleton=skeleton,
                    extra_context=f"frigate_event={event_id} zone={zone_name}",
                )
            )
            if ok:
                with self._stats_lock:
                    self._stats["cabin_enqueued"] += 1
                logger.info(
                    "frigate_bridge cabin_enqueued camera=%s event=%s rule=%s",
                    camera_id[:8], event_id[:12], rule,
                )

    def _maybe_red_light(
        self,
        camera_id: str,
        event_id: str,
        after: dict[str, Any],
        obs_zinfo: dict[str, Any],
        zone_by_uuid: dict[str, dict[str, Any]],
        *,
        candidate_events: list[dict[str, Any]] | None = None,
    ) -> None:
        rule = "red_light_violation"
        # Gate: only ask Gemini while local HSV gate says red (D1 mode + D2 grace).
        light_state = "unknown"
        gate_dbg: dict[str, Any] = {}
        if self._light_debug is not None:
            try:
                gate_dbg = dict(self._light_debug(camera_id) or {})
            except Exception:
                logger.exception("frigate_bridge light_debug_resolver failed")
                gate_dbg = {}
        if self._light_state is not None:
            try:
                light_state = str(self._light_state(camera_id) or "unknown").lower().strip()
            except Exception:
                logger.exception("frigate_bridge light_state_resolver failed")
                light_state = "unknown"
        if gate_dbg.get("gate"):
            light_state = str(gate_dbg.get("gate") or light_state).lower().strip()
        raw_s = str(gate_dbg.get("raw") or "?")
        stable_s = str(gate_dbg.get("stable") or "?")
        gate_mode = str(gate_dbg.get("gate_mode") or os.environ.get("RED_LIGHT_GATE_MODE") or "or")
        grace_active = bool(gate_dbg.get("grace_active"))
        force_enqueue = str(os.environ.get("RED_LIGHT_DEBUG_FORCE_ENQUEUE", "")).strip().lower() in (
            "1", "true", "yes",
        )
        from citevision_ai.road_enforcement.red_light_vote import red_light_vote_mode

        lf_or_g = red_light_vote_mode() == "lf_or_g"
        light_poly: list[Any] = []
        for z in zone_by_uuid.values():
            if str(z.get("behavior") or "") == "traffic_light_color":
                poly = z.get("polygon") or z.get("points") or []
                if isinstance(poly, list):
                    light_poly = poly
                break
        vehicle_box_early = self._vehicle_bbox_norm(after)
        if vehicle_box_early is not None and not self._bbox_center_in_zone(vehicle_box_early, obs_zinfo):
            with self._stats_lock:
                self._stats["red_light_skipped_bbox_outside_zone"] = int(
                    self._stats.get("red_light_skipped_bbox_outside_zone") or 0
                ) + 1
            logger.info(
                "frigate_bridge red_light skip bbox_outside_zone camera=%s event=%s bbox=%s zone=%s",
                camera_id[:8], event_id[:12], vehicle_box_early,
                str(obs_zinfo.get("zone_id") or obs_zinfo.get("name") or ""),
            )
            return
        if self._dedupe(f"red:{event_id}:{rule}", ttl=8.0):
            return
        wait_snapshot_ready(
            self._frigate_url, event_id, timeout_sec=min(12.0, float(self._snapshot_wait)),
        )
        raw_snap = download_snapshot_jpeg(self._frigate_url, event_id)
        if not raw_snap:
            with self._stats_lock:
                self._stats["snapshot_fail"] += 1
                self._stats["red_light_snapshot_fail"] = int(
                    self._stats.get("red_light_snapshot_fail") or 0
                ) + 1
            logger.info(
                "frigate_bridge snapshot_fail red_light camera=%s event=%s",
                camera_id[:8], event_id[:12],
            )
            return
        frigate_light = classify_snapshot_light_state(raw_snap, light_poly)
        snapshot_red = frigate_light == "red"
        emit_gate_red = force_enqueue or light_state == "red" or (lf_or_g and snapshot_red)
        raw_red = raw_s.lower().strip() == "red"
        stable_red = stable_s.lower().strip() == "red"
        if force_enqueue:
            logger.warning(
                "frigate_bridge red_light DEBUG force enqueue camera=%s event=%s "
                "raw=%s stable=%s gate=%s",
                camera_id[:8], event_id[:12], raw_s, stable_s, light_state,
            )
        elif light_state == "unknown" and not (lf_or_g and snapshot_red):
            with self._stats_lock:
                self._stats["red_light_skipped_unknown"] = int(
                    self._stats.get("red_light_skipped_unknown") or 0
                ) + 1
            logger.info(
                "frigate_bridge red_light skip unknown camera=%s event=%s "
                "raw=%s stable=%s gate=%s gate_mode=%s",
                camera_id[:8], event_id[:12], raw_s, stable_s, light_state, gate_mode,
            )
            return
        if not emit_gate_red:
            with self._stats_lock:
                self._stats["red_light_skipped_not_red"] = int(
                    self._stats.get("red_light_skipped_not_red") or 0
                ) + 1
            logger.info(
                "frigate_bridge red_light skip not_red camera=%s event=%s "
                "raw=%s stable=%s gate=%s gate_mode=%s frigate_snapshot=%s",
                camera_id[:8], event_id[:12], raw_s, stable_s, light_state, gate_mode, frigate_light,
            )
            return
        if not force_enqueue and not raw_red and not (lf_or_g and snapshot_red):
            with self._stats_lock:
                self._stats["red_light_skipped_not_raw_red"] = int(
                    self._stats.get("red_light_skipped_not_raw_red") or 0
                ) + 1
            logger.info(
                "frigate_bridge red_light skip not_raw_red camera=%s event=%s "
                "raw=%s stable=%s gate=%s gate_mode=%s grace=%s",
                camera_id[:8], event_id[:12], raw_s, stable_s, light_state, gate_mode, grace_active,
            )
            return
        if not force_enqueue and not stable_red and not (lf_or_g and snapshot_red):
            with self._stats_lock:
                self._stats["red_light_skipped_stable_not_red"] = int(
                    self._stats.get("red_light_skipped_stable_not_red") or 0
                ) + 1
            logger.info(
                "frigate_bridge red_light skip stable_not_red camera=%s event=%s "
                "raw=%s stable=%s gate=%s",
                camera_id[:8], event_id[:12], raw_s, stable_s, light_state,
            )
            return
        if grace_active:
            with self._stats_lock:
                self._stats["red_light_gate_grace"] = int(
                    self._stats.get("red_light_gate_grace") or 0
                ) + 1
        if not force_enqueue and not snapshot_red:
            with self._stats_lock:
                self._stats["red_light_skipped_frigate_snapshot_not_red"] = int(
                    self._stats.get("red_light_skipped_frigate_snapshot_not_red") or 0
                ) + 1
            logger.info(
                "frigate_bridge red_light skip frigate_snapshot_not_red camera=%s event=%s "
                "ia_gate=%s frigate_snapshot=%s",
                camera_id[:8], event_id[:12], light_state, frigate_light,
            )
            return
        from citevision_ai.road_enforcement.red_light_vote import (
            local_already_emitted,
            red_light_vote_mode,
        )

        zone_name = str(obs_zinfo.get("zone_id") or obs_zinfo.get("name") or "")
        violation_ts = time.time()
        bbox_ts = self._bbox_ts_from_after(after, violation_ts)
        violation_dt = datetime.fromtimestamp(violation_ts, tz=timezone.utc).isoformat()
        after_data = after.get("data") if isinstance(after.get("data"), dict) else {}
        frigate_frame_time = after.get("frame_time") or after_data.get("frame_time")
        frigate_start_time = after.get("start_time") or after_data.get("start_time")
        vehicle_box = self._vehicle_bbox_norm(after)
        if not vehicle_box:
            logger.info(
                "frigate_bridge red_light skip no_bbox camera=%s event=%s",
                camera_id[:8], event_id[:12],
            )
            return
        if not self._bbox_center_in_zone(vehicle_box, obs_zinfo):
            with self._stats_lock:
                self._stats["red_light_skipped_bbox_outside_zone"] = int(
                    self._stats.get("red_light_skipped_bbox_outside_zone") or 0
                ) + 1
            logger.info(
                "frigate_bridge red_light skip bbox_outside_zone camera=%s event=%s bbox=%s zone=%s",
                camera_id[:8], event_id[:12], vehicle_box, zone_name,
            )
            return
        candidate_events = candidate_events or self._red_light_candidate_events(camera_id, event_id)
        skeleton = {
            "event_id": str(uuid.uuid4()),
            "camera_id": camera_id,
            "event_type": rule,
            "event": rule,
            "timestamp": violation_dt,
            "bbox_ts": bbox_ts,
            "zone_id": zone_name,
            "track_id": event_id,
            "frigate_event_id": event_id,
            "bbox": vehicle_box,
            "severity": "high",
            "metadata": {
                "detection_method": "gemini_vlm",
                "bridge_source": "frigate",
                "frigate_event_id": event_id,
                "track_id": event_id,
                "frigate_label": after.get("label"),
                "zone_behavior": "red_light_observation",
                "hsv_light_state": light_state,
                "frigate_snapshot_light_state": frigate_light,
                "hsv_raw": raw_s,
                "hsv_stable": stable_s,
                "light_zone_polygon": light_poly,
                "gate_mode": gate_mode,
                "grace_active": grace_active,
                "hsv_gate_ts": bbox_ts,
                "violation_instant_ts": bbox_ts,
                "frigate_frame_time": frigate_frame_time,
                "frigate_start_time": frigate_start_time,
                "red_light_context_bbox": vehicle_box,
                "frigate_candidate_events": candidate_events,
                "debug_forced": force_enqueue,
            },
        }
        self._maybe_emit_lf_or_g_local(
            skeleton=skeleton,
            camera_id=camera_id,
            event_id=event_id,
            light_state=light_state,
            force_enqueue=force_enqueue,
            hsv_gate_red=emit_gate_red,
        )
        if red_light_vote_mode() == "lf_or_g" and local_already_emitted(event_id):
            return
        jpeg, box, _ev = fetch_red_light_jpeg(
            self._frigate_url,
            event_id,
            after,
            light_polygon=light_poly,
            wait_sec=self._snapshot_wait,
        )
        if not jpeg:
            with self._stats_lock:
                self._stats["snapshot_fail"] += 1
                self._stats["red_light_snapshot_fail"] = int(
                    self._stats.get("red_light_snapshot_fail") or 0
                ) + 1
            logger.info(
                "frigate_bridge snapshot_fail red_light camera=%s event=%s",
                camera_id[:8], event_id[:12],
            )
            return
        from citevision_ai.vlm.queue import VlmJob

        vehicle_box = self._vehicle_bbox_norm(after) or box
        if not self._bbox_center_in_zone(vehicle_box, obs_zinfo):
            with self._stats_lock:
                self._stats["red_light_skipped_bbox_outside_zone"] = int(
                    self._stats.get("red_light_skipped_bbox_outside_zone") or 0
                ) + 1
            logger.info(
                "frigate_bridge red_light skip bbox_outside_zone camera=%s event=%s bbox=%s zone=%s",
                camera_id[:8], event_id[:12], vehicle_box, zone_name,
            )
            return
        meta = dict(skeleton.get("metadata") or {})
        meta["red_light_context_bbox"] = box
        skeleton["metadata"] = meta
        skeleton["bbox"] = vehicle_box
        ok = self._vlm_queue.try_enqueue(
            VlmJob(
                jpeg=jpeg,
                rule=rule,
                min_confidence=self._zone_conf(obs_zinfo),
                event_skeleton=skeleton,
                extra_context=(
                    f"frigate_event={event_id} observation_zone={zone_name} "
                    f"hsv_gate=red raw={raw_s} stable={stable_s} gate_mode={gate_mode} "
                    f"grace={grace_active} bbox_ts={bbox_ts}; confirm only if the "
                    "Frigate-bbox vehicle itself is the red-light violator; reject if "
                    "the bbox is empty or another vehicle elsewhere is violating"
                ),
                shadow_only=force_enqueue,
            )
        )
        if ok:
            with self._stats_lock:
                self._stats["red_light_enqueued"] += 1
            logger.info(
                "frigate_bridge red_light enqueue camera=%s event=%s "
                "raw=%s stable=%s gate_mode=%s grace=%s",
                camera_id[:8], event_id[:12], raw_s, stable_s, gate_mode, grace_active,
            )

    def _maybe_emit_lf_or_g_local(
        self,
        *,
        skeleton: dict[str, Any],
        camera_id: str,
        event_id: str,
        light_state: str,
        force_enqueue: bool,
        hsv_gate_red: bool,
    ) -> None:
        from citevision_ai.road_enforcement.red_light_vote import local_frigate_would_emit, red_light_vote_mode

        if not local_frigate_would_emit(hsv_gate_red=hsv_gate_red, frigate_in_obs_zone=True):
            return
        if self._dedupe(f"lf_emit:{event_id}", ttl=30.0):
            return
        with self._stats_lock:
            self._stats["lf_or_g_would_emit"] = int(self._stats.get("lf_or_g_would_emit") or 0) + 1
        shadow_env = str(os.environ.get("GEMINI_SHADOW_MODE", "")).strip().lower() in (
            "1", "true", "yes",
        )
        vote_shadow = str(os.environ.get("RED_LIGHT_VOTE_SHADOW", "")).strip().lower() in (
            "1", "true", "yes",
        )
        if shadow_env or vote_shadow:
            with self._stats_lock:
                self._stats["lf_or_g_shadow"] = int(self._stats.get("lf_or_g_shadow") or 0) + 1
            logger.info(
                "frigate_bridge lf_or_g shadow camera=%s event=%s vote=%s (no local emit)",
                camera_id[:8], event_id[:12], red_light_vote_mode(),
            )
            try:
                from citevision_ai.observability.rule_blockers import blockers
                blockers.note(
                    "lf_or_g_shadow",
                    rule="red_light_violation",
                    camera_id=camera_id,
                    frigate_event_id=event_id,
                    vote_mode=red_light_vote_mode(),
                )
            except Exception:
                pass
            return
        if self._emit is None:
            return
        local_evt = dict(skeleton)
        meta = dict(local_evt.get("metadata") or {})
        meta.update(
            {
                "detection_method": "hsv_local_frigate",
                "vote_mode": red_light_vote_mode(),
                "bbox_source": "frigate_mqtt",
            }
        )
        local_evt["metadata"] = meta
        local_evt["confidence"] = 0.85
        try:
            self._emit(local_evt)
            from citevision_ai.road_enforcement.red_light_vote import mark_local_emitted
            mark_local_emitted(event_id)
            with self._stats_lock:
                self._stats["lf_or_g_emitted"] = int(self._stats.get("lf_or_g_emitted") or 0) + 1
            self._dedupe(f"gemini_skip:{event_id}", ttl=60.0)
            logger.info(
                "frigate_bridge lf_or_g emit camera=%s event=%s",
                camera_id[:8], event_id[:12],
            )
            try:
                from citevision_ai.observability.rule_blockers import blockers
                blockers.note(
                    "lf_or_g_emit",
                    rule="red_light_violation",
                    camera_id=camera_id,
                    frigate_event_id=event_id,
                )
            except Exception:
                pass
        except Exception:
            logger.exception("frigate_bridge lf_or_g emit failed camera=%s", camera_id[:8])

    def _watchlist_entries(self) -> list[dict[str, Any]]:
        if not self._watchlist_resolver:
            return []
        try:
            entries = self._watchlist_resolver() or []
        except Exception:
            logger.exception("frigate_bridge watchlist_resolver failed")
            return []
        return list(entries) if isinstance(entries, list) else []

    def _maybe_face(
        self,
        camera_id: str,
        event_id: str,
        after: dict[str, Any],
        zinfo: dict[str, Any],
    ) -> None:
        """Frigate person crop → Gemini clear-face gate → InsightFace on crop.

        Production watchlist match is InsightFace embeddings only (not Gemini text).
        """
        if self._dedupe(f"face:{event_id}"):
            return
        jpeg, box, _ev = fetch_subject_jpeg(
            self._frigate_url, event_id, after, wait_sec=self._snapshot_wait,
        )
        if not jpeg:
            with self._stats_lock:
                self._stats["snapshot_fail"] += 1
            return
        from citevision_ai.vlm.queue import VlmJob

        zone_name = str(zinfo.get("zone_id") or zinfo.get("name") or "")
        base_meta = {
            "detection_method": "gemini_clear_face_gate",
            "bridge_source": "frigate",
            "frigate_event_id": event_id,
            "face_pipeline": "frigate_crop_gate_insightface",
        }
        # Persist audit dump root for face (YES and NO).
        dump_dir = str(os.environ.get("VLM_FACE_DUMP_DIR") or "").strip()
        if dump_dir:
            try:
                from pathlib import Path
                Path(dump_dir).mkdir(parents=True, exist_ok=True)
                stamp = time.strftime("%H%M%S")
                (Path(dump_dir) / f"{stamp}_{event_id[:12]}_crop.jpg").write_bytes(jpeg)
            except OSError:
                pass

        # Prefer InsightFace on the Frigate crop when available (biometric truth).
        if self._face_match_jpeg is not None:
            try:
                matches = self._face_match_jpeg(jpeg) or []
            except Exception:
                logger.exception("face_match_jpeg failed")
                matches = []
            for m in matches:
                et = str(m.get("event_type") or "")
                if et not in ("face_detected", "face_unknown", "face_watchlist_match"):
                    continue
                if self._dedupe(f"face:{event_id}:{et}", ttl=90.0):
                    continue
                evt = {
                    "event_id": str(uuid.uuid4()),
                    "camera_id": camera_id,
                    "event_type": et,
                    "event": et,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "zone_id": zone_name,
                    "frigate_event_id": event_id,
                    "bbox": box,
                    "severity": "critical" if et == "face_watchlist_match" else (
                        "warning" if et == "face_unknown" else "info"
                    ),
                    "metadata": {
                        **base_meta,
                        **(m.get("metadata") or {}),
                        "detection_method": "insightface_on_frigate_crop",
                    },
                }
                if self._emit:
                    try:
                        self._emit(evt)
                        with self._stats_lock:
                            self._stats["face_enqueued"] += 1
                    except Exception:
                        logger.exception("face emit failed")
            # Still enqueue Gemini gate for audit / face_detected when no IF faces.
            if matches:
                return

        ok_det = self._vlm_queue.try_enqueue(
            VlmJob(
                jpeg=jpeg,
                rule="face_detected",
                min_confidence=0.4,
                event_skeleton={
                    "event_id": str(uuid.uuid4()),
                    "camera_id": camera_id,
                    "event_type": "face_detected",
                    "event": "face_detected",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "zone_id": zone_name,
                    "frigate_event_id": event_id,
                    "bbox": box,
                    "severity": "info",
                    "metadata": dict(base_meta),
                },
            )
        )
        if ok_det:
            with self._stats_lock:
                self._stats["face_enqueued"] += 1

    def _maybe_plate(
        self,
        camera_id: str,
        event_id: str,
        after: dict[str, Any],
        zinfo: dict[str, Any],
    ) -> None:
        rule = "plate_ocr"
        if self._dedupe(f"plate:{event_id}"):
            return
        jpeg, box, _ev = fetch_subject_jpeg(
            self._frigate_url, event_id, after, wait_sec=self._snapshot_wait,
        )
        if not jpeg:
            with self._stats_lock:
                self._stats["snapshot_fail"] += 1
            return
        from citevision_ai.identity.plate_fusion import run_paddle_on_jpeg
        from citevision_ai.vlm.queue import VlmJob

        paddle_reading = run_paddle_on_jpeg(jpeg)
        zone_name = str(zinfo.get("zone_id") or zinfo.get("name") or "")
        skeleton = {
            "event_id": str(uuid.uuid4()),
            "camera_id": camera_id,
            "event_type": "plate_detected",
            "event": "plate_detected",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "zone_id": zone_name,
            "frigate_event_id": event_id,
            "bbox": box,
            "severity": "info",
            "metadata": {
                "detection_method": "gemini_paddle_fusion",
                "bridge_source": "frigate",
                "frigate_event_id": event_id,
            },
        }
        ok = self._vlm_queue.try_enqueue(
            VlmJob(
                jpeg=jpeg,
                rule=rule,
                min_confidence=0.35,
                event_skeleton=skeleton,
                paddle_plate_text=paddle_reading.text if paddle_reading else "",
                paddle_plate_confidence=float(paddle_reading.confidence) if paddle_reading else 0.0,
            )
        )
        if ok:
            with self._stats_lock:
                self._stats["plate_enqueued"] += 1

    def _behavior_cfg(self, zinfo: dict[str, Any]) -> dict[str, Any]:
        bcfg = zinfo.get("behavior_config")
        if isinstance(bcfg, dict):
            cfg = bcfg.get("config")
            if isinstance(cfg, dict):
                return cfg
            return bcfg
        return {}

    def _duration_sec(self, zinfo: dict[str, Any], default: float = 5.0) -> float:
        cfg = self._behavior_cfg(zinfo)
        try:
            return max(1.0, float(cfg.get("duration_seconds") or default))
        except (TypeError, ValueError):
            return default

    def _geom_box(self, after: dict[str, Any]) -> dict[str, Any] | None:
        data = after.get("data") if isinstance(after.get("data"), dict) else {}
        data_box = data.get("box") if isinstance(data, dict) else None
        if isinstance(data_box, (list, tuple)) and len(data_box) >= 4:
            return {
                "x": float(data_box[0]),
                "y": float(data_box[1]),
                "width": float(data_box[2]),
                "height": float(data_box[3]),
                "norm": True,
            }
        return None

    def _emit_geometry(
        self,
        *,
        camera_id: str,
        event_id: str,
        after: dict[str, Any],
        zinfo: dict[str, Any],
        event_type: str,
        severity: str = "medium",
        extra_meta: dict[str, Any] | None = None,
    ) -> None:
        if self._emit is None:
            return
        zone_name = str(zinfo.get("zone_id") or zinfo.get("name") or "")
        meta = {
            "detection_method": "frigate_geometry",
            "bridge_source": "frigate",
            "frigate_event_id": event_id,
            "frigate_label": after.get("label"),
            "bbox_source": "frigate",
            "zone_behavior": str(zinfo.get("behavior") or ""),
        }
        if extra_meta:
            meta.update(extra_meta)
        evt = {
            "event_id": str(uuid.uuid4()),
            "camera_id": camera_id,
            "event_type": event_type,
            "event": event_type,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "zone_id": zone_name,
            "frigate_event_id": event_id,
            "bbox": self._geom_box(after),
            "severity": severity,
            "metadata": meta,
        }
        try:
            self._emit(evt)
            with self._stats_lock:
                self._stats["geometry_emitted"] = int(self._stats.get("geometry_emitted") or 0) + 1
        except Exception:
            logger.exception("geometry emit failed type=%s", event_type)

    def _maybe_geometry_active(
        self,
        camera_id: str,
        event_id: str,
        after: dict[str, Any],
        zinfo: dict[str, Any],
        behavior: str,
        label: str,
    ) -> None:
        zone_key = str(zinfo.get("id") or zinfo.get("zone_id") or "")
        self._zone_last_seen[f"{camera_id}:{zone_key}"] = time.monotonic()
        tracks = self._zone_track_counts.setdefault(f"{camera_id}:{zone_key}", set())
        tracks.add(event_id)

        # Enter emits
        entered = set(self._zone_list(after.get("entered_zones")))
        fz_ids = {f"cv_zone_{zone_key}", zone_key}
        just_entered = bool(entered & fz_ids) or bool(
            entered and any(zone_key in str(x) for x in entered)
        )
        if just_entered or behavior == "perimeter":
            if behavior == "perimeter":
                if not self._dedupe(f"geom:{event_id}:perimeter_breach:{zone_key}", ttl=60.0):
                    self._emit_geometry(
                        camera_id=camera_id, event_id=event_id, after=after, zinfo=zinfo,
                        event_type="perimeter_breach", severity="critical",
                    )
            elif just_entered:
                if not self._dedupe(f"geom:{event_id}:zone_enter:{zone_key}", ttl=60.0):
                    self._emit_geometry(
                        camera_id=camera_id, event_id=event_id, after=after, zinfo=zinfo,
                        event_type="zone_enter", severity="medium",
                    )
                if label in _PERSON_LABELS and str(
                    (self._behavior_cfg(zinfo).get("class_filter") or "person")
                ).lower() in ("person", "any", "*"):
                    # pedestrian in vehicle zone when behavior empty + class vehicle expected elsewhere
                    pass

        # Dwell / loitering / parking / presence
        dwell_map = dict(_DWELL_BEHAVIOR_EVENTS)
        if behavior == "loitering":
            dwell_map["loitering"] = ("loitering", "person")
        if behavior in dwell_map:
            event_type, kind = dwell_map[behavior]
            if kind == "person" and label not in _PERSON_LABELS:
                return
            if kind == "vehicle" and label not in _VEHICLE_LABELS_GEOM:
                return
            dur = self._duration_sec(zinfo, 30.0 if behavior == "loitering" else 5.0)
            if behavior == "parking":
                dur = self._duration_sec(zinfo, 120.0)
                event_type = "vehicle_stopped"
            dkey = f"{event_id}:{zone_key}:{event_type}"
            now = time.monotonic()
            first = self._dwell_since.get(dkey)
            if first is None:
                self._dwell_since[dkey] = now
                return
            if now - first < dur:
                return
            if self._dedupe(f"geom:{dkey}", ttl=max(60.0, dur)):
                return
            sev = "high" if event_type == "loitering" else "medium"
            self._emit_geometry(
                camera_id=camera_id, event_id=event_id, after=after, zinfo=zinfo,
                event_type=event_type, severity=sev,
                extra_meta={"dwell_sec": round(now - first, 1), "duration_threshold_sec": dur},
            )
            with self._stats_lock:
                self._stats["dwell_emitted"] = int(self._stats.get("dwell_emitted") or 0) + 1
            # Also emit dwell_time_exceeded / person_stopped aliases when relevant
            if event_type == "zone_presence" and not self._dedupe(
                f"geom:{event_id}:dwell_time_exceeded:{zone_key}", ttl=max(60.0, dur)
            ):
                self._emit_geometry(
                    camera_id=camera_id, event_id=event_id, after=after, zinfo=zinfo,
                    event_type="dwell_time_exceeded", severity="medium",
                    extra_meta={"dwell_sec": round(now - first, 1)},
                )
            if event_type in ("zone_presence", "loitering") and label in _PERSON_LABELS:
                if not self._dedupe(f"geom:{event_id}:person_stopped:{zone_key}", ttl=max(60.0, dur)):
                    self._emit_geometry(
                        camera_id=camera_id, event_id=event_id, after=after, zinfo=zinfo,
                        event_type="person_stopped", severity="medium",
                        extra_meta={"dwell_sec": round(now - first, 1)},
                    )

    def _maybe_geometry_exit(
        self,
        camera_id: str,
        event_id: str,
        after: dict[str, Any],
        zinfo: dict[str, Any],
        behavior: str,
        label: str,
    ) -> None:
        zone_key = str(zinfo.get("id") or zinfo.get("zone_id") or "")
        if behavior == "controlled_exit":
            if not self._dedupe(f"geom:{event_id}:unauthorized_exit:{zone_key}", ttl=60.0):
                self._emit_geometry(
                    camera_id=camera_id, event_id=event_id, after=after, zinfo=zinfo,
                    event_type="unauthorized_exit", severity="high",
                )
        if not self._dedupe(f"geom:{event_id}:zone_exit:{zone_key}", ttl=60.0):
            self._emit_geometry(
                camera_id=camera_id, event_id=event_id, after=after, zinfo=zinfo,
                event_type="zone_exit", severity="info",
            )

    def _maybe_zone_absence(self, camera_id: str, zone_by_uuid: dict[str, dict[str, Any]]) -> None:
        now = time.monotonic()
        for zuuid, zinfo in zone_by_uuid.items():
            behavior = str(zinfo.get("behavior") or "")
            if behavior not in ("presence", ""):
                continue
            key = f"{camera_id}:{zuuid}"
            last = self._zone_last_seen.get(key)
            if last is None:
                self._zone_last_seen[key] = now
                continue
            dur = self._duration_sec(zinfo, 60.0)
            if now - last < dur:
                continue
            if self._dedupe(f"geom:absence:{camera_id}:{zuuid}", ttl=max(120.0, dur)):
                continue
            # Synthetic absence event (no frigate track)
            if self._emit is None:
                continue
            try:
                self._emit({
                    "event_id": str(uuid.uuid4()),
                    "camera_id": camera_id,
                    "event_type": "zone_absence",
                    "event": "zone_absence",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "zone_id": str(zinfo.get("zone_id") or zinfo.get("name") or ""),
                    "severity": "medium",
                    "metadata": {
                        "detection_method": "frigate_geometry",
                        "bridge_source": "frigate",
                        "absence_sec": round(now - last, 1),
                        "duration_threshold_sec": dur,
                    },
                })
                with self._stats_lock:
                    self._stats["absence_emitted"] = int(self._stats.get("absence_emitted") or 0) + 1
            except Exception:
                logger.exception("absence emit failed")

    def _maybe_zone_counts(self, camera_id: str, zone_by_uuid: dict[str, dict[str, Any]]) -> None:
        for zuuid, zinfo in list(zone_by_uuid.items()):
            key = f"{camera_id}:{zuuid}"
            tracks = self._zone_track_counts.get(key) or set()
            n = len(tracks)
            if n <= 0:
                continue
            cfg = self._behavior_cfg(zinfo)
            try:
                threshold = int(cfg.get("count_threshold") or cfg.get("threshold") or 0)
            except (TypeError, ValueError):
                threshold = 0
            if threshold <= 0:
                # Default density emit only when many tracks
                if n < 8:
                    continue
                threshold = 8
            if n < threshold:
                continue
            if self._dedupe(f"count:{camera_id}:{zuuid}:{threshold}", ttl=45.0):
                continue
            label = str(cfg.get("class_filter") or "person").lower()
            et = "crowd_count_threshold" if label == "person" else "vehicle_count_threshold"
            if n >= max(threshold, 12) and label == "person":
                et = "scene_density_high"
            if self._emit is None:
                continue
            try:
                self._emit({
                    "event_id": str(uuid.uuid4()),
                    "camera_id": camera_id,
                    "event_type": et,
                    "event": et,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "zone_id": str(zinfo.get("zone_id") or zinfo.get("name") or ""),
                    "severity": "medium",
                    "count": n,
                    "metadata": {
                        "detection_method": "frigate_geometry",
                        "bridge_source": "frigate",
                        "count": n,
                        "threshold": threshold,
                    },
                })
                with self._stats_lock:
                    self._stats["count_emitted"] = int(self._stats.get("count_emitted") or 0) + 1
            except Exception:
                logger.exception("count emit failed")
            # prune set periodically
            if n > 50:
                self._zone_track_counts[key] = set(list(tracks)[-20:])

    def _maybe_proximity(
        self,
        camera_id: str,
        event_id: str,
        after: dict[str, Any],
        zone_by_uuid: dict[str, dict[str, Any]],
        label: str,
    ) -> None:
        """Emit person_vehicle_proximity when person+vehicle boxes are close (same event stream)."""
        if label not in _PERSON_LABELS and label not in _VEHICLE_LABELS_GEOM:
            return
        box = self._geom_box(after)
        if not box:
            return
        # Store last boxes per camera lightly
        cache_key = f"_prox_boxes_{camera_id}"
        store: dict[str, Any] = getattr(self, cache_key, {})
        store[event_id] = {"label": label, "box": box, "ts": time.monotonic()}
        # prune
        now = time.monotonic()
        store = {k: v for k, v in store.items() if now - float(v.get("ts") or 0) < 3.0}
        setattr(self, cache_key, store)
        persons = [v for v in store.values() if v.get("label") in _PERSON_LABELS]
        vehicles = [v for v in store.values() if v.get("label") in _VEHICLE_LABELS_GEOM]
        if not persons or not vehicles:
            return

        def _center(b: dict[str, Any]) -> tuple[float, float]:
            return (float(b["x"]) + float(b["width"]) / 2.0, float(b["y"]) + float(b["height"]) / 2.0)

        for p in persons:
            pc = _center(p["box"])
            for v in vehicles:
                vc = _center(v["box"])
                dist = ((pc[0] - vc[0]) ** 2 + (pc[1] - vc[1]) ** 2) ** 0.5
                if dist > 0.12:
                    continue
                pkey = f"prox:{camera_id}:{round(pc[0],2)}:{round(vc[0],2)}"
                if self._dedupe(pkey, ttl=20.0):
                    continue
                if self._emit is None:
                    continue
                try:
                    self._emit({
                        "event_id": str(uuid.uuid4()),
                        "camera_id": camera_id,
                        "event_type": "person_vehicle_proximity",
                        "event": "person_vehicle_proximity",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "frigate_event_id": event_id,
                        "severity": "medium",
                        "bbox": p["box"],
                        "metadata": {
                            "detection_method": "frigate_geometry",
                            "bridge_source": "frigate",
                            "distance_norm": round(dist, 4),
                            "vehicle_bbox": v["box"],
                        },
                    })
                    # multi-person one vehicle
                    near_persons = sum(
                        1 for pp in persons
                        if (( _center(pp["box"])[0] - vc[0]) ** 2 + (_center(pp["box"])[1] - vc[1]) ** 2) ** 0.5 < 0.15
                    )
                    if near_persons >= 2 and not self._dedupe(f"mpv:{camera_id}:{round(vc[0],2)}", ttl=30.0):
                        self._emit({
                            "event_id": str(uuid.uuid4()),
                            "camera_id": camera_id,
                            "event_type": "multiple_persons_one_vehicle",
                            "event": "multiple_persons_one_vehicle",
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                            "severity": "high",
                            "metadata": {
                                "detection_method": "frigate_geometry",
                                "bridge_source": "frigate",
                                "person_count": near_persons,
                            },
                        })
                    with self._stats_lock:
                        self._stats["proximity_emitted"] = int(self._stats.get("proximity_emitted") or 0) + 1
                except Exception:
                    logger.exception("proximity emit failed")
                return

    def _maybe_pedestrian_in_traffic(
        self,
        camera_id: str,
        event_id: str,
        after: dict[str, Any],
        zinfo: dict[str, Any],
        behavior: str,
        label: str,
    ) -> None:
        """Person entering a vehicle/traffic zone → pedestrian_in_vehicle_zone."""
        if label not in _PERSON_LABELS:
            return
        if behavior not in _TRAFFIC_ZONE_BEHAVIORS:
            return
        entered = set(self._zone_list(after.get("entered_zones")))
        zone_key = str(zinfo.get("id") or zinfo.get("zone_id") or "")
        fz_ids = {f"cv_zone_{zone_key}", zone_key}
        if not (entered & fz_ids) and not any(zone_key in str(x) for x in entered):
            return
        if self._dedupe(f"geom:{event_id}:pedestrian:{zone_key}", ttl=60.0):
            return
        self._emit_geometry(
            camera_id=camera_id, event_id=event_id, after=after, zinfo=zinfo,
            event_type="pedestrian_in_vehicle_zone", severity="medium",
            extra_meta={"traffic_behavior": behavior},
        )

    def _maybe_abandoned_active(
        self,
        camera_id: str,
        event_id: str,
        after: dict[str, Any],
        zinfo: dict[str, Any],
        behavior: str,
        label: str,
    ) -> None:
        """Immobile object-like track dwell → abandoned_object (no Gemini by default)."""
        if behavior != "abandoned_object":
            return
        if label in _PERSON_LABELS or label in _VEHICLE_LABELS_GEOM:
            # Still allow suitcase/backpack; skip people/cars unless labeled object-like
            if label not in _OBJECT_LIKE_LABELS:
                return
        elif label and label not in _OBJECT_LIKE_LABELS and label not in ("", "unknown"):
            # Frigate may track generic stationary blobs — allow empty/unknown
            if label not in ("dog", "cat"):  # noise
                pass
        zone_key = str(zinfo.get("id") or zinfo.get("zone_id") or "")
        dur = self._duration_sec(zinfo, 45.0)
        dkey = f"abandoned:{event_id}:{zone_key}"
        now = time.monotonic()
        first = self._dwell_since.get(dkey)
        if first is None:
            self._dwell_since[dkey] = now
            return
        if now - first < dur:
            return
        if self._dedupe(f"geom:{dkey}", ttl=max(90.0, dur)):
            return
        self._emit_geometry(
            camera_id=camera_id, event_id=event_id, after=after, zinfo=zinfo,
            event_type="abandoned_object", severity="high",
            extra_meta={
                "dwell_sec": round(now - first, 1),
                "duration_threshold_sec": dur,
                "object_label": label,
                "vlm_role": "anti_fp_optional",
            },
        )

    def _maybe_object_removed(
        self,
        camera_id: str,
        event_id: str,
        after: dict[str, Any],
        zinfo: dict[str, Any],
        behavior: str,
        label: str,
    ) -> None:
        if behavior not in ("abandoned_object", "presence"):
            return
        if label in _PERSON_LABELS or label in _VEHICLE_LABELS_GEOM:
            if label not in _OBJECT_LIKE_LABELS:
                return
        zone_key = str(zinfo.get("id") or zinfo.get("zone_id") or "")
        if self._dedupe(f"geom:{event_id}:object_removed:{zone_key}", ttl=60.0):
            return
        self._emit_geometry(
            camera_id=camera_id, event_id=event_id, after=after, zinfo=zinfo,
            event_type="object_removed", severity="medium",
            extra_meta={"object_label": label},
        )
        if not self._dedupe(f"geom:{event_id}:object_disappeared:{zone_key}", ttl=60.0):
            self._emit_geometry(
                camera_id=camera_id, event_id=event_id, after=after, zinfo=zinfo,
                event_type="object_disappeared", severity="medium",
                extra_meta={"object_label": label},
            )

    def _maybe_slow_vehicle(
        self,
        camera_id: str,
        event_id: str,
        after: dict[str, Any],
        before: dict[str, Any],
        zinfo: dict[str, Any],
    ) -> None:
        cfg = self._behavior_cfg(zinfo)
        try:
            min_kmh = float(cfg.get("min_speed_kmh") or cfg.get("speed_min_kmh") or 0)
        except (TypeError, ValueError):
            min_kmh = 0.0
        if min_kmh <= 0:
            return
        speed = self._read_speed_kmh(after, before, average_only=True)
        if speed is None or speed >= min_kmh:
            return
        if self._dedupe(f"speed_slow:{event_id}:{zinfo.get('id')}"):
            return
        if self._emit is None:
            return
        try:
            self._emit({
                "event_id": str(uuid.uuid4()),
                "camera_id": camera_id,
                "event_type": "speed_below_minimum",
                "event": "speed_below_minimum",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "zone_id": str(zinfo.get("zone_id") or zinfo.get("name") or ""),
                "frigate_event_id": event_id,
                "speed_kmh": round(float(speed), 1),
                "bbox": self._geom_box(after),
                "severity": "medium",
                "metadata": {
                    "detection_method": "frigate_speed",
                    "bridge_source": "frigate",
                    "min_speed_kmh": min_kmh,
                    "speed_emit_mode": self._speed_emit_mode(),
                    "zone_entry_exit": "exit",
                },
            })
            with self._stats_lock:
                self._stats["slow_emitted"] = int(self._stats.get("slow_emitted") or 0) + 1
        except Exception:
            logger.exception("slow vehicle emit failed")

    def _maybe_sudden_stop(
        self,
        camera_id: str,
        event_id: str,
        after: dict[str, Any],
        before: dict[str, Any],
        zinfo: dict[str, Any],
    ) -> None:
        zone_key = str(zinfo.get("id") or zinfo.get("zone_id") or "")
        peak = self._speed_peak.get(f"{event_id}:{zone_key}")
        avg = self._read_speed_kmh(after, before, average_only=True)
        if peak is None or avg is None:
            return
        # Sudden stop: peak was moving and average collapsed near stop at exit
        if float(peak) < 15.0 or float(avg) > 5.0:
            return
        if float(peak) - float(avg) < 10.0:
            return
        if self._dedupe(f"speed_stop:{event_id}:{zone_key}"):
            return
        if self._emit is None:
            return
        try:
            self._emit({
                "event_id": str(uuid.uuid4()),
                "camera_id": camera_id,
                "event_type": "sudden_stop",
                "event": "sudden_stop",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "zone_id": str(zinfo.get("zone_id") or zinfo.get("name") or ""),
                "frigate_event_id": event_id,
                "speed_kmh": round(float(avg), 1),
                "bbox": self._geom_box(after),
                "severity": "high",
                "metadata": {
                    "detection_method": "frigate_speed",
                    "bridge_source": "frigate",
                    "speed_peak_kmh": round(float(peak), 1),
                    "speed_est_kmh": round(float(avg), 1),
                    "zone_entry_exit": "exit",
                },
            })
            with self._stats_lock:
                self._stats["sudden_stop_emitted"] = int(self._stats.get("sudden_stop_emitted") or 0) + 1
        except Exception:
            logger.exception("sudden_stop emit failed")

    def _read_speed_kmh(
        self,
        after: dict[str, Any],
        before: dict[str, Any],
        *,
        average_only: bool = False,
    ) -> float | None:
        """Read Frigate speed estimate.

        average_only=True restricts to ``average_estimated_speed`` (Frigate's
        mean over the full zone traversal) — the only estimate allowed to
        decide a violation. Instantaneous keys stay available for in-zone
        peak diagnostics.
        """
        keys = (
            ("average_estimated_speed",)
            if average_only
            else ("average_estimated_speed", "current_estimated_speed", "estimated_speed")
        )
        data = after.get("data") if isinstance(after.get("data"), dict) else {}
        before_data = before.get("data") if isinstance(before.get("data"), dict) else {}
        for src in (data, before_data, after, before):
            if not isinstance(src, dict):
                continue
            for key in keys:
                if src.get(key) is not None:
                    try:
                        return float(src[key])
                    except (TypeError, ValueError):
                        continue
        return None

    def _speed_emit_mode(self) -> str:
        return str(os.environ.get("FRIGATE_SPEED_EMIT_MODE", "exit") or "exit").strip().lower()

    def _maybe_speed_in_zone(
        self,
        camera_id: str,
        event_id: str,
        after: dict[str, Any],
        before: dict[str, Any],
        zinfo: dict[str, Any],
    ) -> None:
        """Track peak speed in-zone; emit mid-zone only if FRIGATE_SPEED_EMIT_MODE=max_in_zone."""
        limit = self._speed_limit(zinfo)
        if limit <= 0:
            return
        speed = self._read_speed_kmh(after, before)
        if speed is None:
            return
        zone_key = str(zinfo.get("id") or zinfo.get("zone_id") or "")
        peak_key = f"{event_id}:{zone_key}"
        prev = self._speed_peak.get(peak_key, 0.0)
        if speed > prev:
            self._speed_peak[peak_key] = speed
        mode = self._speed_emit_mode()
        peak = self._speed_peak.get(peak_key, speed)
        if peak < limit:
            return
        if mode in ("shadow_max", "shadow"):
            with self._stats_lock:
                self._stats["speed_shadow_max"] = int(self._stats.get("speed_shadow_max") or 0) + 1
            logger.info(
                "speed_shadow_max camera=%s peak=%.1f limit=%.1f event=%s mode=%s",
                camera_id[:8], peak, limit, event_id[:12], mode,
            )
            return
        # Default / validation: exit-only — never emit while still inside the zone.
        if mode != "max_in_zone":
            return
        if self._dedupe(f"speed_max:{event_id}:{zone_key}"):
            return
        self._emit_speeding(camera_id, event_id, after, zinfo, peak, limit)

    def _emit_speeding(
        self,
        camera_id: str,
        event_id: str,
        after: dict[str, Any],
        zinfo: dict[str, Any],
        speed: float,
        limit: float,
    ) -> None:
        if self._emit is None:
            return
        data = after.get("data") if isinstance(after.get("data"), dict) else {}
        zone_name = str(zinfo.get("zone_id") or zinfo.get("name") or "")
        box = None
        data_box = data.get("box") if isinstance(data, dict) else None
        if isinstance(data_box, (list, tuple)) and len(data_box) >= 4:
            box = {
                "x": float(data_box[0]),
                "y": float(data_box[1]),
                "width": float(data_box[2]),
                "height": float(data_box[3]),
                "norm": True,
            }
        emit_mode = self._speed_emit_mode()
        zone_key = str(zinfo.get("id") or zinfo.get("zone_id") or "")
        peak = self._speed_peak.pop(f"{event_id}:{zone_key}", speed)
        start_time = after.get("start_time") or data.get("start_time")
        end_time = after.get("end_time") or data.get("end_time") or after.get("frame_time")
        entered = after.get("entered_zones") or data.get("entered_zones") or []
        current = after.get("current_zones") or data.get("current_zones") or []
        evt = {
            "event_id": str(uuid.uuid4()),
            "camera_id": camera_id,
            "event_type": "speeding",
            "event": "speeding",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "zone_id": zone_name,
            "frigate_event_id": event_id,
            "speed_kmh": round(speed, 1),
            "speed_limit_kmh": limit,
            "bbox": box,
            "severity": "high",
            "metadata": {
                "detection_method": "frigate_speed",
                "bridge_source": "frigate",
                "frigate_event_id": event_id,
                "frigate_label": after.get("label"),
                "bbox_source": "frigate",
                "speed_est_kmh": round(speed, 1),
                "speed_peak_kmh": round(float(peak), 1),
                "speed_limit_kmh": limit,
                "speed_emit_mode": emit_mode,
                "zone_entry_exit": "exit" if emit_mode == "exit" else emit_mode,
                "frigate_start_time": start_time,
                "frigate_end_time": end_time,
                "entered_zones": list(entered) if isinstance(entered, (list, tuple)) else [],
                "current_zones": list(current) if isinstance(current, (list, tuple)) else [],
            },
        }
        try:
            self._emit(evt)
            with self._stats_lock:
                self._stats["speed_emitted"] += 1
            logger.info(
                "frigate_bridge speeding camera=%s speed=%.1f limit=%.1f event=%s mode=%s",
                camera_id[:8], speed, limit, event_id[:12], emit_mode,
            )
        except Exception:
            logger.exception("frigate_bridge speed emit failed")

    def _maybe_speed(
        self,
        camera_id: str,
        event_id: str,
        after: dict[str, Any],
        before: dict[str, Any],
        zinfo: dict[str, Any],
    ) -> None:
        """Emit speeding only after the vehicle exits the speed_measurement zone."""
        mode = self._speed_emit_mode()
        if mode == "max_in_zone":
            # Mid-zone path owns emits when explicitly requested.
            return
        limit = self._speed_limit(zinfo)
        if limit <= 0:
            return
        # Verdict speed = Frigate's average over the FULL zone traversal only.
        # Instantaneous/peak estimates are diagnostics; judging on them would
        # sanction a vehicle before it finished crossing the measured zone.
        speed = self._read_speed_kmh(after, before, average_only=True)
        zone_key = str(zinfo.get("id") or zinfo.get("zone_id") or "")
        peak_key = f"{event_id}:{zone_key}"
        peak = self._speed_peak.get(peak_key)
        if speed is None:
            with self._stats_lock:
                self._stats["speed_no_estimate"] = int(self._stats.get("speed_no_estimate") or 0) + 1
            logger.info(
                "speed_bridge_reject reason=no_average_speed camera=%s event=%s peak=%s",
                camera_id[:8], event_id[:12], peak,
            )
            self._speed_peak.pop(peak_key, None)
            return
        use_speed = float(speed)
        if mode in ("shadow_max", "shadow"):
            with self._stats_lock:
                self._stats["speed_shadow_max"] = int(self._stats.get("speed_shadow_max") or 0) + 1
            logger.info(
                "speed_shadow_exit camera=%s speed=%.1f peak=%s limit=%.1f event=%s",
                camera_id[:8], use_speed, peak, limit, event_id[:12],
            )
            self._speed_peak.pop(peak_key, None)
            return
        if use_speed < limit:
            with self._stats_lock:
                self._stats["speed_below_limit"] = int(self._stats.get("speed_below_limit") or 0) + 1
            logger.info(
                "speed_bridge_reject reason=below_limit camera=%s speed=%.1f limit=%.1f event=%s",
                camera_id[:8], use_speed, limit, event_id[:12],
            )
            self._speed_peak.pop(peak_key, None)
            return
        if self._dedupe(f"speed:{event_id}:{zinfo.get('id')}"):
            return
        self._emit_speeding(camera_id, event_id, after, zinfo, use_speed, limit)
