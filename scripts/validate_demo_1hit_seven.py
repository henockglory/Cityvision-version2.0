#!/usr/bin/env python3
"""1-hit validation for the 7 demo rules (plan validation finale).

Sequential: one rule enabled at a time. Logs misses/causes. Leaves rules
disabled at the end when --disable-end is set (default for plan 1B).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

API = os.environ.get("BACKEND_API_URL", "http://127.0.0.1:8081")
AI = os.environ.get("AI_ENGINE_URL", "http://127.0.0.1:8001")
RE = os.environ.get("RULES_ENGINE_URL", "http://127.0.0.1:8010")
EMAIL = os.environ.get("ADMIN_EMAIL", "glory.henock@hologram.cd")
PASS = os.environ.get("ADMIN_PASSWORD", "Hologram2026!")
ORG = os.environ.get("DEMO_ORG_ID", "74d51ead-97a7-4e41-a488-503a9b90c466")
TIMEOUT = int(os.environ.get("RULE_TIMEOUT_SEC", "240"))
POLL = float(os.environ.get("POLL_SEC", "8"))
DISABLE_END = os.environ.get("DISABLE_END", "1") != "0"
VALIDATE_ONLY = [
    s.strip() for s in os.environ.get("VALIDATE_ONLY", "").split(",") if s.strip()
]

# Order from plan Phase D.
SPECS = [
    {
        "name": "Démo · Comptage véhicules",
        "event_types": ["line_cross"],
        "require_alert": False,
        "require_counter": True,
        "camera_hint": "décompte",
    },
    {
        "name": "Démo · Feu rouge",
        "event_types": ["red_light_violation"],
        "require_alert": True,
        "camera_hint": "feux",
    },
    {
        "name": "Démo · Excès de vitesse",
        "event_types": ["speeding"],
        "require_alert": True,
        "camera_hint": "ligne continue",
    },
    {
        "name": "Démo · Lecture plaque",
        "event_types": ["plate_detected"],
        "require_alert": True,
        "require_plate_text": True,
        "camera_hint": "okapi",
    },
    {
        "name": "Démo · Intrusion",
        "event_types": ["perimeter_breach"],
        "require_alert": True,
        "camera_hint": "in_out",
    },
    {
        "name": "Démo · Sens interdit",
        "event_types": ["wrong_way"],
        "require_alert": True,
        "camera_hint": "entree_hologram",
    },
    {
        "name": "Démo · Non-port ceinture Zoom",
        "event_types": ["seatbelt_violation"],
        "require_alert": True,
        "camera_hint": "zoom_entree",
    },
]


def req(method: str, url: str, token: str | None = None, body: dict | None = None, timeout: int = 60):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(r, timeout=timeout) as resp:
        raw = resp.read().decode()
        return json.loads(raw) if raw else {}


def soft_health() -> list[str]:
    notes: list[str] = []
    try:
        req("GET", f"{API}/health")
    except Exception as e:
        notes.append(f"API down: {e}")
    try:
        ai = req("GET", f"{AI}/health")
        for k in ("yolo_loaded", "plate_loaded"):
            if str(ai.get(k, "")).lower() != "true":
                notes.append(f"AI {k}!=true")
        for k in ("seatbelt_model_loaded",):
            if str(ai.get(k, "")).lower() != "true":
                notes.append(f"WARN AI {k}!=true (VLM may still judge)")
    except Exception as e:
        notes.append(f"AI down: {e}")
    try:
        re = req("GET", f"{RE}/health")
        notes.append(f"rules-engine ok active={re.get('active_rules', re)}")
    except Exception as e:
        notes.append(f"rules-engine: {e}")
    return notes


def list_ai_cameras() -> list[dict]:
    try:
        d = req("GET", f"{AI}/cameras")
    except Exception:
        return []
    if isinstance(d, list):
        return d
    if isinstance(d, dict):
        return d.get("cameras") or d.get("items") or []
    return []


def stop_all_ai_cameras() -> None:
    for c in list_ai_cameras():
        cid = c.get("camera_id") or c.get("id")
        if not cid:
            continue
        try:
            req("POST", f"{AI}/cameras/{cid}/stop")
        except Exception:
            pass


def build_spatial_for_camera(token: str, camera_id: str) -> dict:
    zones = req("GET", f"{API}/api/v1/orgs/{ORG}/zones", token)
    lines = req("GET", f"{API}/api/v1/orgs/{ORG}/lines", token)
    if isinstance(zones, dict):
        zones = zones.get("items", zones)
    if isinstance(lines, dict):
        lines = lines.get("items", lines)
    zone_list = []
    for z in zones or []:
        if z.get("camera_id") != camera_id:
            continue
        if z.get("is_active") is False:
            continue
        bc = z.get("behavior_config") or {}
        if isinstance(bc, str):
            try:
                bc = json.loads(bc)
            except json.JSONDecodeError:
                bc = {}
        zone_list.append(
            {
                "zone_id": z.get("name"),
                "name": z.get("name"),
                "zone_kind": z.get("zone_kind") or "",
                "behavior": bc.get("behavior") or z.get("zone_kind") or "",
                "behavior_config": bc.get("config") or {},
                "polygon": z.get("polygon") or [],
            }
        )
    line_list = []
    for line in lines or []:
        if line.get("camera_id") != camera_id:
            continue
        line_list.append(
            {
                "line_id": line.get("name"),
                "name": line.get("name"),
                "start": line.get("start") or line.get("start_point"),
                "end": line.get("end") or line.get("end_point"),
                "direction": line.get("direction") or "unknown",
            }
        )
    return {"zones": zone_list, "lines": line_list}


def start_mono_camera(token: str, camera_id: str, video_file: str) -> dict:
    stop_all_ai_cameras()
    time.sleep(2)
    spatial = build_spatial_for_camera(token, camera_id)
    body = {
        "org_id": ORG,
        "video_file": video_file,
        "ai_fps": 8,
        "spatial_rules": spatial,
    }
    out = req("POST", f"{AI}/cameras/{camera_id}/start", body=body)
    print(
        f"  mono-start cam={camera_id[:8]} zones={[z.get('behavior') for z in spatial.get('zones', [])]} "
        f"lines={[ln.get('line_id') for ln in spatial.get('lines', [])]}"
    )
    return out if isinstance(out, dict) else {}


def resolve_camera(token: str, hint: str, rule: dict) -> tuple[str, str]:
    """Return (camera_id, video_file)."""
    cams = req("GET", f"{API}/api/v1/orgs/{ORG}/cameras", token)
    if isinstance(cams, dict):
        cams = cams.get("items", cams)
    hint_l = hint.lower()
    best = None
    best_len = 10**9
    for c in cams or []:
        name = str(c.get("name") or "").lower()
        if hint_l in name and len(name) < best_len:
            best = c
            best_len = len(name)
    if not best:
        # fallback rule binding
        defn = rule.get("definition") or {}
        cid = defn.get("camera_id") or (defn.get("bindings") or {}).get("camera_id")
        return str(cid or ""), ""
    meta = best.get("metadata") or {}
    if isinstance(meta, str):
        try:
            meta = json.loads(meta)
        except json.JSONDecodeError:
            meta = {}
    video = str(meta.get("video_file") or meta.get("local_path") or "")
    return str(best["id"]), video


def login() -> str:
    return req("POST", f"{API}/api/v1/auth/login", body={"email": EMAIL, "password": PASS})["access_token"]


def list_rules(token: str) -> list[dict]:
    rows = req("GET", f"{API}/api/v1/orgs/{ORG}/rules", token)
    if isinstance(rows, dict):
        rows = rows.get("items", [])
    return rows if isinstance(rows, list) else []


def set_enabled(token: str, rule: dict, enabled: bool) -> None:
    rid = rule["id"]
    body = {"is_enabled": enabled}
    url = f"{API}/api/v1/orgs/{ORG}/rules/{rid}?skip_preflight=1&wait_preflight=0"
    try:
        req("PATCH", url, token, body)
        return
    except Exception as api_err:
        # Persist-safe fallback: direct SQL when API flaps (watchdog/restart).
        flag = "true" if enabled else "false"
        cmd = (
            "docker exec citevision-v2-postgres psql -U citevision -d citevision -c "
            f"\"UPDATE rules SET is_enabled={flag}, updated_at=NOW() WHERE id='{rid}'\""
        )
        try:
            subprocess.check_call(["bash", "-lc", cmd], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            print(f"  SQL fallback is_enabled={enabled} for {rule.get('name')}")
        except Exception as sql_err:
            raise RuntimeError(f"api={api_err}; sql={sql_err}") from sql_err


def ensure_api(token_holder: dict) -> str:
    """Re-login if API was restarted mid-run."""
    try:
        req("GET", f"{API}/health")
        return token_holder["token"]
    except Exception:
        time.sleep(3)
        try:
            req("GET", f"{API}/health")
        except Exception:
            # best-effort start hint only
            print("  WARN API down — waiting up to 45s")
            for _ in range(15):
                time.sleep(3)
                try:
                    req("GET", f"{API}/health")
                    break
                except Exception:
                    continue
        token_holder["token"] = login()
        print("  re-login after API heal")
        return token_holder["token"]


def disable_all(token: str, rules: list[dict]) -> None:
    for r in rules:
        if r.get("is_enabled"):
            try:
                set_enabled(token, r, False)
            except Exception as e:
                print(f"  warn disable {r.get('name')}: {e}")


def enable_only(token: str, rules: list[dict], name: str) -> dict | None:
    target = None
    for r in rules:
        want = r.get("name") == name
        try:
            set_enabled(token, r, want)
        except Exception as e:
            print(f"  warn set {r.get('name')} enabled={want}: {e}")
        if want:
            target = r
    return target


def _meta(a: dict) -> dict:
    m = a.get("metadata") or {}
    if isinstance(m, str):
        try:
            m = json.loads(m)
        except json.JSONDecodeError:
            m = {}
    return m


def fetch_alerts(token: str) -> list[dict]:
    rows = req("GET", f"{API}/api/v1/orgs/{ORG}/alerts?limit=200&include_incomplete=true", token)
    if isinstance(rows, dict):
        rows = rows.get("items", [])
    return rows if isinstance(rows, list) else []


def fetch_events(token: str, et: str) -> list[dict]:
    try:
        rows = req("GET", f"{API}/api/v1/orgs/{ORG}/events?limit=100&event_type={et}", token)
    except Exception:
        return []
    if isinstance(rows, dict):
        rows = rows.get("items", [])
    return rows if isinstance(rows, list) else []


def counter_value(token: str, rule_id: str, camera_id: str | None = None) -> int:
    # Observation counters API
    try:
        q = f"{API}/api/v1/orgs/{ORG}/counters"
        if camera_id:
            q += f"?camera_id={camera_id}"
        rows = req("GET", q, token)
        if isinstance(rows, list):
            total = 0
            for row in rows:
                if str(row.get("rule_id") or "") in ("", rule_id) or row.get("kind") == "line_cross":
                    total += int(row.get("value") or row.get("count") or 0)
            if total:
                return total
        if isinstance(rows, dict) and "value" in rows:
            return int(rows.get("value") or 0)
    except Exception:
        pass
    # Fallback: rule_counters via events volume is handled by caller.
    return -1


def event_ids(token: str, event_types: list[str]) -> set[str]:
    ids: set[str] = set()
    for et in event_types:
        for e in fetch_events(token, et):
            eid = e.get("id") or e.get("event_id")
            if eid:
                ids.add(str(eid))
    return ids


def evidence_roles(alert: dict) -> list[str]:
    snap = alert.get("evidence_snapshot") or {}
    if isinstance(snap, str):
        try:
            snap = json.loads(snap)
        except json.JSONDecodeError:
            snap = {}
    roles: list[str] = []
    images = snap.get("images") or snap.get("artifacts") or []
    pkg = snap.get("package") or {}
    if isinstance(pkg, dict):
        images = list(images) + list(pkg.get("images") or [])
        if pkg.get("clip") or (isinstance(pkg.get("clip"), dict) and pkg["clip"].get("url")):
            roles.append("clip")
    for im in images:
        if isinstance(im, dict):
            roles.append(str(im.get("role") or im.get("kind") or ""))
    if snap.get("clip") or snap.get("clip_url") or snap.get("video_url"):
        roles.append("clip")
    # Unique preserve order
    out: list[str] = []
    for r in roles:
        if r and r not in out:
            out.append(r)
    return out


def plate_text_from(alert: dict, events: list[dict]) -> str:
    m = _meta(alert)
    for k in ("plate_number", "plate_text", "plate"):
        v = m.get(k)
        if v:
            return str(v)
    snap = alert.get("evidence_snapshot") or {}
    if isinstance(snap, dict):
        for k in ("plate_number", "plate_text"):
            if snap.get(k):
                return str(snap[k])
        for im in snap.get("images") or []:
            if isinstance(im, dict) and im.get("role") == "plate" and im.get("text"):
                return str(im["text"])
    for e in events:
        p = e.get("payload") or e.get("metadata") or {}
        if isinstance(p, str):
            try:
                p = json.loads(p)
            except json.JSONDecodeError:
                p = {}
        for k in ("plate_number", "plate_text", "plate"):
            if p.get(k):
                return str(p[k])
            md = p.get("metadata") or {}
            if isinstance(md, dict) and md.get(k):
                return str(md[k])
    return ""


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(line_buffering=True)

    notes = soft_health()
    print("preflight:", "; ".join(notes) or "ok")
    token_holder = {"token": login()}
    token = token_holder["token"]
    rules = list_rules(token)
    demo = [r for r in rules if str(r.get("name", "")).startswith("Démo")]
    by_name = {r["name"]: r for r in demo}
    print(f"demo_rules={len(demo)} org={ORG}")

    report: list[dict] = []
    t0_all = time.time()

    for spec in SPECS:
        name = spec["name"]
        if VALIDATE_ONLY and name not in VALIDATE_ONLY:
            continue
        print(f"\n=== {name} ===")
        misses: list[str] = []
        token = ensure_api(token_holder)
        rules = list_rules(token)
        demo = [r for r in rules if str(r.get("name", "")).startswith("Démo")]
        by_name = {r["name"]: r for r in demo}
        rule = by_name.get(name)
        if not rule:
            report.append({"rule": name, "status": "FAIL", "detail": "rule missing", "misses": ["missing_rule"]})
            print("FAIL: rule missing")
            continue

        # Attempt 1: enable only this rule + mono-camera ingest (avoids VLM queue flood).
        disable_all(token, demo)
        time.sleep(3)
        token = ensure_api(token_holder)
        enable_only(token, demo, name)
        time.sleep(5)

        # Refresh rule object
        token = ensure_api(token_holder)
        rules = list_rules(token)
        demo = [r for r in rules if str(r.get("name", "")).startswith("Démo")]
        by_name = {r["name"]: r for r in demo}
        rule = by_name[name]
        if not rule.get("is_enabled"):
            misses.append("enable_failed_api")
            print("WARN: is_enabled still false after toggle")

        cam_id, video = resolve_camera(token, spec.get("camera_hint", ""), rule)
        if cam_id and video:
            try:
                start_mono_camera(token, cam_id, video)
                misses.append("mono_camera_start")  # informational breadcrumb, not a fail
            except Exception as e:
                misses.append(f"mono_start_failed:{e}")
                print(f"  WARN mono-start failed: {e}")
        else:
            misses.append("no_camera_video_resolved")
            print(f"  WARN no camera/video for hint={spec.get('camera_hint')}")

        baseline_alerts = {a["id"] for a in fetch_alerts(token)}
        baseline_event_ids = event_ids(token, spec["event_types"])
        baseline_ts = datetime.now(timezone.utc).isoformat()
        c0 = counter_value(token, rule["id"], cam_id or None) if spec.get("require_counter") else 0

        hit = False
        detail = ""
        alert_hit = None
        new_events = 0
        deadline = time.time() + TIMEOUT
        attempt = 1

        while time.time() < deadline and not hit:
            time.sleep(POLL)
            try:
                token = ensure_api(token_holder)
            except Exception as e:
                misses.append(f"api_down:{e}")
                continue
            # Events (id-diff — robust vs timestamp format)
            now_ids = event_ids(token, spec["event_types"])
            new_ids = now_ids - baseline_event_ids
            new_events = len(new_ids)
            latest_events = []
            for et in spec["event_types"]:
                latest_events.extend(fetch_events(token, et))

            if spec.get("require_counter"):
                c1 = counter_value(token, rule["id"], cam_id or None)
                if (c1 >= 0 and c0 >= 0 and c1 > c0) or new_events >= 1:
                    hit = True
                    detail = f"counter {c0}->{c1} new_events={new_events}"
                    break

            alerts = fetch_alerts(token)
            new_alerts = [a for a in alerts if a["id"] not in baseline_alerts]
            # Prefer alerts for this rule
            matched = [a for a in new_alerts if str(a.get("rule_id")) == str(rule["id"])]
            if not matched:
                # also accept by event type in metadata
                matched = [
                    a
                    for a in new_alerts
                    if any(
                        et in str(_meta(a).get("event_type") or a.get("title") or "")
                        for et in spec["event_types"]
                    )
                ]
            if matched:
                alert_hit = matched[0]
                roles = evidence_roles(alert_hit)
                plate = plate_text_from(alert_hit, latest_events)
                if spec.get("require_alert") is False and not spec.get("require_counter"):
                    hit = True
                elif spec.get("require_alert", True):
                    hit = True
                    detail = f"alert={alert_hit['id'][:8]} roles={roles} plate={plate!r} events={new_events}"
                    if spec.get("require_plate_text") and not plate:
                        misses.append("alert_without_plate_text")
                        # keep waiting for a better alert with plate text
                        hit = False
                        detail += " (waiting plate text)"
                        continue
                break

            elapsed = int(time.time() - (deadline - TIMEOUT))
            if elapsed and elapsed % 40 < POLL:
                print(f"  … waiting {elapsed}s events={new_events} new_alerts={len(new_alerts)}")

        if not hit and attempt == 1:
            misses.append(f"timeout_{TIMEOUT}s_no_hit")
            # Soft heal: re-push spatial for hint camera + retry half timeout once
            print("  MISS attempt1 — soft heal: resync-spatial + short retry")
            try:
                urllib.request.urlopen(
                    urllib.request.Request(
                        f"{API}/api/v1/internal/ingest/resync-spatial",
                        method="POST",
                        headers={"X-Internal-Key": os.environ.get("INTERNAL_API_KEY", "changeme_internal_service_key")},
                    ),
                    timeout=30,
                ).read()
            except Exception as e:
                misses.append(f"resync_failed:{e}")
            time.sleep(8)
            baseline_alerts = {a["id"] for a in fetch_alerts(token)}
            baseline_event_ids = event_ids(token, spec["event_types"])
            baseline_ts = datetime.now(timezone.utc).isoformat()
            deadline2 = time.time() + min(120, TIMEOUT // 2)
            while time.time() < deadline2 and not hit:
                time.sleep(POLL)
                now_ids = event_ids(token, spec["event_types"])
                new_events = len(now_ids - baseline_event_ids)
                if spec.get("require_counter") and new_events >= 1:
                    hit = True
                    detail = f"heal new_events={new_events}"
                    misses.append("needed_resync_heal")
                    break
                if spec.get("require_counter"):
                    c1 = counter_value(token, rule["id"], cam_id or None)
                    if c1 >= 0 and c0 >= 0 and c1 > c0:
                        hit = True
                        detail = f"counter heal {c0}->{c1}"
                        misses.append("needed_resync_heal")
                        break
                alerts = fetch_alerts(token)
                new_alerts = [a for a in alerts if a["id"] not in baseline_alerts]
                matched = [a for a in new_alerts if str(a.get("rule_id")) == str(rule["id"])]
                if matched:
                    alert_hit = matched[0]
                    roles = evidence_roles(alert_hit)
                    plate = plate_text_from(alert_hit, [])
                    if not (spec.get("require_plate_text") and not plate):
                        hit = True
                        detail = f"heal alert={alert_hit['id'][:8]} roles={roles} plate={plate!r}"
                        misses.append("needed_resync_heal")
                        break

        status = "PASS" if hit else "FAIL"
        real_misses = [m for m in misses if m not in ("mono_camera_start",) and not m.startswith("mono_camera")]
        if hit and any(m.startswith("needed_") or m.endswith("_heal") for m in real_misses):
            status = "PASS_AFTER_HEAL"
        entry = {
            "rule": name,
            "status": status,
            "detail": detail or ("no event/alert" if not hit else detail),
            "misses": real_misses,
            "events": new_events,
            "alert_id": (alert_hit or {}).get("id"),
            "evidence_roles": evidence_roles(alert_hit) if alert_hit else [],
            "plate_text": plate_text_from(alert_hit, []) if alert_hit else "",
        }
        report.append(entry)
        print(f"{status}: {entry['detail']} misses={real_misses}")

    if DISABLE_END:
        print("\n=== disable all demo rules (1B) ===")
        try:
            token = ensure_api(token_holder)
            rules = list_rules(token)
            demo = [r for r in rules if str(r.get("name", "")).startswith("Démo")]
            disable_all(token, demo)
        except Exception as e:
            print(f"  WARN disable API failed ({e}) — SQL fallback")
            subprocess.call(
                [
                    "bash",
                    "-lc",
                    "docker exec citevision-v2-postgres psql -U citevision -d citevision "
                    "-c \"UPDATE rules SET is_enabled=false WHERE name LIKE 'Démo%';\"",
                ]
            )

    out_path = os.environ.get("REPORT_PATH", "/tmp/demo_1hit_report.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"generated_at": datetime.now(timezone.utc).isoformat(), "elapsed_sec": int(time.time() - t0_all), "results": report}, f, ensure_ascii=False, indent=2)
    print(f"\nreport: {out_path}")
    for r in report:
        print(f"  {r['status']:16} {r['rule']}")

    fails = sum(1 for r in report if not str(r["status"]).startswith("PASS"))
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
