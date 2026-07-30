#!/usr/bin/env python3
"""Phase 1: purge 18 polluting event_types from shared catalog JSON files."""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SHARED = ROOT / "shared"

PURGED = {
    "phone_driving",
    "fighting",
    "falling",
    "fight_detected",
    "traffic_light_state",
    "behavior_anomaly",
    "running",
    "crowd_panic",
    "crowd_gathering",
    "queue_forming",
    "erratic_motion",
    "wandering",
    "rapid_activity",
    "tailgating",
    "carry_detected",
    "climb_detected",
    "crouch_detected",
    "object_appeared",
}

# Templates whose primary event is purged — remove or redirect
PURGED_TEMPLATES = {
    "tpl-fighting",
    "tpl-fight",
    "tpl-falling",
    "tpl-running",
    "tpl-running-person",
    "tpl-crowd-panic",
    "tpl-crowd-gathering",
    "tpl-group-formation",
    "tpl-queue-forming",
    "tpl-erratic-motion",
    "tpl-wandering",
    "tpl-tailgating",
    "tpl-carry-object",
    "tpl-climb-detected",
    "tpl-crouch-detected",
    "tpl-behavior-anomaly",
    "tpl-object-appeared",
    "tpl-vandalism",  # tied to crowd_gathering / rapid_activity heuristics
}

# Redirect object-appeared style presence to zone_enter if we keep a stub — we remove instead.


def load(p: Path):
    return json.loads(p.read_text(encoding="utf-8"))


def save(p: Path, data) -> None:
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"  wrote {p.relative_to(ROOT)}")


def purge_event_types_dict(d: dict) -> int:
    removed = 0
    for k in list(d.keys()):
        if k in PURGED:
            del d[k]
            removed += 1
    return removed


def walk_remove_templates(obj, removed: list[str]):
    """Remove dict entries / list items keyed by purged template ids."""
    if isinstance(obj, dict):
        for k in list(obj.keys()):
            if k in PURGED_TEMPLATES:
                del obj[k]
                removed.append(k)
            else:
                walk_remove_templates(obj[k], removed)
    elif isinstance(obj, list):
        keep = []
        for item in obj:
            if isinstance(item, dict):
                tid = item.get("id") or item.get("template_id") or item.get("tpl")
                if tid in PURGED_TEMPLATES:
                    removed.append(str(tid))
                    continue
                # redirects
                if item.get("redirect_to") in PURGED_TEMPLATES or item.get("redirect") in PURGED_TEMPLATES:
                    removed.append(str(tid or item))
                    continue
                cap = item.get("capability_id") or item.get("event_type")
                if cap in PURGED:
                    removed.append(str(tid or cap))
                    continue
                walk_remove_templates(item, removed)
                keep.append(item)
            elif isinstance(item, str) and (item in PURGED or item in PURGED_TEMPLATES):
                removed.append(item)
            else:
                if isinstance(item, (dict, list)):
                    walk_remove_templates(item, removed)
                keep.append(item)
        obj[:] = keep


def main() -> None:
    print("=== Phase 1 catalog purge ===")

    # --- ai-capabilities.json ---
    cap_path = SHARED / "ai-capabilities.json"
    cap = load(cap_path)
    n = 0
    if isinstance(cap.get("event_types"), dict):
        n += purge_event_types_dict(cap["event_types"])
    # capabilities array / object
    for key in ("capabilities", "templates", "behaviors", "zone_behaviors"):
        if key not in cap:
            continue
    removed_tpl: list[str] = []
    walk_remove_templates(cap, removed_tpl)
    # Also strip capability entries whose capability_id is purged
    if isinstance(cap.get("capabilities"), list):
        before = len(cap["capabilities"])
        cap["capabilities"] = [
            c
            for c in cap["capabilities"]
            if not (
                isinstance(c, dict)
                and (
                    c.get("capability_id") in PURGED
                    or c.get("id") in PURGED_TEMPLATES
                    or c.get("event_type") in PURGED
                )
            )
        ]
        print(f"  capabilities list: {before} -> {len(cap['capabilities'])}")
    elif isinstance(cap.get("capabilities"), dict):
        for k in list(cap["capabilities"].keys()):
            if k in PURGED or k in PURGED_TEMPLATES:
                del cap["capabilities"][k]
                n += 1
    save(cap_path, cap)
    print(f"  event_types removed: {n}, template walks: {len(removed_tpl)}")

    # --- event-labels ---
    labels_path = SHARED / "event-labels.fr.json"
    if labels_path.is_file():
        labels = load(labels_path)
        if isinstance(labels, dict):
            # sometimes nested under event_types
            target = labels.get("event_types", labels)
            if isinstance(target, dict):
                r = purge_event_types_dict(target)
                print(f"  event-labels removed: {r}")
            save(labels_path, labels)

    # --- catalog-navigation ---
    nav_path = SHARED / "catalog-navigation.json"
    if nav_path.is_file():
        nav = load(nav_path)
        rem: list[str] = []
        walk_remove_templates(nav, rem)
        save(nav_path, nav)
        print(f"  catalog-navigation removed refs: {len(rem)}")

    # --- rule-capability-matrix ---
    mtx_path = SHARED / "rule-capability-matrix.json"
    if mtx_path.is_file():
        mtx = load(mtx_path)
        rem = []
        walk_remove_templates(mtx, rem)
        if isinstance(mtx, dict):
            for k in list(mtx.keys()):
                if k in PURGED or k in PURGED_TEMPLATES:
                    del mtx[k]
        save(mtx_path, mtx)
        print(f"  rule-capability-matrix cleaned")

    # --- rule-catalog/*.json ---
    cat_dir = SHARED / "rule-catalog"
    for p in sorted(cat_dir.glob("*.json")):
        data = load(p)
        rem = []
        # Handle common shapes: { "templates": [...] } or list or dict by id
        if isinstance(data, dict) and "templates" in data:
            walk_remove_templates(data["templates"], rem)
            # Also rewrite tpl-object-appeared if still present as redirect — already removed
        elif isinstance(data, list):
            walk_remove_templates(data, rem)
        else:
            walk_remove_templates(data, rem)
        # Redirect: if any template used object_appeared as condition, already removed
        # Special: presence-motion may have tpl-object-appeared — gone
        save(p, data)
        if rem:
            print(f"  {p.name}: removed {rem}")

    # --- zone-behaviors: keep traffic_light_color zone behavior but note state event purged ---
    zb = SHARED / "zone-behaviors.json"
    if zb.is_file():
        zb_data = load(zb)
        # Do not remove red_light_observation / traffic_light_color behaviors — only the event_type
        save(zb, zb_data)
        print("  zone-behaviors: kept (behaviors unchanged)")

    print("DONE phase1 shared purge")


if __name__ == "__main__":
    main()
