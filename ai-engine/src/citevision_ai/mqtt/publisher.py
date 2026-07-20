from __future__ import annotations

import json
import logging
import threading
import time
from typing import Any

import paho.mqtt.client as mqtt

logger = logging.getLogger(__name__)

DETECTION_TOPIC = "cv/detections/{camera_id}"
EVENT_TOPIC = "cv/events/{camera_id}"

# If the initial connection fails, retry in the background every N seconds.
_RECONNECT_INTERVAL_SEC = 10.0


class MqttPublisher:
    """MQTT publisher for detection and event payloads.

    Connects with up to `retries` attempts at startup.  If the broker is
    unavailable, a background thread keeps retrying every
    _RECONNECT_INTERVAL_SEC seconds so that publishing resumes as soon as the
    broker comes up — no AI restart needed.
    """

    def __init__(
        self,
        broker: str = "localhost",
        port: int = 1884,
        username: str | None = None,
        password: str | None = None,
    ) -> None:
        self.broker = broker
        self.port = port
        self._client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        if username:
            self._client.username_pw_set(username, password)
        self._connected = False
        self._lock = threading.Lock()
        self._reconnect_thread: threading.Thread | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def connect(self, retries: int = 15, delay_sec: float = 2.0) -> None:
        for attempt in range(1, retries + 1):
            try:
                self._client.connect(self.broker, self.port, keepalive=60)
                self._client.loop_start()
                with self._lock:
                    self._connected = True
                logger.info("MQTT connected to %s:%d", self.broker, self.port)
                return
            except Exception as exc:
                if attempt < retries:
                    logger.info(
                        "MQTT connect attempt %d/%d failed (%s); retrying…",
                        attempt,
                        retries,
                        exc,
                    )
                    time.sleep(delay_sec)
                else:
                    logger.warning(
                        "MQTT connection failed after %d attempts; "
                        "starting background reconnect loop",
                        retries,
                    )
                    self._start_reconnect_loop()

    def disconnect(self) -> None:
        with self._lock:
            was_connected = self._connected
            self._connected = False
        if was_connected:
            self._client.loop_stop()
            self._client.disconnect()

    def publish_detection(self, camera_id: str, payload: dict[str, Any]) -> bool:
        topic = DETECTION_TOPIC.format(camera_id=camera_id)
        return self._publish(topic, payload)

    def publish_event(self, camera_id: str, payload: dict[str, Any]) -> bool:
        topic = EVENT_TOPIC.format(camera_id=camera_id)
        return self._publish(topic, payload)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _publish(self, topic: str, payload: dict[str, Any]) -> bool:
        with self._lock:
            connected = self._connected
        if not connected:
            logger.debug("MQTT not connected; would publish to %s", topic)
            return False
        result = self._client.publish(topic, json.dumps(payload), qos=1)
        return result.rc == mqtt.MQTT_ERR_SUCCESS

    def _try_connect_once(self) -> bool:
        """Attempt a single connection; return True on success."""
        try:
            # Recreate client to avoid stale state from failed previous attempt.
            new_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
            if self._client._username:  # type: ignore[attr-defined]
                new_client.username_pw_set(
                    self._client._username,  # type: ignore[attr-defined]
                    self._client._password,  # type: ignore[attr-defined]
                )
            new_client.connect(self.broker, self.port, keepalive=60)
            new_client.loop_start()
            with self._lock:
                # Swap in the new working client.
                old = self._client
                self._client = new_client
                self._connected = True
            try:
                old.loop_stop()
                old.disconnect()
            except Exception:
                pass
            logger.info(
                "MQTT reconnected to %s:%d (background retry)",
                self.broker, self.port,
            )
            return True
        except Exception as exc:
            logger.debug("MQTT background reconnect failed: %s", exc)
            return False

    def _start_reconnect_loop(self) -> None:
        if self._reconnect_thread and self._reconnect_thread.is_alive():
            return
        t = threading.Thread(
            target=self._reconnect_loop,
            daemon=True,
            name="mqtt-reconnect",
        )
        self._reconnect_thread = t
        t.start()

    def _reconnect_loop(self) -> None:
        while True:
            time.sleep(_RECONNECT_INTERVAL_SEC)
            with self._lock:
                already = self._connected
            if already:
                return
            if self._try_connect_once():
                return
