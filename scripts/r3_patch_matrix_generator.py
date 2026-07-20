#!/usr/bin/env python3
"""
R3 – Patch generate-rule-coverage-matrix.py to distinguish e2e_live vs e2e_pytest_fallback.
Also adds e2e_mode field to each row and e2e_live/e2e_pytest_fallback to summary.
"""
from pathlib import Path

matrix_script = Path("scripts/generate-rule-coverage-matrix.py")
content = matrix_script.read_text(encoding="utf-8")

if 'e2e_live' in content and 'e2e_mode' in content:
    print("Already patched")
    exit(0)

# 1. Add E2E_LIVE_SCRIPTS set after E2E_SCRIPTS definition
E2E_LIVE_ANCHOR = """# E2E scripts mapped to template ids (expand as tests are added)."""
E2E_LIVE_ADDITION = """# Scripts that prove the full live chain: video → MQTT → alert (NOT just pytest unit tests).
E2E_LIVE_SCRIPTS: set[str] = {
    "verify-e2e-zone-alert.sh",
    "verify-e2e-family-spatial.sh",
    "verify-e2e-family-identity.sh",
    "verify-e2e-family-road.sh",
    "verify-e2e-sequence-theft.sh",
    "verify-e2e-spatial-semantic.sh",
    "verify-e2e-webhook-cloudevents.sh",
}

# Scripts that rely on pytest unit tests (fallback, don't prove the live chain).
E2E_PYTEST_FALLBACK_SCRIPTS: set[str] = {
    "verify-e2e-pytest-catalog.sh",
    "verify-e2e-event-matrix.sh",
    "verify-e2e-bientot-templates.sh",
}

"""
content = content.replace(E2E_LIVE_ANCHOR, E2E_LIVE_ADDITION + E2E_LIVE_ANCHOR)

# 2. Patch find_e2e to return a mode alongside the script
OLD_FIND_E2E = """def find_e2e(template_id: str, events: list[str], ui_tab: str = "", impl_status: str = "") -> tuple[bool, str | None]:
    if template_id in E2E_SCRIPTS:
        return True, E2E_SCRIPTS[template_id]
    for ev in events:
        canonical = EVENT_ALIASES.get(ev, ev)
        if canonical in E2E_EVENT_COVERAGE:
            return True, E2E_EVENT_COVERAGE[canonical]
    # Disponibles : couverts par pytest catalogue (implémenté) ou matrice MQTT (partiel/absent)
    if ui_tab == "Disponibles":
        if impl_status in ("implémenté", "partiel"):
            return True, "verify-e2e-pytest-catalog.sh"
        return True, "verify-e2e-event-matrix.sh"
    # Bientôt / stubs : script matrice (SKIP honnête documenté)
    if ui_tab == "Bientôt" or template_id in CATALOG_STUBS:
        return True, "verify-e2e-event-matrix.sh"
    return False, None"""

NEW_FIND_E2E = """def find_e2e(template_id: str, events: list[str], ui_tab: str = "", impl_status: str = "") -> tuple[bool, str | None, str]:
    \"\"\"Returns (tested, script, mode) where mode is 'live', 'pytest_fallback', or 'not_tested'.\"\"\"
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
    return False, None, "not_tested\""""

content = content.replace(OLD_FIND_E2E, NEW_FIND_E2E)

# 3. Update the call site that uses find_e2e
OLD_CALL = "        e2e_ok, e2e_script = find_e2e(tid, all_events, ui, status)"
NEW_CALL = "        e2e_ok, e2e_script, e2e_mode = find_e2e(tid, all_events, ui, status)"
content = content.replace(OLD_CALL, NEW_CALL)

# 4. Add e2e_mode to row dict
OLD_ROW_E2E = '            "e2e_tested": e2e_ok,\n            "e2e_script": e2e_script,'
NEW_ROW_E2E = '            "e2e_tested": e2e_ok,\n            "e2e_script": e2e_script,\n            "e2e_mode": e2e_mode,'
content = content.replace(OLD_ROW_E2E, NEW_ROW_E2E)

# 5. Add e2e_live and e2e_pytest_fallback counters to summary
OLD_SUMMARY_E2E = '        "e2e_covered": sum(1 for r in rows if r["e2e_tested"]),\n        "e2e_missing": sum(1 for r in rows if not r["e2e_tested"]),'
NEW_SUMMARY_E2E = """        "e2e_covered": sum(1 for r in rows if r["e2e_tested"]),
        "e2e_missing": sum(1 for r in rows if not r["e2e_tested"]),
        "e2e_live": sum(1 for r in rows if r.get("e2e_mode") == "live"),
        "e2e_pytest_fallback": sum(1 for r in rows if r.get("e2e_mode") == "pytest_fallback"),
        "e2e_not_tested": sum(1 for r in rows if r.get("e2e_mode") == "not_tested"),"""
content = content.replace(OLD_SUMMARY_E2E, NEW_SUMMARY_E2E)

# 6. Update the summary markdown to include the live/fallback split
OLD_MD_E2E = "        f\"- E2E : **{summary['e2e_covered']}** testés / **{summary['e2e_missing']}** sans test\","
NEW_MD_E2E = "        f\"- E2E : **{summary['e2e_covered']}** testés / **{summary['e2e_missing']}** sans test  \",\n        f\"  - dont **{summary['e2e_live']}** live (chemin vidéo→MQTT→alerte) / **{summary['e2e_pytest_fallback']}** pytest-fallback\","
content = content.replace(OLD_MD_E2E, NEW_MD_E2E)

# 7. Add e2e_mode column to markdown table
# Find the table header line
OLD_MD_TABLE_HDR = "| Template | Catégorie | Tab UI | IA émet | Implémentation | Notes | E2E |"
NEW_MD_TABLE_HDR = "| Template | Catégorie | Tab UI | IA émet | Implémentation | Partiel | Notes | E2E | Mode E2E |"
content = content.replace(OLD_MD_TABLE_HDR, NEW_MD_TABLE_HDR)

OLD_MD_SEP = "| --- | --- | --- | :---: | --- | --- | --- |"
NEW_MD_SEP = "| --- | --- | --- | :---: | --- | --- | --- | --- | --- |"
content = content.replace(OLD_MD_SEP, NEW_MD_SEP)

# Update the row formatting to include e2e_mode
OLD_MD_ROW = "        e2e = r[\"e2e_script\"] or \"—\""
NEW_MD_ROW = "        e2e = r[\"e2e_script\"] or \"—\"\n        e2e_m = r.get(\"e2e_mode\", \"—\").replace(\"_\", \" \")"
content = content.replace(OLD_MD_ROW, NEW_MD_ROW)

# Find the table row format string and add the new columns
import re
# Look for the f-string that builds markdown rows
OLD_MD_FSTR = r'f"| {r[\'template_id\']}.*?E2E \|"'
# This is tricky to find with regex, let's try a simpler approach
old_row_line = "        md_rows.append(f\"| {r['template_id']} | {r['category']} | {r['ui_tab']} | {'✓' if r['ai_emits_event'] else '✗'} | {r['implementation_status']} | {r.get('implementation_notes', '')} | {e2e} |\")"
new_row_line = "        partial = r.get('partial_status', '') or ''\n        md_rows.append(f\"| {r['template_id']} | {r['category']} | {r['ui_tab']} | {'✓' if r['ai_emits_event'] else '✗'} | {r['implementation_status']} | {partial} | {r.get('implementation_notes', '')} | {e2e} | {e2e_m} |\")"
content = content.replace(old_row_line, new_row_line)

matrix_script.write_text(content, encoding="utf-8")
print("Patched generate-rule-coverage-matrix.py")

# Verify python syntax
import subprocess
r = subprocess.run(["python3", "-m", "py_compile", str(matrix_script)], capture_output=True, text=True)
if r.returncode != 0:
    print("SYNTAX ERROR:", r.stderr)
else:
    print("Syntax OK")
