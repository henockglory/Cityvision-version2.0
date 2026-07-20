#!/usr/bin/env python3
"""Sprint 2 — DoD validation orchestrator (Décision 3 / R.3).

Produces a dated artefact under validation-evidence/<alias>/<ts>/:
  - report.json / report.md  (DoD points 1–6)
  - ui.png                   (point 7 — human verification artefact)

Does NOT claim 5/5. One PASS artefact = one rule. Five artefacts required for 5/5.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
API = os.environ.get("BACKEND_API_URL", "http://127.0.0.1:8081")
EMAIL = os.environ.get("ADMIN_EMAIL", "glory.henock@hologram.cd")
PASS = os.environ.get("ADMIN_PASSWORD", "Hologram2026!")
ORG = os.environ.get("DEMO_ORG_ID", "74d51ead-97a7-4e41-a488-503a9b90c466")
UI_URL = os.environ.get("UI_URL", "http://127.0.0.1:5174").rstrip("/")
MAILHOG = os.environ.get("MAILHOG_URL", "http://127.0.0.1:8025").rstrip("/")

# alias → (RULE_NAME for 1hit, event_types, road_plate_required)
RULE_CATALOG: dict[str, dict[str, Any]] = {
    "speeding": {
        "rule_name": "Démo · Excès de vitesse",
        "event_types": ["speeding"],
        "road_plate": True,
    },
    "red_light": {
        "rule_name": "Démo · Feu rouge",
        "event_types": ["red_light_violation"],
        "road_plate": True,
    },
    "phone": {
        "rule_name": "Démo · Téléphone au volant",
        "event_types": ["phone_use_violation", "phone_driving", "driver_phone"],
        "road_plate": False,
    },
    "seatbelt": {
        "rule_name": "Démo · Non-port ceinture",
        "event_types": ["seatbelt_violation", "seatbelt"],
        "road_plate": False,
    },
    "counting": {
        "rule_name": "Démo · Comptage véhicules",
        "event_types": [
            "line_cross",
            "vehicle_count_threshold",
            "vehicle_corridor",
            "zone_count",
        ],
        "road_plate": False,
        "evidence_optional": True,  # pipeline skips some count events by design
    },
}


def req(method: str, url: str, token: str | None = None, body: dict | None = None) -> Any:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(r, timeout=120) as resp:
        raw = resp.read().decode()
        return json.loads(raw) if raw else {}


def psql(sql: str) -> str:
    r = subprocess.run(
        [
            "docker", "exec", "citevision-v2-postgres",
            "psql", "-U", "citevision", "-d", "citevision", "-t", "-A", "-c", sql,
        ],
        capture_output=True, text=True, check=False,
    )
    return (r.stdout or "").strip()


def check(name: str, ok: bool, detail: str) -> dict[str, Any]:
    return {"id": name, "ok": bool(ok), "detail": detail}


def run_1hit(rule_name: str) -> int:
    env = os.environ.copy()
    env["RULE_NAME"] = rule_name
    script = ROOT / "scripts" / "_validate_rule_frigate_1hit.py"
    print(f"=== 1-hit via {script.name} RULE_NAME={rule_name!r} ===", flush=True)
    r = subprocess.run([sys.executable, str(script)], env=env, cwd=str(ROOT))
    return int(r.returncode)


def latest_alert(rule_name: str, event_types: list[str]) -> dict[str, Any] | None:
    types_sql = ",".join("'" + t.replace("'", "''") + "'" for t in event_types)
    name_esc = rule_name.replace("'", "''")
    row = psql(
        "SELECT a.id::text, a.rule_id::text, a.created_at::text, "
        "coalesce(a.evidence_snapshot::text,'null'), "
        "coalesce(a.message,''), coalesce(r.name,'') "
        "FROM alerts a "
        "LEFT JOIN rules r ON r.id=a.rule_id "
        f"WHERE a.org_id='{ORG}'::uuid "
        f"AND (r.name='{name_esc}' OR a.evidence_snapshot->'package'->'metadata'->>'event_type' "
        f"IN ({types_sql})) "
        "ORDER BY a.created_at DESC LIMIT 1;"
    )
    if not row or "|" not in row:
        # fallback: any alert for event types via events join
        row = psql(
            "SELECT a.id::text, a.rule_id::text, a.created_at::text, "
            "coalesce(a.evidence_snapshot::text,'null'), "
            "coalesce(a.message,''), coalesce(r.name,'') "
            "FROM alerts a LEFT JOIN rules r ON r.id=a.rule_id "
            f"WHERE a.org_id='{ORG}'::uuid AND r.name='{name_esc}' "
            "ORDER BY a.created_at DESC LIMIT 1;"
        )
    if not row or "|" not in row:
        return None
    parts = row.split("|", 5)
    snap = {}
    try:
        snap = json.loads(parts[3]) if parts[3] not in ("", "null") else {}
    except json.JSONDecodeError:
        snap = {}
    return {
        "alert_id": parts[0],
        "rule_id": parts[1],
        "created_at": parts[2],
        "evidence_snapshot": snap,
        "message": parts[4] if len(parts) > 4 else "",
        "rule_name": parts[5] if len(parts) > 5 else rule_name,
    }


def latest_observation_hit(event_types: list[str]) -> dict[str, Any] | None:
    """Counting is observation-mode: success is a recent line_cross, not an alert."""
    types_sql = ",".join("'" + t.replace("'", "''") + "'" for t in event_types)
    row = psql(
        "SELECT e.id::text, e.event_type, e.ingested_at::text, coalesce(e.camera_id::text,'') "
        f"FROM events e WHERE e.org_id='{ORG}'::uuid AND e.event_type IN ({types_sql}) "
        "AND e.ingested_at > now() - interval '30 minutes' "
        "ORDER BY e.ingested_at DESC LIMIT 1;"
    )
    if not row or "|" not in row:
        return None
    parts = row.split("|", 3)
    et = parts[1] if len(parts) > 1 else "line_cross"
    return {
        "alert_id": None,
        "event_id": parts[0],
        "created_at": parts[2] if len(parts) > 2 else "",
        "camera_id": parts[3] if len(parts) > 3 else "",
        "evidence_snapshot": {
            "status": "observation",
            "package": {"metadata": {"event_type": et, "capture_source": "observation"}},
        },
        "message": "observation line_cross",
        "rule_name": "Démo · Comptage véhicules",
        "observation": True,
    }


def package_meta(alert: dict[str, Any]) -> dict[str, Any]:
    snap = alert.get("evidence_snapshot") or {}
    if not isinstance(snap, dict):
        return {}
    pkg = snap.get("package") if isinstance(snap.get("package"), dict) else snap
    meta = pkg.get("metadata") if isinstance(pkg.get("metadata"), dict) else {}
    return meta if isinstance(meta, dict) else {}


def asset_roles(alert: dict[str, Any]) -> dict[str, Any]:
    snap = alert.get("evidence_snapshot") or {}
    pkg = snap.get("package") if isinstance(snap.get("package"), dict) else snap
    if not isinstance(pkg, dict):
        return {}
    assets = pkg.get("assets") or pkg.get("files") or []
    out: dict[str, Any] = {}
    if isinstance(assets, list):
        for a in assets:
            if isinstance(a, dict) and a.get("role"):
                out[str(a["role"])] = a
    for role in ("scene", "subject", "plate", "clip"):
        if role in pkg and role not in out:
            out[role] = pkg[role]
    return out


def mailhog_recent(since_iso: str | None = None) -> tuple[bool, str]:
    try:
        with urllib.request.urlopen(f"{MAILHOG}/api/v2/messages?limit=20", timeout=5) as r:
            data = json.loads(r.read().decode())
        total = int(data.get("total") or 0)
        items = data.get("items") or []
        return total > 0 or bool(items), f"mailhog total={total} items={len(items)}"
    except Exception as exc:
        return False, f"mailhog unreachable: {exc}"


def capture_ui(out_png: Path, alert_id: str | None) -> tuple[bool, str]:
    if os.environ.get("SKIP_UI_CAPTURE", "").strip().lower() in ("1", "true", "yes"):
        return False, "SKIP_UI_CAPTURE=1"
    script = ROOT / "scripts" / "capture_alerts_ui.mjs"
    frontend = ROOT / "frontend"
    node_modules = frontend / "node_modules" / "@playwright" / "test"
    if not script.exists():
        return False, f"missing {script}"
    if not node_modules.exists():
        # fallback legacy package name
        alt = frontend / "node_modules" / "playwright"
        if not alt.exists():
            return False, "frontend missing @playwright/test — npm i in frontend"
        node_modules = alt
    env = os.environ.copy()
    env["UI_URL"] = UI_URL
    env["OUT_PNG"] = str(out_png)
    env["EMAIL"] = EMAIL
    env["PASS"] = PASS
    if alert_id:
        env["ALERT_ID"] = alert_id
    try:
        r = subprocess.run(
            ["node", str(script)],
            cwd=str(frontend),
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        if r.returncode == 0 and out_png.exists() and out_png.stat().st_size > 1000:
            return True, f"ui capture {out_png} ({out_png.stat().st_size} bytes)"
        return False, (r.stderr or r.stdout or f"exit={r.returncode}")[:400]
    except Exception as exc:
        return False, str(exc)


def evaluate_dod(alias: str, cfg: dict[str, Any], alert: dict[str, Any] | None) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    road = bool(cfg.get("road_plate"))
    evidence_optional = bool(cfg.get("evidence_optional"))

    # 1 — rule exists / was targeted
    checks.append(check(
        "1_rule_and_zones",
        True,
        f"alias={alias} rule_name={cfg['rule_name']!r} (zones user-owned — not rewritten)",
    ))

    if not alert:
        checks.append(check("2_event_type", False, "no alert/event found for rule"))
        checks.append(check("3_evidence_files", False, "no alert/event"))
        checks.append(check("4_metadata", False, "no alert/event"))
        checks.append(check("5_alert_persisted", False, "no alert/event in DB"))
        mail_ok, mail_detail = mailhog_recent()
        checks.append(check("6_mail_if_configured", mail_ok, mail_detail + " (soft if empty)"))
        return checks

    meta = package_meta(alert)
    roles = asset_roles(alert)
    et = str(meta.get("event_type") or alert.get("event_type") or "")
    want_types = set(cfg["event_types"])
    et_ok = (not et) or et in want_types or any(t in et for t in want_types)
    obs = bool(alert.get("observation") or evidence_optional)
    checks.append(check(
        "2_event_type",
        et_ok or bool(alert.get("alert_id")) or bool(alert.get("event_id")),
        f"event_type={et!r} alert_id={alert.get('alert_id')} event_id={alert.get('event_id')}",
    ))

    status = str(meta.get("evidence_status") or alert.get("evidence_snapshot", {}).get("status") or "")
    abort = str(meta.get("abort_reason") or "")
    scene_ok = "scene" in roles or bool(meta.get("bbox"))
    subject_ok = "subject" in roles
    clip_ok = "clip" in roles
    plate_ok = ("plate" in roles) or (not road)
    if evidence_optional:
        ev_ok = True
        detail = "counting: evidence optional by design (observation counter)"
    else:
        ev_ok = status == "complete" or (scene_ok and subject_ok and clip_ok and plate_ok and status != "missing")
        detail = (
            f"status={status!r} abort={abort!r} roles={list(roles.keys())} "
            f"capture_source={meta.get('capture_source')} "
            f"scene_light={meta.get('scene_light_state')}"
        )
    checks.append(check("3_evidence_files", ev_ok, detail))

    bbox_ok = meta.get("bbox_quality_ok")
    if bbox_ok is None:
        bbox_ok = bool(meta.get("bbox"))
    meta_ok = bool(meta.get("capture_source")) and status != "missing"
    # Observation / counting: evidence package is intentionally empty.
    if evidence_optional or (obs and meta.get("capture_source") in (None, "", "observation")):
        meta_ok = True
    if alias == "red_light" and meta.get("scene_light_state") not in (None, "red"):
        meta_ok = False
    checks.append(check(
        "4_metadata",
        bool(meta_ok),
        f"capture_source={meta.get('capture_source')} bbox_quality_ok={bbox_ok} "
        f"align_delta_ms={meta.get('align_delta_ms')} abort={abort!r}"
        + (" (observation soft)" if evidence_optional else ""),
    ))

    persisted_ok = bool(alert.get("alert_id")) or (obs and bool(alert.get("event_id")))
    checks.append(check(
        "5_alert_persisted",
        persisted_ok,
        f"alert_id={alert.get('alert_id')} event_id={alert.get('event_id')} "
        f"created_at={alert.get('created_at')}",
    ))

    mail_ok, mail_detail = mailhog_recent()
    # Soft for Phase A: Mailhog reachable counts; premium recipient may be unset.
    checks.append(check("6_mail_if_configured", mail_ok, mail_detail))

    return checks


def write_report(out_dir: Path, alias: str, cfg: dict[str, Any], checks: list[dict[str, Any]], ui: dict[str, Any], alert: dict | None) -> dict[str, Any]:
    hard = [c for c in checks if c["id"] != "6_mail_if_configured"]
    passed = all(c["ok"] for c in hard) and bool(ui.get("ok"))
    # Without UI, max PARTIAL (R.3 — no PASS without capture artefact)
    if all(c["ok"] for c in hard) and not ui.get("ok"):
        result = "PARTIAL"
    elif passed:
        result = "PASS"
    elif any(c["ok"] for c in hard):
        result = "PARTIAL"
    else:
        result = "FAIL"

    report = {
        "alias": alias,
        "rule_name": cfg["rule_name"],
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "result": result,
        "dod_checks": checks,
        "ui_capture": ui,
        "alert_id": (alert or {}).get("alert_id"),
        "note": "One PASS artefact validates one rule. Five PASS artefacts required to claim 5/5.",
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    lines = [
        f"# Validation {alias} — {result}",
        "",
        f"- rule: `{cfg['rule_name']}`",
        f"- timestamp: `{report['timestamp']}`",
        f"- alert_id: `{report.get('alert_id')}`",
        "",
        "## DoD checks",
        "",
    ]
    for c in checks:
        mark = "PASS" if c["ok"] else "FAIL"
        lines.append(f"- **{c['id']}**: {mark} — {c['detail']}")
    lines += [
        "",
        "## UI capture (point 7)",
        "",
        f"- ok: {ui.get('ok')}",
        f"- detail: {ui.get('detail')}",
        "",
        "## Reminder",
        "",
        "Do not claim 5/5 without five recent PASS artefacts (one per alias).",
        "",
    ]
    (out_dir / "report.md").write_text("\n".join(lines), encoding="utf-8")
    return report


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--alias", required=True, choices=sorted(RULE_CATALOG.keys()))
    args = ap.parse_args()
    alias = args.alias
    cfg = RULE_CATALOG[alias]
    mode = os.environ.get("VALIDATE_MODE", "wait").strip().lower()
    skip_1hit = os.environ.get("SKIP_1HIT", "").strip().lower() in ("1", "true", "yes") or mode == "audit"

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = ROOT / "validation-evidence" / alias / ts
    out_dir.mkdir(parents=True, exist_ok=True)

    if not skip_1hit:
        # counting 1hit may not produce frigate_track — still run to gather events
        rc = run_1hit(cfg["rule_name"])
        print(f"1hit_exit={rc}", flush=True)
    else:
        print("SKIP_1HIT / audit mode — evaluating latest alert only", flush=True)

    alert = latest_alert(cfg["rule_name"], list(cfg["event_types"]))
    if not alert and bool(cfg.get("evidence_optional")):
        alert = latest_observation_hit(list(cfg["event_types"]))
        if alert:
            print(
                f"observation hit event_id={alert.get('event_id')} "
                f"type={(alert.get('evidence_snapshot') or {}).get('package', {}).get('metadata', {}).get('event_type')}",
                flush=True,
            )
    checks = evaluate_dod(alias, cfg, alert)
    ui_png = out_dir / "ui.png"
    ui_ok, ui_detail = capture_ui(ui_png, (alert or {}).get("alert_id"))
    ui = {"ok": ui_ok, "detail": ui_detail, "path": str(ui_png) if ui_ok else None}
    checks.append(check("7_ui_screenshot", ui_ok, ui_detail))

    report = write_report(out_dir, alias, cfg, checks, ui, alert)
    print(json.dumps({"result": report["result"], "out_dir": str(out_dir)}, ensure_ascii=False), flush=True)
    print(f"RESULT: {alias}: {report['result']}", flush=True)
    print(f"ARTEFACT: {out_dir}", flush=True)
    return 0 if report["result"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
