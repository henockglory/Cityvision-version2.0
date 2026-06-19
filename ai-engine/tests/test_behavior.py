from citevision_ai.behavior.heuristics import BehaviorHeuristics, BehaviorLabel


class TestBehaviorHeuristics:
    def test_running_detection(self):
        # Speed 60 >= threshold 50 but < threshold*1.35=67.5 → RUNNING (not RAPID_ACTIVITY)
        h = BehaviorHeuristics(speed_threshold=50.0)
        history = [(0, 0), (60, 0)]
        sig = h.evaluate_track(1, history, "person")
        assert sig.label == BehaviorLabel.RUNNING

    def test_rapid_activity_detection(self):
        # Speed 100 >= threshold*1.35=67.5 → RAPID_ACTIVITY (also emits event_type='running')
        h = BehaviorHeuristics(speed_threshold=50.0)
        history = [(0, 0), (100, 0)]
        sig = h.evaluate_track(1, history, "person")
        assert sig.label == BehaviorLabel.RAPID_ACTIVITY

    def test_normal_walking(self):
        h = BehaviorHeuristics(speed_threshold=200.0)
        history = [(0, 0), (5, 5)]
        sig = h.evaluate_track(1, history, "person")
        assert sig.label == BehaviorLabel.NORMAL

    def test_tailgating_detection(self):
        h = BehaviorHeuristics(tailgate_window_seconds=2.0)
        h.record_line_cross("cam1", "entry", 1, "in", 10.0)
        h.record_line_cross("cam1", "entry", 2, "in", 10.5)
        signals = h.evaluate_line_behaviors("cam1", 10.5)
        assert any(s.label == BehaviorLabel.TAILGATING for s in signals)

    def test_wrong_way_detection(self):
        h = BehaviorHeuristics()
        h.set_line_config("cam1", "lane", {"x": 0, "y": 0}, {"x": 100, "y": 0}, "in")
        h.record_line_cross("cam1", "lane", 3, "out", 5.0)
        signals = h.evaluate_line_behaviors("cam1", 5.0)
        assert any(s.label == BehaviorLabel.WRONG_WAY for s in signals)

    def test_crouch_detection(self):
        h = BehaviorHeuristics()
        bbox_history = [
            {"x": 10, "y": 10, "width": 25, "height": 80},
            {"x": 10, "y": 12, "width": 26, "height": 78},
            {"x": 10, "y": 30, "width": 42, "height": 45},
        ]
        sig = h.evaluate_track(
            1,
            [(22, 50), (23, 52), (24, 54)],
            "person",
            bbox=bbox_history[-1],
            bbox_history=bbox_history,
        )
        assert sig.label == BehaviorLabel.CROUCHING
