from __future__ import annotations

import json
import logging
from typing import Any

import paho.mqtt.client as mqtt

logger = logging.getLogger(__name__)

DETECTION_TOPIC = "cv/detections/{camera_id}"
EVENT_TOPIC = "cv/events/{camera_id}"


class MqttPublisher:
    """MQTT publisher for detection and event payloads."""

    def __init__(
        self,
        broker: str = "localhost",
        port: int = 1883,
        username: str | None = None,
        password: str | None = None,
    ) -> None:
        self.broker = broker
        self.port = port
        self._client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        if username:
            self._client.username_pw_set(username, password)
        self._connected = False

    def connect(self) -> None:
        try:
            self._client.connect(self.broker, self.port, keepalive=60)
            self._client.loop_start()
            self._connected = True
            logger.info("MQTT connected to %s:%d", self.broker, self.port)
        except Exception:
            logger.warning("MQTT connection failed; publishing disabled")
            self._connected = False

    def disconnect(self) -> None:
        if self._connected:
            self._client.loop_stop()
            self._client.disconnect()
            self._connected = False

    def publish_detection(self, camera_id: str, payload: dict[str, Any]) -> bool:
        topic = DETECTION_TOPIC.format(camera_id=camera_id)
        return self._publish(topic, payload)

    def publish_event(self, camera_id: str, payload: dict[str, Any]) -> bool:
        topic = EVENT_TOPIC.format(camera_id=camera_id)
        return self._publish(topic, payload)

    def _publish(self, topic: str, payload: dict[str, Any]) -> bool:
        if not self._connected:
            logger.debug("MQTT not connected; would publish to %s", topic)
            return False
        result = self._client.publish(topic, json.dumps(payload), qos=1)
        return result.rc == mqtt.MQTT_ERR_SUCCESS
