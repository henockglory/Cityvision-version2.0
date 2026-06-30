#!/usr/bin/env python3
"""E2E validation: N detections per demo rule (sequential), then disable all rules."""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
API = os.environ.get("BACKEND_API_URL", "http://localhost:8081")
MAILHOG = os.environ.get("MAILHOG_PUBLIC_URL", "http://localhost:8025")
EMAIL = os.environ.get("ADMIN_EMAIL", "glory.henock@hologram.cd")
PASS = os.environ.get("ADMIN_PASSWORD", "Hologram2026!")
TARGET = int(os.environ.get("TARGET_DETECTIONS", "2"))
TIMEOUT = int(os.environ.get("RULE_TIMEOUT_SEC", "600"))
DEMO_ORG = os.environ.get("DEMO_ORG_ID", "e312f375-7442-4089-8022-ed232abc09e8")
# Comma-separated rule names to validate (default: all). Example:
# VALIDATE_ONLY="Démo · Feu rouge,Démo · Excès de vitesse"
VALIDATE_ONLY = [
    s.strip() for s in os.environ.get("VALIDATE_ONLY", "").split(",") if s.strip()
]

# Order: comptage → ceinture → vitesse → téléphone → feu rouge (one rule active at a time).
RULES = [
    {
        "name": "Démo · Comptage véhicules",
        "event_types": ["line_cross"],
        "mail": False,
        "counter": True,
        "camera_id": "bbf2c5ae-2650-4fc8-b528-2a014e79df87",
        "require_alert": False,
    },
    {"name": "Démo · Non-port ceinture", "event_types": ["seatbelt_violation"], "mail": True, "counter": False},
    {"name": "Démo · Excès de vitesse", "event_types": ["speeding"], "mail": True, "counter": False},
    {
        "name": "Démo · Téléphone au volant",
        "event_types": ["phone_use_violation", "phone_driving"],
        "mail": True,
        "counter": False,
    },
    {"name": "Démo · Feu rouge", "event_types": ["red_light_violation"], "mail": True, "counter": False},
]


def req(method: str, url: str, token: str | None = None, body: dict | None = None) -> dict | list:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(r, timeout=60) as resp:
        raw = resp.read().decode()
        return json.loads(raw) if raw else {}


def login_token() -> str:
    login = req("POST", f"{API}/api/v1/auth/login", body={"email": EMAIL, "password": PASS})
    return login["access_token"]


def mail_count() -> int:
    try:
        with urllib.request.urlopen(f"{MAILHOG}/api/v2/messages?limit=1", timeout=5) as resp:
            return int(json.loads(resp.read()).get("total", 0))
    except Exception:
        return 0


def health_gate() -> None:
    req("GET", f"{API}/health")
    ai = req("GET", f"http://localhost:{os.environ.get('AI_ENGINE_PORT', '8001')}/health")
    for k in ("yolo_loaded", "face_loaded", "plate_loaded"):
        if str(ai.get(k, "")).lower() != "true":
            raise SystemExit(f"AI health: {k} not true")
    for k in ("driver_phone_model_loaded", "seatbelt_model_loaded"):
        if str(ai.get(k, "")).lower() != "true":
            raise SystemExit(f"AI secondary model not loaded: {k}")
    re = req("GET", f"http://localhost:{os.environ.get('RULES_ENGINE_PORT', '8010')}/health")
    print(f"rules-engine: {re}")


def _payload(e: dict) -> dict:
    payload = e.get("payload") or {}
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except json.JSONDecodeError:
            payload = {}
    return payload


def count_demo_events(token: str, org: str, event_types: list[str]) -> int:
    n = 0
    for et in event_types:
        try:
            rows = req(
                "GET",
                f"{API}/api/v1/orgs/{org}/events?limit=100&event_type={et}",
                token,
            )
        except Exception:
            continue
        if not isinstance(rows, list):
            rows = rows.get("items", []) if isinstance(rows, dict) else []
        for e in rows:
            payload = _payload(e)
            if payload.get("demo") is True or (payload.get("metadata") or {}).get("demo") is True:
                n += 1
    return n


def _alert_meta(a: dict) -> dict:
    m = a.get("metadata") or {}
    if isinstance(m, str):
        try:
            m = json.loads(m)
        except json.JSONDecodeError:
            m = {}
    return m


def count_alerts(token: str, org: str) -> int:
    rows = req("GET", f"{API}/api/v1/orgs/{org}/alerts?limit=200", token)
    if not isinstance(rows, list):
        rows = rows.get("items", []) if isinstance(rows, dict) else []
    return sum(
        1
        for a in rows
        if _alert_meta(a).get("demo") is True
        or str(_alert_meta(a).get("demo", "")).lower() == "true"
    )


def count_line_counter(token: str, org: str, camera_id: str) -> int:
    try:
        rows = req("GET", f"{API}/api/v1/orgs/{org}/lines/counters?camera_id={camera_id}", token)
    except Exception:
        return 0
    if not isinstance(rows, list):
        return 0
    return max((int(r.get("count_total", 0)) for r in rows), default=0)


def set_rule(token: str, org: str, rule_id: str, enabled: bool) -> None:
    req("PATCH", f"{API}/api/v1/orgs/{org}/rules/{rule_id}", token, {"is_enabled": enabled})


def disable_all(token: str, org: str, rules: list[dict]) -> None:
    for r in rules:
        if str(r.get("name", "")).startswith("Démo"):
            set_rule(token, org, r["id"], False)


def wait_active_rules(n: int, sec: int = 120) -> None:
    url = f"http://localhost:{os.environ.get('RULES_ENGINE_PORT', '8010')}/health"
    deadline = time.time() + sec
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=5) as resp:
                active = int(json.loads(resp.read()).get("active_rules", -1))
            if active == n:
                print(f"active_rules={active}")
                return
        except Exception:
            pass
        time.sleep(3)
    print(f"WARN: active_rules != {n} after {sec}s")


def main() -> int:
    logs = ROOT / "logs"
    logs.mkdir(exist_ok=True)
    report_tag = os.environ.get("REPORT_TAG", "tuning" if VALIDATE_ONLY else "five-rules")
    if report_tag == "sequential":
        report_md = logs / "demo-five-rules-sequential-report.md"
        report_json = logs / "demo-five-rules-sequential-report.json"
    elif report_tag == "seatbelt-quick":
        report_md = logs / "seatbelt-quick-report.md"
        report_json = logs / "seatbelt-quick-report.json"
    elif report_tag == "phone-quick":
        report_md = logs / "phone-quick-report.md"
        report_json = logs / "phone-quick-report.json"
    elif report_tag == "speed-quick":
        report_md = logs / "speed-quick-report.md"
        report_json = logs / "speed-quick-report.json"
    elif VALIDATE_ONLY:
        report_md = logs / "demo-five-rules-tuning-report.md"
        report_json = logs / "demo-five-rules-tuning-report.json"
    else:
        report_md = logs / "demo-five-rules-report.md"
        report_json = logs / "demo-five-rules-report.json"

    health_gate()

    login = req("POST", f"{API}/api/v1/auth/login", body={"email": EMAIL, "password": PASS})
    token = login["access_token"]
    token_at = time.time()
    me = req("GET", f"{API}/api/v1/auth/me", token)
    org = DEMO_ORG if DEMO_ORG else me.get("org_id", "")
    print(f"org={org} (user org={me.get('org_id')})")

    all_rules = req("GET", f"{API}/api/v1/orgs/{org}/rules", token)
    if not isinstance(all_rules, list):
        all_rules = []

    by_name = {r["name"]: r for r in all_rules if str(r.get("name", "")).startswith("Démo")}
    mail_before = mail_count()
    alerts_before = count_alerts(token, org)
    disable_all(token, org, all_rules)
    time.sleep(8)
    wait_active_rules(0)

    results: list[dict] = []
    pass_n = fail_n = 0

    for spec in RULES:
        name = spec["name"]
        if VALIDATE_ONLY and name not in VALIDATE_ONLY:
            continue
        event_types = spec["event_types"]
        rule = by_name.get(name)
        if not rule:
            results.append({"rule": name, "status": "FAIL", "detail": "rule missing in DB"})
            fail_n += 1
            continue

        print(f"\n=== {name} ===")
        disable_all(token, org, all_rules)
        time.sleep(5)
        wait_active_rules(0)

        evt_baseline = count_demo_events(token, org, event_types)
        ctr_baseline = count_line_counter(token, org, spec["camera_id"]) if spec.get("counter") else 0
        alerts_baseline = count_alerts(token, org)
        mail_rule_before = mail_count()

        set_rule(token, org, rule["id"], True)
        wait_active_rules(1)
        time.sleep(20)

        deadline = time.time() + TIMEOUT
        new_count = 0
        detail_parts: list[str] = []
        while time.time() < deadline:
            if time.time() - token_at > 240:
                token = login_token()
                token_at = time.time()
            evt_now = count_demo_events(token, org, event_types)
            new_count = max(0, evt_now - evt_baseline)
            if spec.get("counter"):
                ctr_now = count_line_counter(token, org, spec["camera_id"])
                new_count = max(new_count, max(0, ctr_now - ctr_baseline))
            if new_count >= TARGET:
                break
            time.sleep(8)

        status = "PASS" if new_count >= TARGET else "FAIL"
        if new_count < TARGET:
            detail_parts.append(f"new_events={new_count}/{TARGET}")

        new_alerts = count_alerts(token, org) - alerts_baseline
        require_alert = spec.get("require_alert", True)
        if status == "PASS" and require_alert and new_alerts < 1:
            status = "FAIL"
            detail_parts.append(f"alerts={new_alerts}, events={new_count}")

        if spec.get("mail") and status == "PASS":
            mail_delta = 0
            for _ in range(6):
                time.sleep(5)
                mail_delta = mail_count() - mail_rule_before
                if mail_delta >= 1:
                    break
            if mail_delta < 1:
                status = "FAIL"
                detail_parts.append("no_mail")
            else:
                detail_parts.append(f"mail+{mail_delta}")

        if status == "PASS":
            pass_n += 1
        else:
            fail_n += 1

        detail = ", ".join(detail_parts) if detail_parts else f"new_count={new_count}"
        print(f"{name}: {status} ({detail})")
        results.append({
            "rule": name,
            "event_types": event_types,
            "status": status,
            "detail": detail,
            "new_count": new_count,
            "new_alerts": new_alerts,
        })
        set_rule(token, org, rule["id"], False)
        time.sleep(5)

    disable_all(token, org, all_rules)
    wait_active_rules(0)

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "pass": pass_n,
        "fail": fail_n,
        "target_per_rule": TARGET,
        "handoff": "all_demo_rules_disabled",
        "results": results,
    }
    report_json.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    lines = [
        "# Demo Five Rules — E2E Report",
        "",
        f"Generated: {summary['generated_at']}",
        f"**PASS:** {pass_n} / **FAIL:** {fail_n} (target: {TARGET} detections/rule)",
        "",
        "## Handoff",
        "",
        "Les 5 règles démo sont **désactivées** après validation (`is_enabled=false`).",
        "Réactivation live : UI Règles ou `scripts/seed-demo-rules.sh`.",
        "",
        "## Résultats",
        "",
        "| Rule | Events | Status | Detail |",
        "|------|--------|--------|--------|",
    ]
    for r in results:
        et = ", ".join(r.get("event_types", []))
        lines.append(f"| {r['rule']} | {et} | {r['status']} | {r.get('detail', '')} |")
    lines.extend([
        "",
        "## Détail par règle",
        "",
    ])
    for r in results:
        lines.append(f"### {r['rule']}")
        lines.append(f"- **Status:** {r['status']}")
        lines.append(f"- **New demo events:** {r.get('new_count', 0)}")
        lines.append(f"- **New alerts:** {r.get('new_alerts', 0)}")
        lines.append(f"- **Detail:** {r.get('detail', '')}")
        lines.append("")
    lines.extend([
        "## Diagnostics runtime",
        "",
        "- **Spatial AI:** `bash scripts/force-spatial-reload.sh` (behaviors feu/vitesse sur caméras Feux + Ligne Continue).",
        "- **Rules-engine actions:** URLs internes corrigées → `/api/v1/internal/orgs/{orgID}/...` (evidence, mail, clip).",
        "- **Feu rouge:** la règle écoute `red_light_violation` (synergie véhicule en mouvement + feu rouge), pas `traffic_light_state` seul.",
        "- **Vitesse:** `speeding` via traverse zone `Zone_distance_parcourue` (8 m, limite 8 km/h).",
        "- **Comptage:** compteur `Ligne_count` via API `/lines/counters`.",
        "",
        "## Notes pipeline",
        "",
        "- **Feu rouge** : nécessite `red_light_violation` (véhicule en mouvement dans Zone_Observation pendant feu rouge).",
        "  `traffic_light_state` seul ne suffit pas pour la règle.",
        "- **Vitesse** : `speeding` via timing zone `Zone_distance_parcourue` (8 m, limite 8 km/h).",
        "- **Comptage** : compteur ligne `Ligne_count` (API `/lines/counters`).",
        "- Prérequis spatial : `bash scripts/force-spatial-reload.sh` si behaviors absents côté AI.",
        "",
        f"JSON détaillé : `logs/demo-five-rules-report.json`",
    ])
    report_md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n" + "\n".join(lines))

    if fail_n > 0:
        print(f"\nVALIDATION FAILED ({fail_n} rules)", file=sys.stderr)
        return 1
    print("\nVALIDATION PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
