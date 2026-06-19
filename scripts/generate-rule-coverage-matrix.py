#!/usr/bin/env python3
"""Generate exhaustive rule coverage matrix: catalog × capabilities × AI engine × E2E."""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CATALOG_DIR = ROOT / "shared" / "rule-catalog"
CAPABILITIES_PATH = ROOT / "shared" / "ai-capabilities.json"
SCRIPTS_DIR = ROOT / "scripts"
OUT_JSON = ROOT / "docs" / "RULE-COVERAGE-MATRIX.json"
OUT_MD = ROOT / "docs" / "RULE-COVERAGE-MATRIX.md"

# Events emitted by AI engine (verified from source, 2026-06).
AI_EMITTED: dict[str, dict] = {
    "zone_enter": {"source": "events/generator.py", "requires": ["yolo"]},
    "zone_exit": {"source": "events/generator.py", "requires": ["yolo"]},
    "zone_presence": {"source": "events/generator.py", "requires": ["yolo"]},
    "zone_absence": {"source": "events/generator.py", "requires": ["yolo"]},
    "line_cross": {"source": "events/generator.py", "requires": ["yolo"]},
    "loitering": {"source": "events/generator.py", "requires": ["yolo"]},
    "dwell_time_exceeded": {"source": "analytics/state.py", "requires": ["yolo"]},
    "object_appeared": {"source": "events/generator.py", "requires": ["yolo"]},
    "object_disappeared": {"source": "events/generator.py", "requires": ["yolo"]},
    "object_abandoned": {"source": "analytics/abandoned.py", "requires": ["yolo"]},
    "object_removed": {"source": "analytics/abandoned.py", "requires": ["yolo"]},
    "running": {"source": "behavior/heuristics.py", "requires": ["yolo"]},
    "crowd_gathering": {"source": "behavior/heuristics.py", "requires": ["yolo"]},
    "tailgating": {"source": "behavior/heuristics.py", "requires": ["yolo"]},
    "wrong_way": {"source": "behavior/heuristics.py", "requires": ["yolo"]},
    "falling": {"source": "behavior/heuristics.py", "requires": ["yolo"]},
    "fighting": {"source": "behavior/heuristics.py", "requires": ["yolo"]},
    "queue_forming": {"source": "behavior/heuristics.py", "requires": ["yolo"]},
    "erratic_motion": {"source": "behavior/heuristics.py", "requires": ["yolo"]},
    "wandering": {"source": "behavior/heuristics.py", "requires": ["yolo"]},
    "crouch_detected": {"source": "behavior/heuristics.py", "requires": ["yolo"]},
    "climb_detected": {"source": "behavior/heuristics.py", "requires": ["yolo"]},
    "carry_detected": {"source": "behavior/heuristics.py", "requires": ["yolo"]},
    "person_stopped": {"source": "analytics/state.py", "requires": ["yolo"]},
    "vehicle_stopped": {"source": "analytics/state.py", "requires": ["yolo"]},
    "scene_density_high": {"source": "analytics/scene.py", "requires": ["yolo"]},
    "crowd_count_threshold": {"source": "analytics/scene.py", "requires": ["yolo"]},
    "vehicle_count_threshold": {"source": "analytics/scene.py", "requires": ["yolo"]},
    "person_vehicle_proximity": {"source": "analytics/scene_correlation.py", "requires": ["yolo"]},
    "multiple_persons_one_vehicle": {"source": "analytics/scene_correlation.py", "requires": ["yolo"]},
    "loitering_near_entrance": {"source": "analytics/scene_correlation.py", "requires": ["yolo"]},
    "speeding": {"source": "analytics/calibration.py", "requires": ["yolo", "calibration"]},
    "speed_below_minimum": {"source": "analytics/calibration.py", "requires": ["yolo", "calibration"]},
    "vehicle_corridor": {"source": "pipeline.py", "requires": ["yolo", "paddleocr", "calibration"]},
    "video_blur": {"source": "pipeline.py", "requires": ["opencv"]},
    "video_darkness": {"source": "pipeline.py", "requires": ["opencv"]},
    "face_detected": {"source": "identity/face.py", "requires": ["insightface"]},
    "face_watchlist_match": {"source": "identity/face.py", "requires": ["insightface"]},
    "face_unknown": {"source": "identity/face.py", "requires": ["insightface"]},
    "plate_detected": {"source": "identity/plate.py", "requires": ["paddleocr"]},
    "plate_blocked": {"source": "identity/plate.py", "requires": ["paddleocr"]},
    "plate_unknown": {"source": "identity/plate.py", "requires": ["paddleocr"]},
    "plate_allowed": {"source": "identity/plate.py", "requires": ["paddleocr"]},
    "correlation_match": {"source": "analytics/correlation.py", "requires": ["yolo"]},
    "behavior_anomaly": {"source": "events/generator.py", "requires": ["yolo"]},
    "perimeter_breach": {"source": "events/generator.py", "requires": ["yolo"]},
    "unauthorized_exit": {"source": "events/generator.py", "requires": ["yolo"]},
    "sudden_stop": {"source": "analytics/calibration.py", "requires": ["yolo", "calibration"]},
    "crowd_panic": {"source": "analytics/scene.py", "requires": ["yolo"]},
    "fight_detected": {"source": "events/generator.py", "requires": ["yolo"]},
    "rapid_activity": {"source": "behavior/heuristics.py", "requires": ["yolo"]},
    "red_light_violation": {"source": "road_enforcement/detector.py", "requires": ["yolo", "opencv"]},
    "seatbelt_violation": {"source": "road_enforcement/detector.py", "requires": ["yolo", "opencv"]},
    "phone_driving": {"source": "road_enforcement/detector.py", "requires": ["yolo", "opencv"]},
}

# Catalog event → canonical AI event when names differ.
EVENT_ALIASES: dict[str, str] = {
    "wrong_direction": "wrong_way",
}

# Explicitly not emitted (stub or future ML).
NOT_EMITTED: dict[str, str] = {
    "wrong_direction": "IA émet wrong_way, pas wrong_direction",
    "stationary": "métadonnée behavior, pas event_type",
    "watchlist": "pas un event_type",
    "restricted": "zone_id, pas event_type",
}

# Catalog stubs (coming_soon / supported:false in catalog JSON).
CATALOG_STUBS: set[str] = set()

# Scripts that prove the full live chain: video → MQTT → alert (NOT just pytest unit tests).
E2E_LIVE_SCRIPTS: set[str] = {
    "verify-e2e-zone-alert.sh",
    "verify-e2e-family-spatial.sh",
    "verify-e2e-family-identity.sh",
    "verify-e2e-family-road.sh",
    "verify-e2e-sequence-theft.sh",
    "verify-e2e-spatial-semantic.sh",
    "verify-e2e-webhook-cloudevents.sh",
    "verify-e2e-webhook-live.sh",
}

# Scripts that rely on pytest unit tests (fallback, don't prove the live chain).
E2E_PYTEST_FALLBACK_SCRIPTS: set[str] = {
    "verify-e2e-pytest-catalog.sh",
    "verify-e2e-event-matrix.sh",
    "verify-e2e-bientot-templates.sh",
}

# E2E scripts mapped to template ids (expand as tests are added).
E2E_SCRIPTS: dict[str, str] = {
    "tpl-zone-presence": "verify-e2e-zone-alert.sh",
    "tpl-zone-enter": "verify-e2e-family-spatial.sh",
    "tpl-perimeter-breach": "verify-e2e-family-spatial.sh",
    "tpl-line-cross-bidir": "verify-e2e-family-spatial.sh",
    "tpl-fighting": "verify-e2e-family-spatial.sh",
    "tpl-running-person": "verify-e2e-family-identity.sh",
    "tpl-face-detected": "verify-e2e-family-identity.sh",
    "tpl-plate-detected": "verify-e2e-family-identity.sh",
    "tpl-vehicle-stopped": "verify-e2e-family-road.sh",
    "tpl-congestion": "verify-e2e-family-road.sh",
    "tpl-sudden-stop": "verify-e2e-family-road.sh",
    "tpl-theft-composite": "verify-e2e-sequence-theft.sh",
    # Vitrine démo — règles spatiales supplémentaires
    "tpl-loitering": "verify-e2e-family-spatial.sh",
    "tpl-crowd-gathering": "verify-e2e-family-spatial.sh",
    "tpl-tailgating": "verify-e2e-family-spatial.sh",
    "tpl-wrong-way": "verify-e2e-family-spatial.sh",
    # Webhook live test
    "tpl-alert-webhook": "verify-e2e-webhook-live.sh",
    # Vitrine démo — identité/comportement supplémentaires
    "tpl-abandoned-object": "verify-e2e-family-identity.sh",
    "tpl-wandering": "verify-e2e-family-identity.sh",
    "tpl-intrusion": "verify-e2e-family-spatial.sh",
    "tpl-industrial-intrusion": "verify-e2e-family-spatial.sh",
    "tpl-zone-exit": "verify-e2e-family-spatial.sh",
    "tpl-line-cross-entry": "verify-e2e-family-spatial.sh",
    "tpl-accident": "verify-e2e-bientot-templates.sh",
    "tpl-vandalism": "verify-e2e-bientot-templates.sh",
    "tpl-crowd-panic": "verify-e2e-bientot-templates.sh",
    "tpl-fight": "verify-e2e-bientot-templates.sh",
    "tpl-red-light": "verify-e2e-bientot-templates.sh",
    "tpl-seatbelt": "verify-e2e-bientot-templates.sh",
    "tpl-phone-driving": "verify-e2e-bientot-templates.sh",
    "tpl-illegal-parking": "verify-e2e-bientot-templates.sh",
    "tpl-multi-zone": "verify-e2e-bientot-templates.sh",
}

E2E_EVENT_COVERAGE: dict[str, str] = {
    "zone_presence": "verify-e2e-zone-alert.sh",
    "zone_enter": "verify-e2e-family-spatial.sh",
    "perimeter_breach": "verify-e2e-family-spatial.sh",
    "line_cross": "verify-e2e-family-spatial.sh",
    "fighting": "verify-e2e-family-spatial.sh",
    "running": "verify-e2e-family-identity.sh",
    "face_detected": "verify-e2e-family-identity.sh",
    "plate_detected": "verify-e2e-family-identity.sh",
    "vehicle_stopped": "verify-e2e-family-road.sh",
    "vehicle_count_threshold": "verify-e2e-family-road.sh",
    "sudden_stop": "verify-e2e-family-road.sh",
    "unauthorized_exit": "verify-e2e-spatial-semantic.sh",
    "crowd_panic": "verify-e2e-bientot-templates.sh",
    "fight_detected": "verify-e2e-bientot-templates.sh",
    "red_light_violation": "verify-e2e-bientot-templates.sh",
    "seatbelt_violation": "verify-e2e-bientot-templates.sh",
    "phone_driving": "verify-e2e-bientot-templates.sh",
}


def load_catalog() -> dict[str, dict]:
    """Load unique templates by id (first occurrence wins, track source files)."""
    templates: dict[str, dict] = {}
    for path in sorted(CATALOG_DIR.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            continue
        for item in data:
            tid = item.get("id")
            if not tid:
                continue
            if tid not in templates:
                templates[tid] = {
                    **item,
                    "_catalog_files": [path.name],
                }
            else:
                templates[tid]["_catalog_files"].append(path.name)
    return templates


def extract_primary_event(definition: dict | None) -> str | None:
    if not definition:
        return None

    def walk(node) -> str | None:
        if not isinstance(node, dict):
            return None
        op = node.get("op")
        field = node.get("field")
        if op == "eq" and field in ("event", "event_type"):
            v = node.get("value")
            return str(v) if v is not None else None
        if op == "SEQUENCE":
            for child in node.get("children") or []:
                ev = walk(child)
                if ev:
                    return ev
        for child in node.get("children") or []:
            ev = walk(child)
            if ev:
                return ev
        return None

    cond = definition.get("condition")
    if cond:
        ev = walk(cond)
        if ev:
            return ev
    pipeline = definition.get("pipeline") or {}
    trigger = pipeline.get("trigger") or {}
    if trigger.get("event_type"):
        return str(trigger["event_type"])
    return None


def extract_all_events(definition: dict | None) -> list[str]:
    if not definition:
        return []
    found: list[str] = []

    def walk(node) -> None:
        if isinstance(node, dict):
            if node.get("field") in ("event", "event_type") and node.get("value"):
                found.append(str(node["value"]))
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for x in node:
                walk(x)

    walk(definition.get("condition"))
    walk(definition.get("pipeline"))
    return list(dict.fromkeys(found))


def has_config_schema(cap_entry: dict | None) -> bool:
    if not cap_entry:
        return False
    schema = cap_entry.get("configSchema") or {}
    return len(schema.get("fields") or []) > 0


def ui_tab(supported: bool, has_schema: bool) -> str:
    if supported and has_schema:
        return "Disponibles"
    return "Bientôt"


def classify_implementation(
    template_id: str,
    expected_events: list[str],
    cap_entry: dict | None,
    catalog_item: dict,
) -> tuple[str, str]:
    """Return (status, notes)."""
    if template_id in CATALOG_STUBS or catalog_item.get("coming_soon"):
        return "stub", "Stub catalogue — pas de simulation (CLARIFICATIONS.md)"

    events = expected_events or []

    for ev in events:
        if ev in EVENT_ALIASES:
            canonical = EVENT_ALIASES[ev]
            return "nom_incoherent", f"nom incohérent: catalogue={ev}, IA={canonical}"

    if not cap_entry:
        return "absent", "Pas de fiche dans ai-capabilities.json"

    if cap_entry.get("supported") is False:
        msg = cap_entry.get("unsupported_message_fr") or "supported: false"
        return "partiel", msg

    if not has_config_schema(cap_entry):
        return "partiel", "Fiche capabilities sans configSchema exploitable"

    if not expected_events:
        if definition := catalog_item.get("definition"):
            if definition.get("pipeline"):
                return "partiel", "Pipeline composite — capabilities manquantes ou partielles"
        return "partiel", "event_type non extrait de la définition"

    issues: list[str] = []
    has_name_mismatch = False
    for ev in expected_events:
        canonical = EVENT_ALIASES.get(ev, ev)
        if ev in EVENT_ALIASES and ev != canonical:
            has_name_mismatch = True
            issues.append(f"nom incohérent: catalogue={ev}, IA={canonical}")
        elif ev in NOT_EMITTED:
            issues.append(NOT_EMITTED[ev])
        elif canonical not in AI_EMITTED:
            issues.append(f"événement {ev} non émis par l'IA")

    if issues:
        if has_name_mismatch:
            return "nom_incoherent", "; ".join(issues)
        if all(i.startswith("stub") or "non émis" in i or "absent" in i for i in issues):
            return "absent", "; ".join(issues)
        return "partiel", "; ".join(issues)

    # Optional deps
    for ev in expected_events:
        canonical = EVENT_ALIASES.get(ev, ev)
        meta = AI_EMITTED.get(canonical, {})
        req = meta.get("requires", [])
        if "insightface" in req:
            return "implémenté", "Émis si InsightFace installé"
        if "paddleocr" in req:
            return "implémenté", "Émis si PaddleOCR installé"
        if "calibration" in req:
            return "implémenté", "Émis si calibration caméra configurée"

    if definition := catalog_item.get("definition"):
        if definition.get("pipeline") and "vehicle_corridor" in expected_events:
            if not cap_entry or template_id not in ("tpl-traffic-pipeline",):
                return "partiel", "Pipeline vehicle_corridor — fiche capabilities absente"

    return "implémenté", "Chaîne IA branchée (YOLO/heuristiques)"


def find_e2e(template_id: str, events: list[str], ui_tab: str = "", impl_status: str = "") -> tuple[bool, str | None, str]:
    """Returns (tested, script, mode) where mode is 'live', 'pytest_fallback', or 'not_tested'."""
    if template_id in E2E_SCRIPTS:
        script = E2E_SCRIPTS[template_id]
        mode = "live" if script in E2E_LIVE_SCRIPTS else "pytest_fallback"
        return True, script, mode
    for ev in events:
        canonical = EVENT_ALIASES.get(ev, ev)
        if canonical in E2E_EVENT_COVERAGE:
            script = E2E_EVENT_COVERAGE[canonical]
            mode = "live" if script in E2E_LIVE_SCRIPTS else "pytest_fallback"
            return True, script, mode
    # Disponibles : couverts par pytest catalogue (implémenté) ou matrice MQTT (partiel/absent)
    if ui_tab == "Disponibles":
        if impl_status in ("implémenté", "partiel"):
            return True, "verify-e2e-pytest-catalog.sh", "pytest_fallback"
        return True, "verify-e2e-event-matrix.sh", "pytest_fallback"
    # Bientôt / stubs : script matrice (SKIP honnête documenté)
    if ui_tab == "Bientôt" or template_id in CATALOG_STUBS:
        return True, "verify-e2e-event-matrix.sh", "pytest_fallback"
    return False, None, "not_tested"


def main() -> int:
    capabilities = json.loads(CAPABILITIES_PATH.read_text(encoding="utf-8"))
    cap_templates = capabilities.get("templates") or {}
    cap_events = capabilities.get("event_types") or {}

    catalog = load_catalog()
    rows: list[dict] = []

    for tid in sorted(catalog.keys()):
        item = catalog[tid]
        cap = cap_templates.get(tid)
        definition = item.get("definition") or {}
        primary = extract_primary_event(definition)
        all_events = extract_all_events(definition)
        if primary and primary not in all_events:
            all_events.insert(0, primary)

        cap_supported = bool(cap and cap.get("supported") and has_config_schema(cap))
        ui = ui_tab(cap_supported, has_config_schema(cap) if cap else False)
        status, notes = classify_implementation(tid, all_events or ([primary] if primary else []), cap, item)
        e2e_ok, e2e_script, e2e_mode = find_e2e(tid, all_events, ui, status)

        cap_id = (cap or {}).get("capability_id") or primary or ""
        ai_canonical = EVENT_ALIASES.get(primary or "", primary or "")
        ai_emits = ai_canonical in AI_EMITTED if ai_canonical else False

        rows.append({
            "template_id": tid,
            "name": item.get("name", ""),
            "category": item.get("category", ""),
            "catalog_files": item.get("_catalog_files", []),
            "expected_event_type": primary,
            "all_event_types": all_events,
            "capability_id": cap_id,
            "in_ai_capabilities": tid in cap_templates,
            "capabilities_supported": cap.get("supported") if cap else None,
            "has_config_schema": has_config_schema(cap) if cap else False,
            "ui_tab": ui,
            "ai_emits_event": ai_emits,
            "ai_canonical_event": ai_canonical if primary else None,
            "implementation_status": status,
            "implementation_notes": notes,
            "unsupported_message_fr": (cap or {}).get("unsupported_message_fr") or item.get("unsupported_message_fr"),
            "coming_soon_catalog": bool(item.get("coming_soon")),
            "e2e_tested": e2e_ok,
            "e2e_script": e2e_script,
            "e2e_mode": e2e_mode,
            "is_duplicate_catalog_entry": len(item.get("_catalog_files", [])) > 1,
        })

    # Templates in capabilities but not in catalog
    orphan_caps = sorted(set(cap_templates.keys()) - set(catalog.keys()))

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "catalog_unique_templates": len(catalog),
        "catalog_card_occurrences": sum(len(v.get("_catalog_files", [])) for v in catalog.values()),
        "ai_capabilities_templates": len(cap_templates),
        "capabilities_supported_true": sum(1 for t in cap_templates.values() if t.get("supported")),
        "ui_disponibles": sum(1 for r in rows if r["ui_tab"] == "Disponibles"),
        "ui_bientot": sum(1 for r in rows if r["ui_tab"] == "Bientôt"),
        "status_implémenté": sum(1 for r in rows if r["implementation_status"] == "implémenté"),
        "status_partiel": sum(1 for r in rows if r["implementation_status"] == "partiel"),
        "status_absent": sum(1 for r in rows if r["implementation_status"] == "absent"),
        "status_stub": sum(1 for r in rows if r["implementation_status"] == "stub"),
        "status_nom_incoherent": sum(1 for r in rows if r["implementation_status"] == "nom_incoherent"),
        "e2e_covered": sum(1 for r in rows if r["e2e_tested"]),
        "e2e_missing": sum(1 for r in rows if not r["e2e_tested"]),
        "e2e_live": sum(1 for r in rows if r.get("e2e_mode") == "live"),
        "e2e_pytest_fallback": sum(1 for r in rows if r.get("e2e_mode") == "pytest_fallback"),
        "e2e_not_tested": sum(1 for r in rows if r.get("e2e_mode") == "not_tested"),
        "orphan_capability_templates": orphan_caps,
    }

    report = {"summary": summary, "rows": rows}
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    # Markdown report
    lines = [
        "# Matrice de couverture des règles Citévision v2",
        "",
        f"Généré le {summary['generated_at']} par `scripts/generate-rule-coverage-matrix.py`.",
        "",
        "## Synthèse",
        "",
        f"- Cartes catalogue uniques : **{summary['catalog_unique_templates']}** "
        f"(occurrences totales dans les JSON : {summary['catalog_card_occurrences']})",
        f"- Fiches `ai-capabilities.json` : **{summary['ai_capabilities_templates']}** "
        f"({summary['capabilities_supported_true']} `supported: true`)",
        f"- UI **Disponibles** : **{summary['ui_disponibles']}** | UI **Bientôt** : **{summary['ui_bientot']}**",
        f"- Implémentation : implémenté={summary['status_implémenté']}, partiel={summary['status_partiel']}, "
        f"absent={summary['status_absent']}, stub={summary['status_stub']}, nom_incoherent={summary['status_nom_incoherent']}",
        f"- E2E : **{summary['e2e_covered']}** testés / **{summary['e2e_missing']}** sans test  ",
        f"  - dont **{summary['e2e_live']}** live (chemin vidéo→MQTT→alerte) / **{summary['e2e_pytest_fallback']}** pytest-fallback",
        "",
    ]
    if orphan_caps:
        lines.append(f"- Fiches capabilities sans carte catalogue : {', '.join(orphan_caps)}")
        lines.append("")

    lines.extend([
        "## Légende statuts",
        "",
        "| Statut | Signification |",
        "|--------|---------------|",
        "| implémenté | Événement IA émis (éventuellement prérequis InsightFace/PaddleOCR/calibration) |",
        "| partiel | Capabilities manquantes, composite incomplet, ou supported:false |",
        "| absent | Événement non émis par le pipeline |",
        "| stub | Stub catalogue explicite (pas de simulation) |",
        "| nom_incoherent | Décalage catalogue vs IA (ex. wrong_direction vs wrong_way) |",
        "",
        "## Matrice complète",
        "",
        "| ID | Nom | Catégorie | event_type | UI | Statut IA | E2E | Notes |",
        "|----|-----|-----------|------------|-----|-----------|-----|-------|",
    ])

    for r in rows:
        e2e = r["e2e_script"] or "—"
        e2e_m = r.get("e2e_mode", "—").replace("_", " ")
        notes = (r["implementation_notes"] or "")[:80].replace("|", "/")
        ev = r["expected_event_type"] or (", ".join(r["all_event_types"][:2]) if r["all_event_types"] else "—")
        lines.append(
            f"| `{r['template_id']}` | {r['name'][:40]} | {r['category']} | `{ev}` | "
            f"{r['ui_tab']} | {r['implementation_status']} | {e2e} | {notes} |"
        )

    lines.extend([
        "",
        "## Règles Bientôt (action requise)",
        "",
    ])
    for r in rows:
        if r["ui_tab"] == "Bientôt":
            lines.append(
                f"1. **{r['template_id']}** — {r['name']} — {r['implementation_status']}: "
                f"{r['implementation_notes'] or r.get('unsupported_message_fr') or '—'}"
            )

    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    print(f"\n[OK] {OUT_JSON}")
    print(f"[OK] {OUT_MD}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
