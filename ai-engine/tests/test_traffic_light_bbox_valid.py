"""Tests for red-light bbox validation and terminal evidence status helpers."""
from __future__ import annotations

from citevision_ai.road_enforcement.traffic_light import TrafficLightEngine


def test_reject_degenerate_pixel_bbox():
    assert TrafficLightEngine._valid_vehicle_bbox(
        {"x": 1116.0, "y": 350.0, "width": 1.0, "height": 39.0}, 1920, 1080,
    ) is False


def test_accept_normal_normalized_bbox():
    assert TrafficLightEngine._valid_vehicle_bbox(
        {"x": 0.78, "y": 0.35, "width": 0.05, "height": 0.06}, 1920, 1080,
    ) is True


def test_accept_normal_pixel_bbox():
    assert TrafficLightEngine._valid_vehicle_bbox(
        {"x": 800.0, "y": 400.0, "width": 120.0, "height": 80.0}, 1920, 1080,
    ) is True


def test_reject_tiny_normalized_area():
    assert TrafficLightEngine._valid_vehicle_bbox(
        {"x": 0.5, "y": 0.5, "width": 0.001, "height": 0.001}, 1920, 1080,
    ) is False
