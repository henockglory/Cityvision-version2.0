"""Geometry helpers for zone edge calibration (real-world metres per polygon edge)."""
from __future__ import annotations

import math
from typing import Any


def _vertex(poly: list[dict], i: int) -> tuple[float, float]:
    p = poly[i]
    return float(p.get("x", 0)), float(p.get("y", 0))


def edge_count(poly: list[dict]) -> int:
    return len(poly) if len(poly) >= 3 else 0


def edge_pixel_length_norm(poly: list[dict], i: int) -> float:
    """Length of edge i → i+1 in normalized (0–1) image coordinates."""
    n = len(poly)
    if n < 2:
        return 0.0
    x1, y1 = _vertex(poly, i)
    x2, y2 = _vertex(poly, (i + 1) % n)
    return math.hypot(x2 - x1, y2 - y1)


def edge_distance_m(poly: list[dict], i: int, behavior_config: dict | None = None) -> float | None:
    """Real-world length (m) for edge i, from polygon point or behavior_config fallback."""
    if i < 0 or i >= len(poly):
        return None
    p = poly[i]
    raw = p.get("distance_to_next_m")
    if raw is None and behavior_config:
        edges = behavior_config.get("edge_distances_m")
        if isinstance(edges, list) and i < len(edges):
            raw = edges[i]
    try:
        v = float(raw)
        return v if v > 0 else None
    except (TypeError, ValueError):
        return None


def calibrated_edges(poly: list[dict], behavior_config: dict | None = None) -> list[tuple[int, float, float]]:
    """List of (edge_index, pixel_len_norm, metres) for calibrated edges only."""
    n = edge_count(poly)
    out: list[tuple[int, float, float]] = []
    for i in range(n):
        px = edge_pixel_length_norm(poly, i)
        m = edge_distance_m(poly, i, behavior_config)
        if m is not None and px > 1e-9:
            out.append((i, px, m))
    return out


def meters_per_norm_unit(poly: list[dict], behavior_config: dict | None = None) -> float | None:
    """Average scale (metres per unit normalized distance) from calibrated edges."""
    edges = calibrated_edges(poly, behavior_config)
    if not edges:
        return None
    total_m = sum(m for _, _, m in edges)
    total_px = sum(px for _, px, _ in edges)
    if total_px <= 0:
        return None
    return total_m / total_px


def norm_distance(x1: float, y1: float, x2: float, y2: float) -> float:
    return math.hypot(x2 - x1, y2 - y1)


def path_distance_m(
    entry_xy: tuple[float, float],
    exit_xy: tuple[float, float],
    poly: list[dict],
    behavior_config: dict | None = None,
) -> float | None:
    """Convert centroid entry→exit path to metres using edge calibration."""
    scale = meters_per_norm_unit(poly, behavior_config)
    if scale is None:
        return None
    d_norm = norm_distance(entry_xy[0], entry_xy[1], exit_xy[0], exit_xy[1])
    if d_norm <= 1e-9:
        return None
    return d_norm * scale


def perimeter_m(poly: list[dict], behavior_config: dict | None = None) -> float | None:
    edges = calibrated_edges(poly, behavior_config)
    if len(edges) != edge_count(poly):
        return None
    return sum(m for _, _, m in edges)


def effective_travel_distance_m(poly: list[dict], behavior_config: dict | None = None) -> float | None:
    """Best estimate of travel distance through zone when path endpoints unknown.

    Uses the longest calibrated edge (typical road direction) or explicit distance_m.
    """
    cfg = behavior_config or {}
    try:
        explicit = float(cfg.get("distance_m", 0) or 0)
    except (TypeError, ValueError):
        explicit = 0.0

    edges = calibrated_edges(poly, behavior_config)
    if edges:
        # Longest calibrated edge ≈ direction of travel for strip-shaped zones.
        return max(m for _, _, m in edges)

    if explicit > 0:
        return explicit
    return None


def has_edge_calibration(poly: list[dict], behavior_config: dict | None = None) -> bool:
    n = edge_count(poly)
    if n == 0:
        return False
    calibrated = calibrated_edges(poly, behavior_config)
    return len(calibrated) >= max(2, n // 2)


def edge_midpoint(poly: list[dict], i: int) -> tuple[float, float] | None:
    n = edge_count(poly)
    if i < 0 or i >= n:
        return None
    x1, y1 = _vertex(poly, i)
    x2, y2 = _vertex(poly, (i + 1) % n)
    return (x1 + x2) / 2.0, (y1 + y2) / 2.0


def edge_pair_distance_m(
    poly: list[dict],
    entry_edge_index: int,
    exit_edge_index: int,
    behavior_config: dict | None = None,
) -> float | None:
    """Sum calibrated edge lengths along the polygon from entry edge to exit edge (clockwise)."""
    n = edge_count(poly)
    if n < 3 or entry_edge_index < 0 or exit_edge_index < 0:
        return None
    if entry_edge_index >= n or exit_edge_index >= n:
        return None
    total = 0.0
    i = entry_edge_index
    for _ in range(n + 1):
        metres = edge_distance_m(poly, i, behavior_config)
        if metres is None or metres <= 0:
            return None
        total += metres
        if i == exit_edge_index:
            return total
        i = (i + 1) % n
        if i == entry_edge_index:
            break
    return None


def resolve_speed_distance_m(
    poly: list[dict],
    behavior_config: dict | None,
    entry_xy: tuple[float, float] | None,
    exit_xy: tuple[float, float] | None,
) -> tuple[float | None, str]:
    """Return (distance_metres, method) for speed = distance / time."""
    cfg = behavior_config or {}

    try:
        entry_edge = cfg.get("entry_edge_index")
        exit_edge = cfg.get("exit_edge_index")
        if entry_edge is not None and exit_edge is not None:
            pair_m = edge_pair_distance_m(poly, int(entry_edge), int(exit_edge), cfg)
            if pair_m is not None and pair_m > 0:
                return pair_m, "edge_pair_timing"
    except (TypeError, ValueError):
        pass

    if entry_xy and exit_xy:
        path_m = path_distance_m(entry_xy, exit_xy, poly, cfg)
        eff = effective_travel_distance_m(poly, cfg)
        if path_m is not None and path_m > 0:
            # Large demo zones: tiny centroid drift understates speed — use strip length.
            if eff is not None and eff > 0 and path_m < eff * 0.25:
                return eff, "edge_longest_timing"
            return path_m, "edge_path_timing"

    if has_edge_calibration(poly, cfg):
        eff = effective_travel_distance_m(poly, cfg)
        if eff is not None and eff > 0:
            return eff, "edge_longest_timing"

    try:
        explicit = float(cfg.get("distance_m", 0) or 0)
    except (TypeError, ValueError):
        explicit = 0.0
    if explicit > 0:
        return explicit, "zone_distance_timing"

    return None, "unconfigured"
