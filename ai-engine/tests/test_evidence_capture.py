"""Evidence image role assignment (scene / subject / plate)."""

from __future__ import annotations

import cv2
import numpy as np

from citevision_ai.evidence.capture import capture_images_from_policy
from citevision_ai.evidence.gate import default_evidence_policy


def _frame(w: int = 640, h: int = 480) -> np.ndarray:
    img = np.zeros((h, w, 3), dtype=np.uint8)
    cv2.rectangle(img, (200, 150), (420, 320), (40, 40, 200), -1)
    return img


def test_subject_is_full_scene_plate_is_crop():
    frame = _frame()
    bbox = {"x": 0.3125, "y": 0.3125, "width": 0.34375, "height": 0.354}
    spec = default_evidence_policy()["images"]
    scene, subject, extras = capture_images_from_policy(frame, bbox, spec, quality=80)

    assert scene is not None
    assert subject is not None
    assert scene == subject

    decoded_scene = cv2.imdecode(np.frombuffer(scene, np.uint8), cv2.IMREAD_COLOR)
    assert decoded_scene.shape[:2] == frame.shape[:2]

    assert len(extras) == 1 and extras[0] is not None
    decoded_plate = cv2.imdecode(np.frombuffer(extras[0], np.uint8), cv2.IMREAD_COLOR)
    assert decoded_plate.shape[0] < frame.shape[0]
    assert decoded_plate.shape[1] < frame.shape[1]
