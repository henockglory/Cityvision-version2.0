from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class BBox:
    x: float
    y: float
    width: float
    height: float

    @property
    def center(self) -> tuple[float, float]:
        return (self.x + self.width / 2, self.y + self.height / 2)

    def to_dict(self) -> dict[str, float]:
        return {"x": self.x, "y": self.y, "width": self.width, "height": self.height}


@dataclass
class Detection:
    track_id: int
    class_id: int
    class_name: str
    confidence: float
    bbox: BBox

    def to_dict(self) -> dict[str, Any]:
        return {
            "track_id": self.track_id,
            "class_id": self.class_id,
            "class_name": self.class_name,
            "confidence": self.confidence,
            "bbox": self.bbox.to_dict(),
        }


@dataclass
class DetectionFrame:
    camera_id: str
    timestamp: str
    frame_id: int
    width: int
    height: int
    detections: list[Detection] = field(default_factory=list)

    def to_mqtt_payload(self) -> dict[str, Any]:
        return {
            "camera_id": self.camera_id,
            "timestamp": self.timestamp,
            "frame_id": self.frame_id,
            "resolution": {"width": self.width, "height": self.height},
            "detections": [d.to_dict() for d in self.detections],
        }
