from citevision_ai.behavior.heuristics import BehaviorHeuristics, BehaviorLabel


class TestBehaviorHeuristics:
    def test_running_detection(self):
        h = BehaviorHeuristics(speed_threshold=50.0)
        history = [(0, 0), (100, 0)]
        sig = h.evaluate_track(1, history, "person")
        assert sig.label == BehaviorLabel.RUNNING

    def test_normal_walking(self):
        h = BehaviorHeuristics(speed_threshold=200.0)
        history = [(0, 0), (5, 5)]
        sig = h.evaluate_track(1, history, "person")
        assert sig.label == BehaviorLabel.NORMAL
