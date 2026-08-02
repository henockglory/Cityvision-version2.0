"""Frigate MQTT event bridge → Gemini VLM / speeding emits."""
from __future__ import annotations

import json
import logging
import os
import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Callable

import paho.mqtt.client as mqtt

from citevision_ai.frigate_bridge.ids import parse_camera_uuid, parse_zone_uuid
from citevision_ai.frigate_bridge.snapshot import fetch_cabin_jpeg, fetch_red_light_jpeg, fetch_subject_jpeg

logger = logging.getLogger(__name__)

EmitCallback = Callable[[dict[str, Any]], None]
SpatialResolver = Callable[[str], dict[str, Any] | None]
LightStateResolver = Callable[[str], str]
LightDebugResolver = Callable[[str], dict[str, Any]]

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
        mqtt_user: str = "",
        mqtt_password: str = "",
        snapshot_wait_sec: float = 25.0,
        watchlist_resolver: Callable[[], list[dict[str, Any]]] | None = None,
        light_state_resolver: LightStateResolver | None = None,
        light_debug_resolver: LightDebugResolver | None = None,
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
        self._snapshot_wait = float(snapshot_wait_sec)
        self._watchlist_resolver = watchlist_resolver
        self._light_state = light_state_resolver
        self._light_debug = light_debug_resolver
        self._client: mqtt.Client | None = None
        self._stop = threading.Event()
        self._seen: dict[str, float] = {}
        self._seen_lock = threading.Lock()
        self._stats: dict[str, Any] = {
            "mqtt_messages": 0,
            "cabin_enqueued": 0,
            "cabin_snapshot_fail": 0,
            "cabin_skipped_too_small": 0,
            "face_enqueued": 0,
            "plate_enqueued": 0,
            "red_light_enqueued": 0,
            "red_light_skipped_not_red": 0,
            "red_light_skipped_unknown": 0,
            "red_light_snapshot_fail": 0,
            "red_light_gate_grace": 0,
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

    @property
    def enabled(self) -> bool:
        return self._vlm_enabled or self._speed_enabled or self._face_enabled or self._plate_enabled

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

        # Red light / cabin / face / plate: Frigate zones on the MQTT after payload
        active_zone_ids = self._active_frigate_zones(after) | entered | current
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
                and (label in _VEHICLE_LABELS or label == "person")
            ):
                self._maybe_cabin(camera_id, event_id, after, zinfo, behavior)
            if self._vlm_enabled and label in _VEHICLE_LABELS and behavior == "red_light_observation":
                self._maybe_red_light(camera_id, event_id, after, zinfo, zone_by_uuid)
            if self._face_enabled and label == "person" and behavior not in _FACE_SKIP_BEHAVIORS:
                self._maybe_face(camera_id, event_id, after, zinfo)
            if self._plate_enabled and label in _VEHICLE_LABELS and behavior == "plate_ocr":
                self._maybe_plate(camera_id, event_id, after, zinfo)

        self._stats_lock = threading.Lock()
        self._speed_peak: dict[str, float] = {}

        # Speed: also track max while inside zone (campaign shadow / max_in_zone modes).
        if self._speed_enabled and label in _VEHICLE_LABELS:
            in_speed_zones = active_zone_ids | entered | current
            for fz in in_speed_zones:
                zuuid = parse_zone_uuid(fz)
                if not zuuid:
                    continue
                zinfo = zone_by_uuid.get(zuuid)
                if not zinfo or str(zinfo.get("behavior") or "") != "speed_measurement":
                    continue
                self._maybe_speed_in_zone(camera_id, event_id, after, before, zinfo)

        # Speed: vehicle left a speed_measurement zone with estimate
        if self._speed_enabled and label in _VEHICLE_LABELS:
            for fz in exited:
                zuuid = parse_zone_uuid(fz)
                if not zuuid:
                    continue
                zinfo = zone_by_uuid.get(zuuid)
                if not zinfo or str(zinfo.get("behavior") or "") != "speed_measurement":
                    continue
                self._maybe_speed(camera_id, event_id, after, before, zinfo)

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
        # Prefer seatbelt first under free-tier (same as YOLO path)
        rule = rules[0]
        # Re-sample ~25s — shorter TTLs flooded Gemini (dropped_full) with distant crops.
        dedupe_key = f"cabin:{event_id}:{rule}"
        try:
            dedupe_ttl = float(os.environ.get("FRIGATE_CABIN_DEDUPE_SEC", "60") or 60)
        except (TypeError, ValueError):
            dedupe_ttl = 60.0
        if self._dedupe(dedupe_key, ttl=max(1.0, dedupe_ttl)):
            return
        # Size gate before snapshot download (Frigate box is xywh, often normalized).
        box_probe = after.get("box") or (after.get("data") or {}).get("box")
        if isinstance(box_probe, (list, tuple)) and len(box_probe) >= 4:
            try:
                _x, _y, w, h = (float(box_probe[i]) for i in range(4))
                if w * h < 0.035 or h < 0.12:
                    with self._stats_lock:
                        self._stats["cabin_skipped_too_small"] = int(
                            self._stats.get("cabin_skipped_too_small") or 0
                        ) + 1
                    return
            except (TypeError, ValueError):
                pass
        jpeg, box, _ev = fetch_cabin_jpeg(
            self._frigate_url,
            event_id,
            after,
            wait_sec=self._snapshot_wait,
            label=str(after.get("label") or ""),
        )
        if not jpeg:
            with self._stats_lock:
                # Distinguishes empty jpeg (too small / decode) from HTTP snapshot miss.
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
        skeleton = {
            "event_id": str(uuid.uuid4()),
            "camera_id": camera_id,
            "event_type": rule,
            "event": rule,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "zone_id": zone_name,
            "frigate_event_id": event_id,
            "bbox": box,
            "severity": "medium",
            "metadata": {
                "detection_method": "gemini_vlm",
                "bridge_source": "frigate",
                "frigate_event_id": event_id,
                "frigate_label": after.get("label"),
                "zone_behavior": behavior,
                "crop_mode": meta_crop_mode,
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
                "frigate_bridge cabin enqueue rule=%s camera=%s event=%s",
                rule, camera_id[:8], event_id[:12],
            )

    def _maybe_red_light(
        self,
        camera_id: str,
        event_id: str,
        after: dict[str, Any],
        obs_zinfo: dict[str, Any],
        zone_by_uuid: dict[str, dict[str, Any]],
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
        if force_enqueue:
            logger.warning(
                "frigate_bridge red_light DEBUG force enqueue camera=%s event=%s "
                "raw=%s stable=%s gate=%s",
                camera_id[:8], event_id[:12], raw_s, stable_s, light_state,
            )
        elif light_state == "unknown":
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
        if not force_enqueue and light_state != "red":
            with self._stats_lock:
                self._stats["red_light_skipped_not_red"] = int(
                    self._stats.get("red_light_skipped_not_red") or 0
                ) + 1
            logger.info(
                "frigate_bridge red_light skip not_red camera=%s event=%s "
                "raw=%s stable=%s gate=%s gate_mode=%s",
                camera_id[:8], event_id[:12], raw_s, stable_s, light_state, gate_mode,
            )
            return
        if grace_active:
            with self._stats_lock:
                self._stats["red_light_gate_grace"] = int(
                    self._stats.get("red_light_gate_grace") or 0
                ) + 1
        # Re-sample every ~8s while the track stays in observation (light may turn red).
        # Fail-closed should_emit unchanged — more tries, not forged violations.
        if self._dedupe(f"red:{event_id}:{rule}", ttl=8.0):
            return
        light_poly: list[Any] = []
        for z in zone_by_uuid.values():
            if str(z.get("behavior") or "") == "traffic_light_color":
                poly = z.get("polygon") or z.get("points") or []
                if isinstance(poly, list):
                    light_poly = poly
                break
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

        zone_name = str(obs_zinfo.get("zone_id") or obs_zinfo.get("name") or "")
        skeleton = {
            "event_id": str(uuid.uuid4()),
            "camera_id": camera_id,
            "event_type": rule,
            "event": rule,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "zone_id": zone_name,
            "frigate_event_id": event_id,
            "bbox": box,
            "severity": "high",
            "metadata": {
                "detection_method": "gemini_vlm",
                "bridge_source": "frigate",
                "frigate_event_id": event_id,
                "frigate_label": after.get("label"),
                "zone_behavior": "red_light_observation",
                "hsv_light_state": light_state,
                "hsv_raw": raw_s,
                "hsv_stable": stable_s,
                "gate_mode": gate_mode,
                "grace_active": grace_active,
                "debug_forced": force_enqueue,
            },
        }
        self._maybe_emit_lf_or_g_local(
            skeleton=skeleton,
            camera_id=camera_id,
            event_id=event_id,
            light_state=light_state,
            force_enqueue=force_enqueue,
        )
        ok = self._vlm_queue.try_enqueue(
            VlmJob(
                jpeg=jpeg,
                rule=rule,
                min_confidence=self._zone_conf(obs_zinfo),
                event_skeleton=skeleton,
                extra_context=(
                    f"frigate_event={event_id} observation_zone={zone_name} "
                    f"hsv_gate=red raw={raw_s} stable={stable_s} gate_mode={gate_mode} "
                    f"grace={grace_active}; vehicle in red_light_observation; confirm red violation"
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
    ) -> None:
        from citevision_ai.road_enforcement.red_light_vote import local_frigate_would_emit, red_light_vote_mode

        hsv_red = force_enqueue or light_state == "red"
        if not local_frigate_would_emit(hsv_gate_red=hsv_red, frigate_in_obs_zone=True):
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
            "detection_method": "gemini_vlm",
            "bridge_source": "frigate",
            "frigate_event_id": event_id,
        }
        # Always: clear-face detection.
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
        enqueued = bool(ok_det)

        # Watchlist cameras: Gemini match against label/identifier text context.
        wl = self._watchlist_entries()
        if wl:
            labels: list[str] = []
            for entry in wl[:20]:
                if not isinstance(entry, dict):
                    continue
                for key in ("label", "identifier", "name", "display_name"):
                    val = str(entry.get(key) or "").strip()
                    if val and val not in labels:
                        labels.append(val)
            ctx = (
                f"frigate_event={event_id} zone={zone_name} "
                f"watchlist_labels={', '.join(labels) if labels else '(empty)'}"
            )
            ok_wl = self._vlm_queue.try_enqueue(
                VlmJob(
                    jpeg=jpeg,
                    rule="face_watchlist_match",
                    min_confidence=0.55,
                    extra_context=ctx,
                    event_skeleton={
                        "event_id": str(uuid.uuid4()),
                        "camera_id": camera_id,
                        "event_type": "face_watchlist_match",
                        "event": "face_watchlist_match",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "zone_id": zone_name,
                        "frigate_event_id": event_id,
                        "bbox": box,
                        "severity": "critical",
                        "metadata": {
                            **base_meta,
                            "watchlist_labels": labels,
                        },
                    },
                )
            )
            enqueued = enqueued or bool(ok_wl)

        if enqueued:
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

    def _read_speed_kmh(
        self,
        after: dict[str, Any],
        before: dict[str, Any],
    ) -> float | None:
        data = after.get("data") if isinstance(after.get("data"), dict) else {}
        before_data = before.get("data") if isinstance(before.get("data"), dict) else {}
        for src in (data, before_data, after, before):
            if not isinstance(src, dict):
                continue
            for key in ("average_estimated_speed", "current_estimated_speed", "estimated_speed"):
                if src.get(key) is not None:
                    try:
                        return float(src[key])
                    except (TypeError, ValueError):
                        continue
        return None

    def _maybe_speed_in_zone(
        self,
        camera_id: str,
        event_id: str,
        after: dict[str, Any],
        before: dict[str, Any],
        zinfo: dict[str, Any],
    ) -> None:
        """Track peak speed in-zone; optional emit on max (FRIGATE_SPEED_EMIT_MODE)."""
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
        mode = str(os.environ.get("FRIGATE_SPEED_EMIT_MODE", "exit") or "exit").strip().lower()
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
            }
        emit_mode = str(os.environ.get("FRIGATE_SPEED_EMIT_MODE", "exit") or "exit")
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
                "speed_est_kmh": round(speed, 1),
                "speed_limit_kmh": limit,
                "speed_emit_mode": emit_mode,
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
        limit = self._speed_limit(zinfo)
        if limit <= 0:
            return
        speed = self._read_speed_kmh(after, before)
        if speed is None:
            with self._stats_lock:
                self._stats["speed_no_estimate"] = int(self._stats.get("speed_no_estimate") or 0) + 1
            logger.info(
                "speed_bridge_reject reason=no_estimate camera=%s event=%s",
                camera_id[:8], event_id[:12],
            )
            return
        if speed < limit:
            with self._stats_lock:
                self._stats["speed_below_limit"] = int(self._stats.get("speed_below_limit") or 0) + 1
            logger.info(
                "speed_bridge_reject reason=below_limit camera=%s speed=%.1f limit=%.1f event=%s",
                camera_id[:8], speed, limit, event_id[:12],
            )
            return
        if self._dedupe(f"speed:{event_id}:{zinfo.get('id')}"):
            return
        self._emit_speeding(camera_id, event_id, after, zinfo, speed, limit)
