from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

CARRY_OBJECT_CLASSES = {"backpack", "handbag", "suitcase", "sports ball"}


class BehaviorLabel(str, Enum):
    NORMAL = "normal"
    RUNNING = "running"
    CROWDING = "crowding"
    ABANDONED_OBJECT = "abandoned_object"
    TAILGATING = "tailgating"
    WRONG_WAY = "wrong_way"
    CROUCHING = "crouching"
    FALLING = "falling"
    FIGHTING = "fighting"
    QUEUE_FORMING = "queue_forming"
    ERRATIC = "erratic"
    WANDERING = "wandering"
    CLIMBING = "climbing"
    CARRYING = "carrying"
    RAPID_ACTIVITY = "rapid_activity"


BEHAVIOR_EVENT_TYPES: dict[BehaviorLabel, str] = {
    BehaviorLabel.RUNNING: "running",
    BehaviorLabel.CROWDING: "crowd_gathering",
    BehaviorLabel.TAILGATING: "tailgating",
    BehaviorLabel.WRONG_WAY: "wrong_way",
    BehaviorLabel.ABANDONED_OBJECT: "object_appeared",
    BehaviorLabel.FALLING: "falling",
    BehaviorLabel.FIGHTING: "fighting",
    BehaviorLabel.QUEUE_FORMING: "queue_forming",
    BehaviorLabel.ERRATIC: "erratic_motion",
    BehaviorLabel.WANDERING: "wandering",
    BehaviorLabel.CROUCHING: "crouch_detected",
    BehaviorLabel.CLIMBING: "climb_detected",
    BehaviorLabel.CARRYING: "carry_detected",
    BehaviorLabel.RAPID_ACTIVITY: "running",
}


@dataclass
class BehaviorSignal:
    track_id: int
    label: BehaviorLabel
    confidence: float
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class _LineCrossing:
    track_id: int
    direction: str
    timestamp: float


class BehaviorHeuristics:
    """Rule-based behavior classification from track kinematics and line history."""

    def __init__(
        self,
        speed_threshold: float = 120.0,
        crowding_min_tracks: int = 5,
        crowding_radius: float = 80.0,
        tailgate_window_seconds: float = 2.0,
        fight_overlap_ratio: float = 0.25,
        wandering_path_ratio: float = 3.0,
        carry_proximity: float = 50.0,
        queue_min_persons: int = 4,
        queue_alignment_tolerance: float = 15.0,
        erratic_turn_threshold: float = 2.5,
    ) -> None:
        self.speed_threshold = speed_threshold
        self.crowding_min_tracks = crowding_min_tracks
        self.crowding_radius = crowding_radius
        self.tailgate_window_seconds = tailgate_window_seconds
        self.fight_overlap_ratio = fight_overlap_ratio
        self.wandering_path_ratio = wandering_path_ratio
        self.carry_proximity = carry_proximity
        self.queue_min_persons = queue_min_persons
        self.queue_alignment_tolerance = queue_alignment_tolerance
        self.erratic_turn_threshold = erratic_turn_threshold
        self._line_expected: dict[tuple[str, str], str] = {}
        self._line_geometry: dict[tuple[str, str], tuple[dict, dict]] = {}
        self._crossing_history: dict[tuple[str, str], list[_LineCrossing]] = {}

    def set_line_config(
        self,
        camera_id: str,
        line_id: str,
        start: dict[str, float],
        end: dict[str, float],
        expected_direction: str = "unknown",
    ) -> None:
        key = (camera_id, line_id)
        self._line_geometry[key] = (start, end)
        if expected_direction not in ("", "unknown", "both"):
            self._line_expected[key] = expected_direction

    @staticmethod
    def _speed(history: list[tuple[float, float]]) -> float:
        if len(history) < 2:
            return 0.0
        x1, y1 = history[-2]
        x2, y2 = history[-1]
        return ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5

    @staticmethod
    def _path_ratio(history: list[tuple[float, float]]) -> float:
        if len(history) < 3:
            return 0.0
        total = 0.0
        for i in range(1, len(history)):
            x1, y1 = history[i - 1]
            x2, y2 = history[i]
            total += math.hypot(x2 - x1, y2 - y1)
        x0, y0 = history[0]
        xn, yn = history[-1]
        displacement = math.hypot(xn - x0, yn - y0)
        if displacement < 1e-6:
            return total
        return total / displacement

    @staticmethod
    def _bbox_overlap(a: dict, b: dict) -> float:
        ax1, ay1 = a["x"], a["y"]
        ax2, ay2 = ax1 + a["width"], ay1 + a["height"]
        bx1, by1 = b["x"], b["y"]
        bx2, by2 = bx1 + b["width"], by1 + b["height"]
        ix1, iy1 = max(ax1, bx1), max(ay1, by1)
        ix2, iy2 = min(ax2, bx2), min(ay2, by2)
        if ix2 <= ix1 or iy2 <= iy1:
            return 0.0
        inter = (ix2 - ix1) * (iy2 - iy1)
        min_area = min(a["width"] * a["height"], b["width"] * b["height"])
        return inter / max(min_area, 1.0)

    @staticmethod
    def crossing_direction(
        prev: tuple[float, float],
        curr: tuple[float, float],
        start: dict[str, float],
        end: dict[str, float],
    ) -> str:
        lx = end["x"] - start["x"]
        ly = end["y"] - start["y"]
        mx = curr[0] - prev[0]
        my = curr[1] - prev[1]
        cross = lx * my - ly * mx
        return "in" if cross > 0 else "out"

    def record_line_cross(
        self,
        camera_id: str,
        line_id: str,
        track_id: int,
        direction: str,
        timestamp: float,
    ) -> None:
        key = (camera_id, line_id)
        history = self._crossing_history.setdefault(key, [])
        history.append(_LineCrossing(track_id, direction, timestamp))
        cutoff = timestamp - max(self.tailgate_window_seconds * 3, 10.0)
        self._crossing_history[key] = [c for c in history if c.timestamp >= cutoff]

    def evaluate_line_behaviors(
        self,
        camera_id: str,
        timestamp: float,
    ) -> list[BehaviorSignal]:
        signals: list[BehaviorSignal] = []
        for (cam, line_id), crossings in self._crossing_history.items():
            if cam != camera_id or not crossings:
                continue
            latest = crossings[-1]
            expected = self._line_expected.get((cam, line_id))
            if expected and latest.direction not in ("unknown", expected):
                signals.append(
                    BehaviorSignal(
                        latest.track_id,
                        BehaviorLabel.WRONG_WAY,
                        0.75,
                        {
                            "line_id": line_id,
                            "direction": latest.direction,
                            "expected_direction": expected,
                        },
                    )
                )
            recent = [
                c for c in crossings[:-1]
                if c.track_id != latest.track_id
                and timestamp - c.timestamp <= self.tailgate_window_seconds
            ]
            if recent:
                signals.append(
                    BehaviorSignal(
                        latest.track_id,
                        BehaviorLabel.TAILGATING,
                        0.7,
                        {
                            "line_id": line_id,
                            "preceding_track_id": recent[-1].track_id,
                            "gap_seconds": round(timestamp - recent[-1].timestamp, 2),
                        },
                    )
                )
        return signals

    def _posture_signal(
        self,
        track_id: int,
        bbox_history: list[dict],
    ) -> BehaviorSignal | None:
        first = bbox_history[0]
        last = bbox_history[-1]
        first_ratio = first["width"] / max(first["height"], 1)
        last_ratio = last["width"] / max(last["height"], 1)

        if last["width"] > first["width"] * 1.8 and last["height"] < first["height"] * 0.55:
            return BehaviorSignal(
                track_id, BehaviorLabel.FALLING, 0.8,
                {"aspect_ratio": round(last_ratio, 3)},
            )
        if last["height"] < first["height"] * 0.65 and last["y"] < first["y"]:
            return BehaviorSignal(
                track_id, BehaviorLabel.CLIMBING, 0.65,
                {"vertical_delta": round(first["y"] - last["y"], 1)},
            )
        if last_ratio > first_ratio * 1.25 and last["height"] < first["height"] * 0.75:
            return BehaviorSignal(
                track_id, BehaviorLabel.CROUCHING, 0.65,
                {"aspect_ratio": round(last_ratio, 3)},
            )
        return None

    def evaluate_track(
        self,
        track_id: int,
        history: list[tuple[float, float]],
        class_name: str,
        bbox: dict | None = None,
        bbox_history: list[dict] | None = None,
    ) -> BehaviorSignal:
        if bbox_history and len(bbox_history) >= 2 and class_name == "person":
            posture = self._posture_signal(track_id, bbox_history)
            if posture is not None:
                return posture

        if len(history) >= 4 and class_name == "person":
            ratio = self._path_ratio(history)
            if ratio >= self.wandering_path_ratio:
                return BehaviorSignal(track_id, BehaviorLabel.WANDERING, 0.6, {"path_ratio": round(ratio, 2)})

        speed = self._speed(history)
        if speed >= self.speed_threshold * 1.35 and class_name == "person":
            return BehaviorSignal(
                track_id, BehaviorLabel.RAPID_ACTIVITY, 0.72,
                {"speed": speed, "behavior": "rapid_activity"},
            )
        if speed >= self.speed_threshold and class_name == "person":
            return BehaviorSignal(track_id, BehaviorLabel.RUNNING, 0.7, {"speed": speed})
        return BehaviorSignal(track_id, BehaviorLabel.NORMAL, 0.9, {"speed": speed})

    def evaluate_fighting(self, persons: list[dict]) -> list[BehaviorSignal]:
        signals: list[BehaviorSignal] = []
        for i, a in enumerate(persons):
            for b in persons[i + 1:]:
                overlap = self._bbox_overlap(a["bbox"], b["bbox"])
                if overlap >= self.fight_overlap_ratio:
                    details = {"overlap_ratio": round(overlap, 3)}
                    signals.append(BehaviorSignal(a["track_id"], BehaviorLabel.FIGHTING, 0.75, details))
                    signals.append(BehaviorSignal(b["track_id"], BehaviorLabel.FIGHTING, 0.75, details))
        return signals

    def evaluate_carry(self, person: dict, tracks: list[dict]) -> BehaviorSignal | None:
        pb = person["bbox"]
        pcx = pb["x"] + pb["width"] / 2
        pcy = pb["y"] + pb["height"] / 2
        for obj in tracks:
            if obj["track_id"] == person["track_id"]:
                continue
            if obj.get("class_name") not in CARRY_OBJECT_CLASSES:
                continue
            ob = obj["bbox"]
            ocx = ob["x"] + ob["width"] / 2
            ocy = ob["y"] + ob["height"] / 2
            if math.hypot(ocx - pcx, ocy - pcy) <= self.carry_proximity:
                return BehaviorSignal(
                    person["track_id"],
                    BehaviorLabel.CARRYING,
                    0.7,
                    {"object_class": obj.get("class_name"), "object_track_id": obj["track_id"]},
                )
        return None

    def evaluate_queue(self, persons: list[dict]) -> list[BehaviorSignal]:
        if len(persons) < self.queue_min_persons:
            return []
        xs = [p["bbox"]["x"] + p["bbox"]["width"] / 2 for p in persons]
        ys = [p["bbox"]["y"] + p["bbox"]["height"] / 2 for p in persons]
        x_span = max(xs) - min(xs)
        y_span = max(ys) - min(ys)
        aligned = x_span <= self.queue_alignment_tolerance or y_span <= self.queue_alignment_tolerance
        if not aligned:
            return []
        return [
            BehaviorSignal(p["track_id"], BehaviorLabel.QUEUE_FORMING, 0.6, {"queue_size": len(persons)})
            for p in persons
        ]

    def evaluate_scene(
        self,
        centroids: list[tuple[int, tuple[float, float]]],
    ) -> list[BehaviorSignal]:
        signals: list[BehaviorSignal] = []
        if len(centroids) < self.crowding_min_tracks:
            return signals
        for i, (tid, (x, y)) in enumerate(centroids):
            neighbors = 0
            for j, (_, (ox, oy)) in enumerate(centroids):
                if i == j:
                    continue
                if math.hypot(x - ox, y - oy) <= self.crowding_radius:
                    neighbors += 1
            if neighbors >= self.crowding_min_tracks - 1:
                signals.append(
                    BehaviorSignal(tid, BehaviorLabel.CROWDING, 0.6, {"neighbor_count": neighbors})
                )
        return signals

    def evaluate_frame(
        self,
        tracks: list[dict],
        histories: dict[int, list[tuple[float, float]]],
        bbox_histories: dict[int, list[dict]],
    ) -> list[BehaviorSignal]:
        signals: list[BehaviorSignal] = []
        centroids: list[tuple[int, tuple[float, float]]] = []
        persons: list[dict] = []

        for track in tracks:
            tid = track["track_id"]
            hist = histories.get(tid, [])
            bbox_hist = bbox_histories.get(tid, [])
            sig = self.evaluate_track(
                tid,
                hist,
                track.get("class_name", "unknown"),
                track.get("bbox"),
                bbox_hist or None,
            )
            if sig.label != BehaviorLabel.NORMAL:
                signals.append(sig)

            bbox = track.get("bbox", {})
            centroids.append((tid, (bbox.get("x", 0) + bbox.get("width", 0) / 2, bbox.get("y", 0) + bbox.get("height", 0) / 2)))
            if track.get("class_name") == "person":
                persons.append(track)

        signals.extend(self.evaluate_scene(centroids))
        signals.extend(self.evaluate_fighting(persons))
        signals.extend(self.evaluate_queue(persons))
        for person in persons:
            carry = self.evaluate_carry(person, tracks)
            if carry is not None:
                signals.append(carry)
        return signals
