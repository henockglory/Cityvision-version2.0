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


def nearest_edge_index(poly: list[dict], x: float, y: float) -> int | None:
    """Index of the polygon edge whose midpoint is closest to (x, y) in norm coords."""
    n = edge_count(poly)
    if n < 3:
        return None
    best_i: int | None = None
    best_d = float("inf")
    for i in range(n):
        mid = edge_midpoint(poly, i)
        if mid is None:
            continue
        d = math.hypot(x - mid[0], y - mid[1])
        if d < best_d:
            best_d = d
            best_i = i
    return best_i


def point_to_edge_distance(poly: list[dict], i: int, x: float, y: float) -> float:
    """Distance from (x, y) to polygon edge i (segment, not midpoint)."""
    n = edge_count(poly)
    if i < 0 or i >= n:
        return float("inf")
    ax, ay = _vertex(poly, i)
    bx, by = _vertex(poly, (i + 1) % n)
    vx, vy = bx - ax, by - ay
    len2 = vx * vx + vy * vy
    if len2 <= 1e-18:
        return math.hypot(x - ax, y - ay)
    t = max(0.0, min(1.0, ((x - ax) * vx + (y - ay) * vy) / len2))
    return math.hypot(x - (ax + t * vx), y - (ay + t * vy))


def nearest_edge_if_close(
    poly: list[dict],
    x: float,
    y: float,
    *,
    max_dist: float = 0.08,
) -> int | None:
    """Edge index only when (x, y) is actually next to that edge — not merely nearest.

    Using 'nearest of 4' on a car already inside the zone tags the wrong neighbour
    when two vehicles sit side by side.
    """
    n = edge_count(poly)
    if n < 3:
        return None
    best_i: int | None = None
    best_d = float("inf")
    for i in range(n):
        d = point_to_edge_distance(poly, i, x, y)
        if d < best_d:
            best_d = d
            best_i = i
    if best_i is None or best_d > max_dist:
        return None
    return best_i


def _ccw(ax: float, ay: float, bx: float, by: float, cx: float, cy: float) -> float:
    return (cy - ay) * (bx - ax) - (cx - ax) * (by - ay)


def _point_on_segment(
    ax: float, ay: float, bx: float, by: float, px: float, py: float, *, eps: float = 1e-9
) -> bool:
    if abs(_ccw(ax, ay, bx, by, px, py)) > eps:
        return False
    return (
        min(ax, bx) - eps <= px <= max(ax, bx) + eps
        and min(ay, by) - eps <= py <= max(ay, by) + eps
    )


def segments_intersect(
    a: tuple[float, float],
    b: tuple[float, float],
    c: tuple[float, float],
    d: tuple[float, float],
    *,
    eps: float = 1e-9,
) -> bool:
    """True if ab and cd share a point (proper cross or endpoint on the other segment)."""
    ax, ay = a
    bx, by = b
    cx, cy = c
    dx, dy = d
    o1 = _ccw(ax, ay, bx, by, cx, cy)
    o2 = _ccw(ax, ay, bx, by, dx, dy)
    o3 = _ccw(cx, cy, dx, dy, ax, ay)
    o4 = _ccw(cx, cy, dx, dy, bx, by)
    if (o1 * o2 < -eps) and (o3 * o4 < -eps):
        return True
    if abs(o1) <= eps and _point_on_segment(ax, ay, bx, by, cx, cy, eps=eps):
        return True
    if abs(o2) <= eps and _point_on_segment(ax, ay, bx, by, dx, dy, eps=eps):
        return True
    if abs(o3) <= eps and _point_on_segment(cx, cy, dx, dy, ax, ay, eps=eps):
        return True
    if abs(o4) <= eps and _point_on_segment(cx, cy, dx, dy, bx, by, eps=eps):
        return True
    return False


def _segment_intersection_t(
    a: tuple[float, float],
    b: tuple[float, float],
    c: tuple[float, float],
    d: tuple[float, float],
) -> float:
    """Parametric t of ab at the intersection with cd (0 at a, 1 at b)."""
    ax, ay = a
    bx, by = b
    cx, cy = c
    dx, dy = d
    den = (bx - ax) * (dy - cy) - (by - ay) * (dx - cx)
    if abs(den) < 1e-15:
        vx, vy = bx - ax, by - ay
        denom = vx * vx + vy * vy
        if denom <= 1e-18:
            return 0.0

        def t_of(px: float, py: float) -> float:
            return ((px - ax) * vx + (py - ay) * vy) / denom

        return min(t_of(cx, cy), t_of(dx, dy))
    return ((cx - ax) * (dy - cy) - (cy - ay) * (dx - cx)) / den


def edges_crossed_by_segment(
    poly: list[dict],
    x1: float,
    y1: float,
    x2: float,
    y2: float,
) -> list[int]:
    """Polygon edge indices crossed by (x1,y1)→(x2,y2), ordered along the trajectory."""
    n = edge_count(poly)
    if n < 3:
        return []
    a = (x1, y1)
    b = (x2, y2)
    if math.hypot(x2 - x1, y2 - y1) <= 1e-12:
        return []
    hits: list[tuple[float, int]] = []
    for i in range(n):
        c = _vertex(poly, i)
        d = _vertex(poly, (i + 1) % n)
        if segments_intersect(a, b, c, d):
            hits.append((_segment_intersection_t(a, b, c, d), i))
    hits.sort(key=lambda item: item[0])
    return [i for _, i in hits]


def append_edge_crossing(crossed: list[int], edge: int | None) -> None:
    """Append an edge index if it is new relative to the last recorded crossing."""
    if edge is None:
        return
    if not crossed or crossed[-1] != edge:
        crossed.append(int(edge))


def is_wrong_way_ordered(
    crossed: list[int],
    entry_edge_index: int,
    exit_edge_index: int,
) -> bool:
    """Wrong-way iff exit edge (P3-P4) is first seen before entry edge (P1-P2).

    Other edges between the two do not cancel. Missing either edge is not wrong-way.
    """
    try:
        i_exit = crossed.index(int(exit_edge_index))
        i_entry = crossed.index(int(entry_edge_index))
    except ValueError:
        return False
    return i_exit < i_entry


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
