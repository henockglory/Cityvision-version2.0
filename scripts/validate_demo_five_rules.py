#!/usr/bin/env python3
"""E2E validation: N detections per demo rule (sequential), then disable all rules."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(line_buffering=True)
API = os.environ.get("BACKEND_API_URL", "http://localhost:8081")
MAILHOG = os.environ.get("MAILHOG_PUBLIC_URL", "http://localhost:8025")
EMAIL = os.environ.get("ADMIN_EMAIL", "glory.henock@hologram.cd")
PASS = os.environ.get("ADMIN_PASSWORD", "Henockglory@03")
TARGET = int(os.environ.get("TARGET_DETECTIONS", "2"))
TIMEOUT = int(os.environ.get("RULE_TIMEOUT_SEC", "600"))
SYNC_WAIT = int(os.environ.get("RULE_SYNC_WAIT_SEC", "35"))
# [P.131] No hardcoded IDs. Org is resolved live from /auth/me; an explicit
# DEMO_ORG_ID env override is honored only when the operator sets it on purpose.
DEMO_ORG = os.environ.get("DEMO_ORG_ID", "")
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
        # [P.131] camera_id resolved live (see resolve_counter_camera) — never hardcoded.
        "camera_id": None,
        "counter_camera_hint": "compt",
        "require_alert": False,
    },
    {"name": "Démo · Non-port ceinture", "event_types": ["seatbelt_violation"], "mail": True, "counter": False},
    {"name": "Démo · Excès de vitesse", "event_types": ["speeding"], "mail": True, "counter": False},
    {"name": "Démo · Téléphone au volant", "event_types": ["phone_use_violation"], "mail": True, "counter": False},
    {"name": "Démo · Feu rouge", "event_types": ["red_light_violation"], "mail": True, "counter": False},
]


def _results_to_rules_map(results: list[dict]) -> dict[str, dict]:
    """Normalize validate_demo results for ROADMAP-138 tracker."""
    key_map = {
        "Démo · Comptage véhicules": "line_count",
        "Démo · Non-port ceinture": "seatbelt",
        "Démo · Excès de vitesse": "speed",
        "Démo · Téléphone au volant": "phone",
        "Démo · Feu rouge": "red_light",
    }
    out: dict[str, dict] = {}
    for r in results:
        key = key_map.get(str(r.get("rule", "")))
        if not key:
            continue
        st = str(r.get("status", "")).lower()
        out[key] = {
            "status": "pass" if st == "pass" else ("deferred" if st == "skipped" else "fail"),
            "detail": r.get("detail", ""),
            "new_count": r.get("new_count", 0),
        }
    return out


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


def list_demo_alert_ids(token: str, org: str) -> set[str]:
    rows = req("GET", f"{API}/api/v1/orgs/{org}/alerts?limit=200&include_incomplete=true", token)
    if not isinstance(rows, list):
        rows = rows.get("items", []) if isinstance(rows, dict) else []
    ids: set[str] = set()
    for a in rows:
        meta = _alert_meta(a)
        if meta.get("demo") is True or str(meta.get("demo", "")).lower() == "true":
            aid = a.get("id")
            if aid:
                ids.add(str(aid))
    return ids


def latest_demo_alert(token: str, org: str, baseline_ids: set[str]) -> dict | None:
    rows = req("GET", f"{API}/api/v1/orgs/{org}/alerts?limit=50&include_incomplete=true", token)
    if not isinstance(rows, list):
        rows = rows.get("items", []) if isinstance(rows, dict) else []
    for a in rows:
        aid = str(a.get("id", ""))
        if aid and aid not in baseline_ids:
            meta = _alert_meta(a)
            if meta.get("demo") is True or str(meta.get("demo", "")).lower() == "true":
                return a
    return None


def alert_evidence_ok(alert: dict) -> tuple[bool, str]:
    """Check evidence completeness per [A.3] — clip url + scene + subject."""
    meta = _alert_meta(alert)
    snap = meta.get("evidence_snapshot") or meta.get("evidence") or {}
    pkg = snap.get("package") if isinstance(snap.get("package"), dict) else snap
    if not isinstance(pkg, dict):
        return False, "no_evidence_package"
    clip = pkg.get("clip") or {}
    if not (clip.get("url") or clip.get("asset_id")):
        return False, "missing_clip"
    images = pkg.get("images") or []
    roles = {str(i.get("role")) for i in images if isinstance(i, dict)}
    missing = [r for r in ("scene", "subject") if r not in roles]
    if missing:
        return False, f"missing_images:{','.join(missing)}"
    return True, "complete"


def count_alerts(token: str, org: str) -> int:
    return len(list_demo_alert_ids(token, org))


def resolve_counter_camera(token: str, org: str, hint: str, rule: dict | None) -> str | None:
    """[P.131] Resolve the counting camera dynamically — no hardcoded UUID.

    Priority: (1) camera bound in the rule definition, (2) a camera whose name
    matches the hint (e.g. "compt"/"décompte"), (3) the only camera that has a
    line counter. Returns None if nothing can be resolved (caller degrades).
    """
    # (1) From the rule's own bindings, if present.
    if rule:
        definition = rule.get("definition")
        if isinstance(definition, str):
            try:
                definition = json.loads(definition)
            except json.JSONDecodeError:
                definition = {}
        bindings = (definition or {}).get("bindings") or {}
        cam = bindings.get("camera_id")
        if cam:
            return str(cam)

    # (2) By camera name hint.
    try:
        cams = req("GET", f"{API}/api/v1/orgs/{org}/cameras", token)
        if isinstance(cams, dict):
            cams = cams.get("items", [])
        if isinstance(cams, list):
            for c in cams:
                name = str(c.get("name", "")).lower()
                if hint and hint.lower() in name:
                    return str(c.get("id") or c.get("camera_id"))
    except Exception:
        pass

    # (3) The camera that already owns a line counter.
    try:
        rows = req("GET", f"{API}/api/v1/orgs/{org}/lines/counters", token)
        if isinstance(rows, list):
            for r in rows:
                cam = r.get("camera_id")
                if cam:
                    return str(cam)
    except Exception:
        pass
    return None


def count_observation_counter(token: str, org: str, camera_id: str) -> int:
    try:
        rows = req("GET", f"{API}/api/v1/orgs/{org}/observations/counters?camera_id={camera_id}", token)
    except Exception:
        return 0
    if not isinstance(rows, list):
        return 0
    return sum(int(r.get("count", 0)) for r in rows)


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


def rule_camera_id(rule: dict | None) -> str | None:
    """Extract the camera_id a demo rule is bound to (definition.bindings.camera_id)."""
    if not rule:
        return None
    definition = rule.get("definition")
    if isinstance(definition, str):
        try:
            definition = json.loads(definition)
        except json.JSONDecodeError:
            definition = {}
    bindings = (definition or {}).get("bindings") or {}
    cam = bindings.get("camera_id") or (definition or {}).get("camera_id")
    return str(cam) if cam else None


def get_active_demo_video(token: str, org: str) -> str | None:
    try:
        st = req("GET", f"{API}/api/v1/orgs/{org}/demo/settings", token)
    except Exception:
        return None
    vid = (st or {}).get("active_video_id") if isinstance(st, dict) else None
    return str(vid) if vid else None


def camera_video_id(token: str, org: str, camera_id: str) -> str | None:
    """Resolve the demo video id backing a demo camera (metadata.demo_video_id)."""
    try:
        cams = req("GET", f"{API}/api/v1/orgs/{org}/cameras", token)
    except Exception:
        return None
    if isinstance(cams, dict):
        cams = cams.get("items", [])
    for c in cams or []:
        if str(c.get("id") or c.get("camera_id")) != str(camera_id):
            continue
        meta = c.get("metadata") or {}
        if isinstance(meta, str):
            try:
                meta = json.loads(meta)
            except json.JSONDecodeError:
                meta = {}
        vid = meta.get("demo_video_id")
        return str(vid) if vid else None
    return None


def set_active_demo_video(token: str, org: str, video_id: str) -> None:
    """[B.24]/[D.35] Demo ingestion is mono-camera and switched by ACTIVE VIDEO
    (the API rejects setting a demo/virtual camera via active_camera_id). Setting
    active_video_id makes the orchestrator resolve+start the backing camera with
    its behaviors automatically — no manual spatial push needed.
    """
    req(
        "PATCH",
        f"{API}/api/v1/orgs/{org}/demo/settings",
        token,
        {"source_mode": "video", "active_video_id": video_id},
    )


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


def refresh_feux_stream() -> None:
    script = ROOT / "scripts/push_ai_spatial_from_api.py"
    if not script.is_file():
        return
    print("==> refresh feux AI stream before feu rule")
    try:
        subprocess.run(
            [sys.executable, str(script)],
            cwd=str(ROOT),
            timeout=120,
            check=False,
            env=os.environ.copy(),
        )
        time.sleep(12)
    except Exception as exc:
        print(f"WARN: feux refresh: {exc}")


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
    elif report_tag == "speed-retest":
        report_md = logs / "demo-five-rules-speed-retest.md"
        report_json = logs / "demo-five-rules-speed-retest.json"
    elif report_tag == "final":
        report_md = logs / "demo-five-rules-final-report.md"
        report_json = logs / "demo-five-rules-final-report.json"
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

    # [P.131] Resolve counter camera(s) dynamically — no hardcoded UUID.
    for spec in RULES:
        if spec.get("counter") and not spec.get("camera_id"):
            resolved = resolve_counter_camera(
                token, org, spec.get("counter_camera_hint", ""), by_name.get(spec["name"])
            )
            spec["camera_id"] = resolved
            print(f"resolved counter camera for '{spec['name']}': {resolved}")

    mail_before = mail_count()
    alerts_before = count_alerts(token, org)
    original_video = get_active_demo_video(token, org)
    print(f"original active demo video: {original_video}")
    disable_all(token, org, all_rules)
    time.sleep(8)
    wait_active_rules(0)

    results: list[dict] = []
    pass_n = fail_n = 0

    for spec in RULES:
        name = spec["name"]
        if VALIDATE_ONLY and name not in VALIDATE_ONLY:
            if name == "Démo · Excès de vitesse" and os.environ.get("SPEED_DEFERRED", "0") == "1":
                results.append({
                    "rule": name,
                    "event_types": spec["event_types"],
                    "status": "SKIPPED",
                    "detail": "deferred: zone Zone_distance_parcourue hors trafic [A.1]",
                    "new_count": 0,
                    "new_alerts": 0,
                })
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

        # [B.24]/[D.35] Switch mono-camera demo ingestion to this scenario's camera
        # via its backing video, so the orchestrator auto-starts it with behaviors.
        scenario_cam = spec.get("camera_id") or rule_camera_id(rule)
        scenario_video = camera_video_id(token, org, scenario_cam) if scenario_cam else None
        if scenario_video:
            try:
                set_active_demo_video(token, org, scenario_video)
                settle = int(os.environ.get("DEMO_SETTLE_SEC", "40"))
                print(f"active demo video -> {scenario_video} (cam {scenario_cam}); settling {settle}s…")
                time.sleep(settle)
            except Exception as exc:
                print(f"WARN: could not switch demo video: {exc}")
        else:
            print(f"WARN: no video resolved for camera {scenario_cam}; skipping switch")

        evt_baseline = count_demo_events(token, org, event_types)
        ctr_baseline = (
            max(
                count_line_counter(token, org, spec["camera_id"]),
                count_observation_counter(token, org, spec["camera_id"]),
            )
            if spec.get("counter") and spec.get("camera_id")
            else 0
        )
        alerts_baseline_ids = list_demo_alert_ids(token, org)
        alerts_baseline = len(alerts_baseline_ids)
        mail_rule_before = mail_count()

        if name == "Démo · Feu rouge":
            refresh_feux_stream()

        set_rule(token, org, rule["id"], True)
        wait_active_rules(1, sec=180)
        print(f"rules-engine sync wait {SYNC_WAIT}s…")
        time.sleep(SYNC_WAIT)

        deadline = time.time() + TIMEOUT
        new_count = 0
        detail_parts: list[str] = []
        while time.time() < deadline:
            if time.time() - token_at > 240:
                token = login_token()
                token_at = time.time()
            evt_now = count_demo_events(token, org, event_types)
            new_count = max(0, evt_now - evt_baseline)
            if spec.get("counter") and spec.get("camera_id"):
                ctr_now = max(
                    count_line_counter(token, org, spec["camera_id"]),
                    count_observation_counter(token, org, spec["camera_id"]),
                )
                new_count = max(new_count, max(0, ctr_now - ctr_baseline))
            if new_count >= TARGET:
                break
            time.sleep(8)

        # [H.72]/[A.9] Evidence capture is async — wait for alerts after events land.
        alert_wait = int(os.environ.get("ALERT_WAIT_SEC", "120"))
        if new_count >= TARGET and spec.get("require_alert", True):
            alert_deadline = time.time() + alert_wait
            while time.time() < alert_deadline:
                if len(list_demo_alert_ids(token, org) - alerts_baseline_ids) >= 1:
                    break
                time.sleep(8)

        status = "PASS" if new_count >= TARGET else "FAIL"
        if new_count < TARGET:
            detail_parts.append(f"new_events={new_count}/{TARGET}")

        new_alerts = len(list_demo_alert_ids(token, org) - alerts_baseline_ids)
        mail_delta = 0
        if spec.get("mail") and new_count >= TARGET:
            for _ in range(12):
                time.sleep(5)
                mail_delta = mail_count() - mail_rule_before
                if mail_delta >= 1:
                    break

        require_alert = spec.get("require_alert", True)
        if status == "PASS" and require_alert and new_alerts < 1:
            if mail_delta >= 1:
                detail_parts.append(f"mail+{mail_delta} (alert async)")
            else:
                status = "FAIL"
                detail_parts.append(f"alerts={new_alerts}, events={new_count}")

        if spec.get("mail") and status == "PASS":
            if mail_delta < 1:
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

        if status == "PASS" and require_alert and spec.get("name") != "Démo · Comptage véhicules":
            alert = latest_demo_alert(token, org, alerts_baseline_ids)
            if alert:
                ev_ok, ev_reason = alert_evidence_ok(alert)
                if not ev_ok:
                    status = "PARTIAL"
                    detail_parts.append(f"evidence:{ev_reason}")
            else:
                detail_parts.append("no_alert_for_evidence_audit")

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
    if original_video:
        try:
            set_active_demo_video(token, org, original_video)
            print(f"restored active demo video -> {original_video}")
        except Exception as exc:
            print(f"WARN: could not restore demo video: {exc}")

    speed_skipped = any(
        r.get("rule") == "Démo · Excès de vitesse" and r.get("status") == "SKIPPED"
        for r in results
    )
    validated_n = len([r for r in results if r.get("status") in ("PASS", "FAIL", "SKIPPED")])
    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "pass": pass_n,
        "fail": fail_n,
        "passed_rules": pass_n,
        "total_rules": validated_n or len(RULES),
        "phase_a_mode": f"{pass_n}/5",
        "speed_deferred": speed_skipped,
        "handoff": "all_demo_rules_disabled",
        "results": results,
        "rules": _results_to_rules_map(results),
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
        "- **Vitesse:** `speeding` via traverse zone `Zone_distance_parcourue` (calibration arêtes, limite 30 km/h).",
        "- **Comptage:** compteur `Ligne_count` via API `/lines/counters`.",
        "",
        "## Notes pipeline",
        "",
        "- **Feu rouge** : nécessite `red_light_violation` (véhicule en mouvement dans Zone_Observation pendant feu rouge).",
        "  `traffic_light_state` seul ne suffit pas pour la règle.",
        "- **Vitesse** : `speeding` via timing zone `Zone_distance_parcourue` (calibration arêtes, limite 30 km/h).",
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
