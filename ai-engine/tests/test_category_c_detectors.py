from citevision_ai.behavior.heuristics import BehaviorHeuristics, BehaviorLabel
from citevision_ai.events.generator import EventGenerator


SQUARE_ZONE = [
    {"x": 0, "y": 0},
    {"x": 100, "y": 0},
    {"x": 100, "y": 100},
    {"x": 0, "y": 100},
]


class TestCategoryCHeuristics:
    def test_falling_detection(self):
        h = BehaviorHeuristics()
        bbox_history = [
            {"x": 10, "y": 10, "width": 20, "height": 60},
            {"x": 10, "y": 30, "width": 20, "height": 40},
            {"x": 10, "y": 50, "width": 70, "height": 25},
        ]
        sig = h.evaluate_track(
            1,
            [(20, 40), (20, 55), (45, 62)],
            "person",
            bbox=bbox_history[-1],
            bbox_history=bbox_history,
        )
        assert sig.label == BehaviorLabel.FALLING

    def test_fighting_detection(self):
        h = BehaviorHeuristics(fight_overlap_ratio=0.1)
        persons = [
            {
                "track_id": 1,
                "class_name": "person",
                "bbox": {"x": 10, "y": 10, "width": 40, "height": 80},
            },
            {
                "track_id": 2,
                "class_name": "person",
                "bbox": {"x": 30, "y": 20, "width": 40, "height": 80},
            },
        ]
        signals = h.evaluate_fighting(persons)
        assert len(signals) == 2
        assert all(s.label == BehaviorLabel.FIGHTING for s in signals)

    def test_wandering_detection(self):
        h = BehaviorHeuristics(wandering_path_ratio=2.0)
        history = [(0, 0), (10, 5), (5, 15), (15, 10), (8, 20), (12, 8)]
        sig = h.evaluate_track(3, history, "person")
        assert sig.label == BehaviorLabel.WANDERING

    def test_carry_detection(self):
        h = BehaviorHeuristics(carry_proximity=100.0)
        person = {
            "track_id": 1,
            "class_name": "person",
            "bbox": {"x": 10, "y": 10, "width": 30, "height": 80},
        }
        backpack = {
            "track_id": 2,
            "class_name": "backpack",
            "bbox": {"x": 25, "y": 40, "width": 20, "height": 30},
        }
        sig = h.evaluate_carry(person, [backpack])
        assert sig is not None
        assert sig.label == BehaviorLabel.CARRYING

    def test_queue_forming(self):
        h = BehaviorHeuristics(queue_min_persons=3, queue_alignment_tolerance=20.0)
        persons = [
            {"track_id": i, "class_name": "person", "bbox": {"x": 10, "y": y, "width": 20, "height": 60}}
            for i, y in enumerate([10, 40, 70], start=1)
        ]
        signals = h.evaluate_queue(persons)
        assert len(signals) == 3
        assert all(s.label == BehaviorLabel.QUEUE_FORMING for s in signals)


class TestCategoryCEventGenerator:
    def test_object_appeared_event(self):
        gen = EventGenerator()
        ts = "2026-06-12T12:00:00+00:00"
        tracks = [
            {"track_id": 42, "class_name": "backpack", "bbox": {"x": 10, "y": 10, "width": 20, "height": 30}},
        ]
        events = gen.process_frame("cam-1", tracks, [], ts)
        appeared = [e for e in events if e["event_type"] == "object_appeared"]
        assert len(appeared) == 1
        assert appeared[0]["track_id"] == 42
        assert appeared[0]["class_name"] == "backpack"

    def test_object_disappeared_event(self):
        gen = EventGenerator()
        ts = "2026-06-12T12:00:00+00:00"
        tracks = [
            {"track_id": 7, "class_name": "suitcase", "bbox": {"x": 5, "y": 5, "width": 25, "height": 35}},
        ]
        gen.process_frame("cam-1", tracks, [], ts)
        events = gen.process_frame("cam-1", [], [], "2026-06-12T12:00:01+00:00")
        disappeared = [e for e in events if e["event_type"] == "object_disappeared"]
        assert len(disappeared) == 1
        assert disappeared[0]["track_id"] == 7

    def test_zone_presence_event(self):
        gen = EventGenerator(presence_threshold_seconds=1.0)
        rules = [
            {
                "camera_id": "cam-1",
                "rule_type": "zone_presence",
                "enabled": True,
                "presence_seconds": 1.0,
                "zone": {"zone_id": "zone-a", "polygon": SQUARE_ZONE},
            }
        ]
        tracks = [
            {"track_id": 1, "class_name": "person", "bbox": {"x": 40, "y": 40, "width": 10, "height": 10}},
        ]
        gen.process_frame("cam-1", tracks, rules, "2026-06-12T12:00:00+00:00")
        events = gen.process_frame("cam-1", tracks, rules, "2026-06-12T12:00:02+00:00")
        presence = [e for e in events if e["event_type"] == "zone_presence"]
        assert len(presence) == 1
        assert presence[0]["zone_id"] == "zone-a"
        assert presence[0]["class_name"] == "person"

    def test_zone_enter_includes_class_name(self):
        gen = EventGenerator()
        rules = [
            {
                "camera_id": "cam-1",
                "rule_type": "zone",
                "enabled": True,
                "zone": {"zone_id": "zone-a", "polygon": SQUARE_ZONE},
            }
        ]
        tracks = [
            {"track_id": 2, "class_name": "car", "bbox": {"x": 40, "y": 40, "width": 10, "height": 10}},
        ]
        events = gen.process_frame("cam-1", tracks, rules, "2026-06-12T12:00:00+00:00")
        enters = [e for e in events if e["event_type"] == "zone_enter"]
        assert len(enters) == 1
        assert enters[0]["class_name"] == "car"

    def test_emit_behavior_signals_falling(self):
        gen = EventGenerator()
        h = BehaviorHeuristics()
        bbox_history = [
            {"x": 10, "y": 10, "width": 20, "height": 60},
            {"x": 10, "y": 30, "width": 20, "height": 40},
            {"x": 10, "y": 50, "width": 70, "height": 25},
        ]
        sig = h.evaluate_track(
            1,
            [(20, 40), (20, 55), (45, 62)],
            "person",
            bbox=bbox_history[-1],
            bbox_history=bbox_history,
        )
        events = gen.emit_behavior_signals("cam-1", [sig], "2026-06-12T12:00:00+00:00")
        assert events[0]["event_type"] == "falling"
        assert events[0]["severity"] == "critical"
