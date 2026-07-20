"""Traffic-light HSV gate: reject green glare / weak red as red."""

from __future__ import annotations

import numpy as np

from citevision_ai.road_enforcement.traffic_light import classify_light_color


def _solid_bgr(b: int, g: int, r: int, size: int = 40) -> np.ndarray:
    img = np.zeros((size, size, 3), dtype=np.uint8)
    img[:, :] = (b, g, r)
    return img


def test_classify_green_not_red():
    state, ratios = classify_light_color(_solid_bgr(40, 220, 40))
    assert state == "green", (state, ratios)
    assert ratios["green"] > ratios["red"]


def test_classify_red_dominates():
    state, ratios = classify_light_color(_solid_bgr(40, 40, 220))
    assert state == "red", (state, ratios)
    assert ratios["red"] > ratios["green"]


def test_classify_weak_red_with_green_spill_becomes_green():
    # Mostly green with a thin red fringe — must not report red.
    img = _solid_bgr(40, 200, 40)
    img[:4, :, :] = (30, 30, 200)
    state, ratios = classify_light_color(img)
    assert state != "red", (state, ratios)


def test_no_prefer_red_bias_on_mixed_green():
    # Green dominant with moderate red channel — old "prefer red" would fire.
    img = _solid_bgr(40, 200, 40)
    img[10:20, 10:20, :] = (30, 30, 180)
    state, ratios = classify_light_color(img)
    assert state != "red", (state, ratios)
