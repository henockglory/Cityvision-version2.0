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
        self._client: mqtt.Client | None = None
        self._stop = threading.Event()
        self._seen: dict[str, float] = {}
        self._seen_lock = threading.Lock()
        self._stats = {
            "mqtt_messages": 0,
            "cabin_enqueued": 0,
            "face_enqueued": 0,
            "plate_enqueued": 0,
            "red_light_enqueued": 0,
            "speed_emitted": 0,
            "dropped_dedupe": 0,
            "snapshot_fail": 0,
        }
        self._stats_lock = threading.Lock()

    @property
    def enabled(self) -> bool:
        return self._vlm_enabled or self._speed_enabled or self._face_enabled or self._plate_enabled

    def stats(self) -> dict[str, int]:
        with self._stats_lock:
            return dict(self._stats)

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

        # Cabin / face / plate: object currently in or just entered a mapped zone
        active_zone_ids = entered | current
        for fz in active_zone_ids:
            zuuid = parse_zone_uuid(fz)
            if not zuuid:
                continue
            zinfo = zone_by_uuid.get(zuuid)
            if not zinfo:
                continue
            behavior = str(zinfo.get("behavior") or "")
            if self._vlm_enabled and label in _VEHICLE_LABELS and behavior in _CABIN_BEHAVIORS:
                self._maybe_cabin(camera_id, event_id, after, zinfo, behavior)
            if self._vlm_enabled and label in _VEHICLE_LABELS and behavior == "red_light_observation":
                self._maybe_red_light(camera_id, event_id, after, zinfo, zone_by_uuid)
            if self._face_enabled and label == "person" and behavior not in _FACE_SKIP_BEHAVIORS:
                self._maybe_face(camera_id, event_id, after, zinfo)
            if self._plate_enabled and label in _VEHICLE_LABELS and behavior == "plate_ocr":
                self._maybe_plate(camera_id, event_id, after, zinfo)

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
        out: dict[str, dict[str, Any]] = {}
        for z in zones:
            if not isinstance(z, dict):
                continue
            zid = str(z.get("id") or z.get("uuid") or "").strip()
            if zid:
                out[zid] = z
        return out

    @staticmethod
    def _zone_list(raw: Any) -> list[str]:
        if isinstance(raw, list):
            return [str(x) for x in raw if x]
        return []

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
        dedupe_key = f"cabin:{event_id}:{rule}"
        if self._dedupe(dedupe_key):
            return
        jpeg, box, _ev = fetch_cabin_jpeg(
            self._frigate_url,
            event_id,
            after,
            wait_sec=self._snapshot_wait,
            label=str(after.get("label") or ""),
        )
        if not jpeg:
            with self._stats_lock:
                self._stats["snapshot_fail"] += 1
            logger.info(
                "frigate_bridge snapshot_fail cabin camera=%s event=%s",
                camera_id[:8], event_id[:12],
            )
            return
        from citevision_ai.vlm.queue import VlmJob

        crop_mode_env = (os.environ.get("FRIGATE_VLM_BRIDGE_CROP_MODE") or "vehicle_bbox").strip().lower()
        meta_crop_mode = "frigate_vehicle_bbox" if crop_mode_env in {
            "vehicle_bbox",
            "vehicle",
            "car_bbox",
            "passthrough",
        } else "cabin_driver_subcrop"

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
        if self._dedupe(f"red:{event_id}:{rule}"):
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
            },
        }
        ok = self._vlm_queue.try_enqueue(
            VlmJob(
                jpeg=jpeg,
                rule=rule,
                min_confidence=self._zone_conf(obs_zinfo),
                event_skeleton=skeleton,
                extra_context=(
                    f"frigate_event={event_id} observation_zone={zone_name} "
                    "vehicle in red_light_observation; judge if light is red"
                ),
            )
        )
        if ok:
            with self._stats_lock:
                self._stats["red_light_enqueued"] += 1
            logger.info(
                "frigate_bridge red_light enqueue camera=%s event=%s",
                camera_id[:8], event_id[:12],
            )

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
        from citevision_ai.vlm.queue import VlmJob

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
                "detection_method": "gemini_ocr",
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
            )
        )
        if ok:
            with self._stats_lock:
                self._stats["plate_enqueued"] += 1

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
        data = after.get("data") if isinstance(after.get("data"), dict) else {}
        before_data = before.get("data") if isinstance(before.get("data"), dict) else {}
        speed = None
        for src in (data, before_data, after, before):
            if not isinstance(src, dict):
                continue
            for key in ("average_estimated_speed", "current_estimated_speed", "estimated_speed"):
                if src.get(key) is not None:
                    try:
                        speed = float(src[key])
                        break
                    except (TypeError, ValueError):
                        continue
            if speed is not None:
                break
        if speed is None or speed < limit:
            return
        if self._dedupe(f"speed:{event_id}:{zinfo.get('id')}"):
            return
        if self._emit is None:
            return
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
            },
        }
        try:
            self._emit(evt)
            with self._stats_lock:
                self._stats["speed_emitted"] += 1
            logger.info(
                "frigate_bridge speeding camera=%s speed=%.1f limit=%.1f event=%s",
                camera_id[:8], speed, limit, event_id[:12],
            )
        except Exception:
            logger.exception("frigate_bridge speed emit failed")
