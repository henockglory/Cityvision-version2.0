from citevision_ai.analytics.calibration import CalibrationEngine


def test_sudden_stop_emitted_on_rapid_deceleration():
    cal = CalibrationEngine({"world_scale": 0.05, "speed_limit_kmh": 80, "min_speed_kmh": 5})
    cam, tid = "cam-1", 7
    t0 = 1000.0
    # Simulate fast movement then halt within one frame step
    r1 = cal.update_track(cam, tid, 0, 0, t0, "car")
    r2 = cal.update_track(cam, tid, 200, 0, t0 + 0.5, "car")
    assert r2.get("speed_kmh", 0) > 20
    r3 = cal.update_track(cam, tid, 200, 0, t0 + 0.6, "car")
    assert r3.get("speed_event") == "sudden_stop"
