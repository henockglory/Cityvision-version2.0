#!/usr/bin/env python3
"""Hyper-reactive 7-rule Frigate validation — SLO latency + evidence complete.

Order: Comptage → Intrusion → Plaque → Vitesse → Sens → Ceinture → Feu
PASS only with expected evidence (no soft missing_clip). Journal T_ALERT_MS.
"""
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
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "scripts" / "lib"))

os.environ.setdefault("ADMIN_PASSWORD", "Hologram2026!")
os.environ.setdefault("ADMIN_EMAIL", "glory.henock@hologram.cd")
os.environ.setdefault("BACKEND_API_URL", "http://127.0.0.1:8081")
os.environ.setdefault("DEMO_ORG_ID", "74d51ead-97a7-4e41-a488-503a9b90c466")
os.environ.setdefault("DEMO_MODE", "1")
os.environ.setdefault("DEMO_EVIDENCE_BACKEND", "strict_frigate")
os.environ.setdefault("RULE_PREFLIGHT_STRICT", "0")
os.environ.setdefault("INTERNAL_API_KEY", "changeme_internal_service_key")

import frigate_detect_gate as gate  # noqa: E402
import validate_demo_five_rules as v  # noqa: E402

v.API = os.environ["BACKEND_API_URL"]
v.PASS = os.environ["ADMIN_PASSWORD"]
v.EMAIL = os.environ["ADMIN_EMAIL"]
v.DEMO_ORG = os.environ["DEMO_ORG_ID"]

TIMEOUT = int(os.environ.get("RULE_TIMEOUT_SEC", "600"))
EVIDENCE_WAIT_SEC = int(os.environ.get("EVIDENCE_WAIT_SEC", "240"))
POLL = float(os.environ.get("POLL_SEC", "2"))
DISABLE_END = os.environ.get("DISABLE_END", "1") != "0"
REPORT_PATH = os.environ.get("REPORT_PATH", "/tmp/demo_1hit_seven_reactive.json")

# SLO first alert (ms). Feu = None (phase coincidence).
SPECS = [
    {
        "name": "Démo · Comptage véhicules",
        "event_types": ["line_cross"],
        "require_alert": False,
        "require_counter": True,
        "require_plate": False,
        "cabin": False,
        "geometry": False,
        "slo_ms": 10_000,
        "timeout": 180,
        "stop_parasites": False,
    },
    {
        "name": "Démo · Intrusion",
        "event_types": ["perimeter_breach"],
        "require_alert": True,
        "require_plate": False,
        "cabin": False,
        "geometry": True,
        "slo_ms": 10_000,
        "timeout": 300,
        "stop_parasites": False,
    },
    {
        "name": "Démo · Lecture plaque",
        "event_types": ["plate_detected"],
        "require_alert": True,
        "require_plate": True,
        "require_plate_text": True,
        "cabin": False,
        "geometry": False,
        "slo_ms": 10_000,
        "timeout": 300,
        "stop_parasites": False,
    },
    {
        "name": "Démo · Excès de vitesse",
        "event_types": ["speeding"],
        "require_alert": True,
        "require_plate": False,
        "cabin": False,
        "geometry": False,
        "slo_ms": 10_000,
        "timeout": 300,
        "stop_parasites": False,
    },
    {
        "name": "Démo · Sens interdit",
        "event_types": ["wrong_way"],
        "require_alert": True,
        "require_plate": False,
        "cabin": False,
        "geometry": True,
        "slo_ms": 10_000,
        "timeout": 300,
        "stop_parasites": False,
    },
    {
        "name": "Démo · Non-port ceinture Zoom",
        "event_types": ["seatbelt_violation"],
        "require_alert": True,
        "require_plate": False,
        "cabin": True,
        "geometry": False,
        "slo_ms": 15_000,
        "timeout": 420,
        "stop_parasites": False,  # Frigate cabin-local; avoid AI heal storms
    },
    {
        "name": "Démo · Feu rouge",
        "event_types": ["red_light_violation"],
        "require_alert": True,
        "require_plate": True,
        "cabin": False,
        "geometry": False,
        "slo_ms": None,  # exception — wait for red phase
        "timeout": 720,
        "stop_parasites": False,
    },
]

_VALIDATE_ONLY = [
    s.strip() for s in os.environ.get("VALIDATE_ONLY", "").split(",") if s.strip()
]
if _VALIDATE_ONLY:
    SPECS = [s for s in SPECS if any(v.lower() in s["name"].lower() for v in _VALIDATE_ONLY)]
    print(f"VALIDATE_ONLY -> {[s['name'] for s in SPECS]}", flush=True)


def sql_set_enabled(rule_id: str, enabled: bool) -> None:
    flag = "true" if enabled else "false"
    subprocess.call(
        [
            "docker", "exec", "citevision-v2-postgres",
            "psql", "-U", "citevision", "-d", "citevision", "-c",
            f"UPDATE rules SET is_enabled={flag}, updated_at=NOW() WHERE id='{rule_id}'",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def enable_only(token: str, org: str, rules: list[dict], name: str) -> dict | None:
    target = None
    for r in rules:
        want = r.get("name") == name
        already = bool(r.get("is_enabled"))
        if already == want:
            if want:
                target = r
            continue
        try:
            v.set_rule(token, org, r["id"], want)
            r["is_enabled"] = want
        except Exception:
            sql_set_enabled(r["id"], want)
            r["is_enabled"] = want
        if want:
            target = r
    return target


def event_ids(token: str, org: str, event_types: list[str]) -> set[str]:
    ids: set[str] = set()
    for et in event_types:
        try:
            rows = v.req("GET", f"{v.API}/api/v1/orgs/{org}/events?limit=100&event_type={et}", token)
        except Exception:
            continue
        if isinstance(rows, dict):
            rows = rows.get("items") or []
        for e in rows or []:
            eid = e.get("id") or e.get("event_id")
            if eid:
                ids.add(str(eid))
    return ids


def wait_api(sec: int = 120) -> bool:
    deadline = time.time() + sec
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"{v.API}/health", timeout=5) as resp:
                if resp.status == 200:
                    return True
        except Exception:
            pass
        time.sleep(2)
    return False


def safe_login() -> str:
    wait_api(180)
    return v.login_token()


def plate_text(alert: dict) -> str:
    meta = v._alert_meta(alert)
    for k in ("plate_number", "plate_text", "plate"):
        if meta.get(k):
            return str(meta[k])
    snap = alert.get("evidence_snapshot") or meta.get("evidence_snapshot") or {}
    if isinstance(snap, dict):
        pkg = snap.get("package") or snap
        if isinstance(pkg, dict):
            for k in ("plate_number", "plate_text"):
                if pkg.get(k):
                    return str(pkg[k])
    return ""


def evidence_status(alert: dict) -> str:
    meta = v._alert_meta(alert)
    snap = alert.get("evidence_snapshot") or meta.get("evidence_snapshot") or meta.get("evidence") or {}
    if isinstance(snap, str):
        try:
            snap = json.loads(snap)
        except json.JSONDecodeError:
            snap = {}
    if not isinstance(snap, dict):
        return ""
    st = str(snap.get("evidence_status") or "")
    pkg = snap.get("package") if isinstance(snap.get("package"), dict) else snap
    if isinstance(pkg, dict):
        md = pkg.get("metadata") if isinstance(pkg.get("metadata"), dict) else {}
        st = str(md.get("evidence_status") or st or "")
    return st.lower().strip()


def package_of(alert: dict) -> dict:
    meta = v._alert_meta(alert)
    snap = alert.get("evidence_snapshot") or meta.get("evidence_snapshot") or meta.get("evidence") or {}
    if isinstance(snap, str):
        try:
            snap = json.loads(snap)
        except json.JSONDecodeError:
            snap = {}
    if not isinstance(snap, dict):
        return {}
    pkg = snap.get("package") if isinstance(snap.get("package"), dict) else snap
    return pkg if isinstance(pkg, dict) else {}


def evidence_complete(alert: dict, *, cabin: bool, geometry: bool, require_plate: bool) -> tuple[bool, str]:
    st = evidence_status(alert)
    pkg = package_of(alert)
    images = pkg.get("images") or []
    roles = {str(i.get("role")) for i in images if isinstance(i, dict)}
    clip = pkg.get("clip") if isinstance(pkg.get("clip"), dict) else {}
    has_clip = bool(clip.get("url") or clip.get("asset_id"))

    if cabin:
        et = str(alert.get("event_type") or "")
        meta = alert.get("metadata") if isinstance(alert.get("metadata"), dict) else {}
        if not et:
            et = str(meta.get("event_type") or meta.get("event") or "")
        if et and et not in ("seatbelt_violation", "phone_use_violation"):
            return False, f"cabin_wrong_event_type={et}"
        if "scene" in roles and "subject" in roles:
            return True, f"cabin_complete roles={sorted(roles)}"
        return False, f"cabin_incomplete roles={sorted(roles)} status={st}"

    if geometry:
        if has_clip and "scene" in roles and "subject" in roles:
            return True, f"geometry_complete status={st}"
        ok, reason = v.alert_evidence_ok(alert, require_plate=False)
        return ok, f"geometry:{reason} status={st}"

    if st == "complete" and has_clip and "scene" in roles and "subject" in roles:
        if require_plate and "plate" not in roles and not plate_text(alert):
            ok, reason = v.alert_evidence_ok(alert, require_plate=True)
            return ok, f"road_plate:{reason}"
        return True, f"road_complete status={st}"
    ok, reason = v.alert_evidence_ok(alert, require_plate=require_plate)
    return ok, f"{reason} status={st}"


def fetch_alert(token: str, org: str, alert_id: str) -> dict | None:
    try:
        rows = v.req(
            "GET",
            f"{v.API}/api/v1/orgs/{org}/alerts?limit=50&include_incomplete=true",
            token,
        )
    except Exception:
        return None
    if isinstance(rows, dict):
        rows = rows.get("items") or []
    for a in rows or []:
        if str(a.get("id")) == str(alert_id):
            return a
    return None


def wait_evidence(
    token_box: list[str],
    org: str,
    alert: dict,
    *,
    cabin: bool,
    geometry: bool,
    require_plate: bool,
    require_plate_text: bool,
    wait_sec: int,
) -> tuple[bool, str, dict]:
    deadline = time.time() + wait_sec
    last = "waiting"
    cur = alert
    while time.time() < deadline:
        try:
            refreshed = fetch_alert(token_box[0], org, str(alert.get("id")))
            if refreshed:
                cur = refreshed
        except Exception as e:
            if "401" in str(e):
                token_box[0] = safe_login()
            time.sleep(POLL)
            continue
        if require_plate_text and not plate_text(cur):
            last = "waiting_plate_text"
            time.sleep(POLL)
            continue
        ok, reason = evidence_complete(
            cur, cabin=cabin, geometry=geometry, require_plate=require_plate
        )
        last = reason
        if ok:
            return True, reason, cur
        print(f"  … evidence {reason}", flush=True)
        time.sleep(POLL)
    return False, f"evidence_timeout:{last}", cur


def counter_delta(token: str, org: str, camera_id: str | None, baseline: int) -> int:
    if not camera_id:
        return 0
    try:
        n = v.count_line_counter(token, org, camera_id)
    except Exception:
        try:
            n = v.count_observation_counter(token, org, camera_id)
        except Exception:
            return 0
    return max(0, int(n) - int(baseline))


def write_report(path: str, *, t0: float, notes: list[str], report: list[dict]) -> None:
    out = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "protocol": "7-reactive-frigate-focus",
        "elapsed_sec": int(time.time() - t0),
        "notes": notes,
        "results": report,
        "summary": {r["rule"]: r["status"] for r in report},
    }
    Path(path).write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(line_buffering=True)

    print("=== 7-rule hyper-reactive Frigate focus ===", flush=True)
    notes: list[str] = []
    try:
        notes.extend(gate.clear_retained_detect())
        notes.extend(gate.restore_all())
    except Exception as e:
        notes.append(f"gate_clear:{e}")

    token_box = [safe_login()]
    me = v.req("GET", f"{v.API}/api/v1/auth/me", token_box[0])
    org = v.DEMO_ORG or me.get("org_id", "")
    print(f"org={org}", flush=True)

    all_rules = v.req("GET", f"{v.API}/api/v1/orgs/{org}/rules", token_box[0])
    if isinstance(all_rules, dict):
        all_rules = all_rules.get("items", [])
    demo = [r for r in (all_rules or []) if str(r.get("name", "")).startswith("Démo")]
    by_name = {r["name"]: r for r in demo}
    print(f"demo_rules={len(demo)}", flush=True)

    report: list[dict] = []
    t0 = time.time()

    for spec in SPECS:
        name = spec["name"]
        print(f"\n======== {name} ========", flush=True)
        misses: list[str] = []
        rule = by_name.get(name)
        if not rule:
            report.append({"rule": name, "status": "FAIL_NO_RULE", "detail": "missing", "t_alert_ms": None})
            continue

        try:
            v.disable_all(token_box[0], org, demo)
        except Exception:
            for r in demo:
                sql_set_enabled(r["id"], False)
        time.sleep(2)

        cam_id = v.rule_camera_id(rule)
        try:
            video_id = v.camera_video_id(token_box[0], org, cam_id) if cam_id else None
        except Exception:
            token_box[0] = safe_login()
            video_id = v.camera_video_id(token_box[0], org, cam_id) if cam_id else None
        print(f"  cam={cam_id} video={video_id}", flush=True)

        # Idle state is detect OFF everywhere — boost target BEFORE preflight
        # so Frigate MQTT frames flow for the ingest checks.
        if cam_id:
            try:
                gate.boost(cam_id)
            except Exception as e:
                print(f"WARN: pre-preflight boost: {e}", flush=True)

        pf_ok, pf_detail = v.ensure_rule_test_ready(
            token_box[0],
            org,
            name,
            camera_id=cam_id,
            video_id=video_id,
            needs_frigate=True,
            needs_phone_model=False,
        )
        if not pf_ok:
            misses.append(pf_detail)

        if video_id:
            try:
                v.set_active_demo_video(token_box[0], org, video_id)
            except Exception as e:
                misses.append(f"switch:{e}")

        boost_notes: list[str] = []
        if cam_id:
            try:
                boost_notes.extend(gate.boost(cam_id))
            except Exception as e:
                misses.append(f"boost:{e}")
            # The video switch restarts the go2rtc stream — Frigate's ffmpeg
            # can sit in retry backoff for 20-40s (run14: Intrusion alert at
            # 34s because Frigate decoded nothing at enable). Do not start the
            # SLO clock until Frigate confirms frames on the target camera.
            try:
                deadline = time.time() + 45.0
                kicked = False
                while time.time() < deadline:
                    fps = 0.0
                    try:
                        with urllib.request.urlopen(
                            "http://127.0.0.1:5000/api/stats", timeout=5
                        ) as resp:
                            stats = json.loads(resp.read().decode())
                        c = (stats.get("cameras") or {}).get(f"cv_{cam_id}") or {}
                        fps = float(c.get("camera_fps") or 0.0)
                    except Exception:
                        fps = 0.0
                    if fps > 0.5:
                        print(f"  [frigate-warm] camera_fps={fps}", flush=True)
                        break
                    if not kicked and time.time() > deadline - 30.0:
                        # Nudge ffmpeg out of backoff: enabled OFF→ON restarts it.
                        gate.publish_detect([cam_id], on=False, retain=False, kinds=("enabled",))
                        time.sleep(1.0)
                        gate.publish_detect([cam_id], on=True, retain=False, kinds=("enabled", "detect"))
                        kicked = True
                        print("  [frigate-warm] kick enabled OFF→ON (ffmpeg backoff)", flush=True)
                    time.sleep(1.5)
                else:
                    print("  [frigate-warm] WARN no frames before enable", flush=True)
            except Exception as e:
                print(f"WARN: frigate warm wait: {e}", flush=True)
            try:
                v.stop_extra_ai_cameras(cam_id)
            except Exception as e:
                print(f"WARN: stop extra AI cameras: {e}", flush=True)
        if cam_id and spec.get("stop_parasites"):
            try:
                v.stop_extra_ai_cameras(cam_id)
            except Exception as e:
                print(f"WARN: stop parasites: {e}", flush=True)

        # Baselines BEFORE enable so the first post-enable hit is not swallowed.
        baseline_alerts = set()
        baseline_events = set()
        baseline_counter = 0
        try:
            baseline_alerts = v.list_demo_alert_ids(token_box[0], org)
            baseline_events = event_ids(token_box[0], org, spec["event_types"])
            if spec.get("require_counter") and cam_id:
                try:
                    baseline_counter = v.count_line_counter(token_box[0], org, cam_id)
                except Exception:
                    baseline_counter = v.count_observation_counter(token_box[0], org, cam_id)
        except Exception:
            token_box[0] = safe_login()

        enable_only(token_box[0], org, demo, name)
        # SLO clock: first alert after enable (plan non-négociable).
        enable_t0 = time.time()
        # Re-boost in background — never block the poll loop.
        if cam_id:
            import threading

            def _bg_boost(cid: str = cam_id) -> None:
                try:
                    # Geometry + counter: immediate OFF→ON re-creates every visible
                    # track so enter/cross edges fire under the enabled rule. With
                    # the pre-enable warm wait the camera is already decoding, so
                    # established tracks would otherwise never re-enter (run15:
                    # Comptage 64s waiting for genuinely new cars).
                    if (spec.get("geometry") or spec.get("require_counter")) and not spec.get("require_plate") and not spec.get("cabin"):
                        try:
                            gate.publish_detect([cid], on=False, retain=False)
                            time.sleep(0.25)
                            gate.publish_detect([cid], on=True, retain=False)
                        except Exception:
                            pass
                    gate.boost(cid)
                except Exception as e:
                    print(f"WARN: boost2: {e}", flush=True)

            threading.Thread(target=_bg_boost, daemon=True).start()

        # Second kick wave at +5s if no alert yet: the immediate kick can land
        # while Frigate still resumes old tracks (0.25s detect gap is short).
        if (spec.get("geometry") or spec.get("require_counter")) and not spec.get("cabin"):
            geom_kick_deadline = enable_t0 + 5.0
            geom_kicked = False
        else:
            geom_kick_deadline = None
            geom_kicked = True  # immediate kick already scheduled in _bg_boost

        rule_timeout = int(spec.get("timeout") or TIMEOUT)
        deadline = enable_t0 + rule_timeout
        alert_hit = None
        t_alert_ms: int | None = None
        new_events = 0
        status = "FAIL_NO_ALERT"
        detail = "no alert"
        hit = False

        while time.time() < deadline and not hit:
            if (
                geom_kick_deadline is not None
                and not geom_kicked
                and time.time() >= geom_kick_deadline
            ):
                geom_kicked = True

                def _geom_kick(cid: str = cam_id) -> None:
                    try:
                        gate.publish_detect([cid], on=False, retain=False)
                        time.sleep(0.25)
                        gate.publish_detect([cid], on=True, retain=False)
                        gate.boost(cid)
                        print("  [kick] deferred geometry detect OFF→ON", flush=True)
                    except Exception as e:
                        print(f"WARN: geom kick: {e}", flush=True)

                threading.Thread(target=_geom_kick, daemon=True).start()

            time.sleep(POLL)
            try:
                if spec.get("require_counter"):
                    delta = counter_delta(token_box[0], org, cam_id, baseline_counter)
                    if delta > 0:
                        t_alert_ms = int((time.time() - enable_t0) * 1000)
                        hit = True
                        detail = f"HIT_COUNTER delta={delta}"
                        print(f"  {detail} t_alert_ms={t_alert_ms}", flush=True)
                        break
                now_events = event_ids(token_box[0], org, spec["event_types"])
                new_events = len(now_events - baseline_events)
                new_alert_ids = v.list_demo_alert_ids(token_box[0], org) - baseline_alerts
            except Exception as e:
                if "401" in str(e):
                    token_box[0] = safe_login()
                continue

            if spec.get("require_alert") and new_alert_ids:
                rows = v.req(
                    "GET",
                    f"{v.API}/api/v1/orgs/{org}/alerts?limit=50&include_incomplete=true",
                    token_box[0],
                )
                if isinstance(rows, dict):
                    rows = rows.get("items") or []
                matched = [
                    a for a in (rows or [])
                    if str(a.get("id")) in new_alert_ids
                    and str(a.get("rule_id") or "") == str(rule["id"])
                ]
                # Also accept title/rule_name match when rule_id missing on payload.
                if not matched:
                    matched = [
                        a for a in (rows or [])
                        if str(a.get("id")) in new_alert_ids
                        and name in str(a.get("title") or a.get("rule_name") or "")
                    ]
                if matched:
                    alert_hit = matched[0]
                    t_alert_ms = int((time.time() - enable_t0) * 1000)
                    hit = True
                    detail = f"HIT_ALERT alert={alert_hit['id'][:8]}"
                    print(f"  {detail} t_alert_ms={t_alert_ms}", flush=True)
                    break

            elapsed = int(time.time() - enable_t0)
            if elapsed and elapsed % 30 < POLL:
                print(f"  … {elapsed}s events={new_events}", flush=True)

        slo = spec.get("slo_ms")
        slow = bool(slo is not None and t_alert_ms is not None and t_alert_ms > int(slo))

        if spec.get("require_counter") and hit:
            status = "FAIL_SLOW" if slow else "PASS"
            detail = f"{status} counter t_alert_ms={t_alert_ms} slo={slo}"
        elif hit and alert_hit and not spec.get("require_counter"):
            ok, reason, alert_hit = wait_evidence(
                token_box,
                org,
                alert_hit,
                cabin=bool(spec.get("cabin")),
                geometry=bool(spec.get("geometry")),
                require_plate=bool(spec.get("require_plate")),
                require_plate_text=bool(spec.get("require_plate_text")),
                wait_sec=EVIDENCE_WAIT_SEC,
            )
            if ok:
                if slow:
                    status = "FAIL_SLOW"
                    detail = f"FAIL_SLOW evidence_ok t_alert_ms={t_alert_ms} slo={slo} ev={reason}"
                else:
                    status = "PASS"
                    detail = f"PASS t_alert_ms={t_alert_ms} ev={reason} plate={plate_text(alert_hit)!r}"
            else:
                # one heal retry
                misses.append(f"evidence_first:{reason}")
                try:
                    v.trigger_ingest_resync()
                except Exception:
                    pass
                if cam_id:
                    try:
                        gate.boost(cam_id)
                    except Exception:
                        pass
                ok2, reason2, alert2 = wait_evidence(
                    token_box,
                    org,
                    alert_hit,
                    cabin=bool(spec.get("cabin")),
                    geometry=bool(spec.get("geometry")),
                    require_plate=bool(spec.get("require_plate")),
                    require_plate_text=bool(spec.get("require_plate_text")),
                    wait_sec=min(120, EVIDENCE_WAIT_SEC),
                )
                if ok2:
                    alert_hit = alert2
                    status = "FAIL_SLOW" if slow else "PASS_AFTER_HEAL"
                    detail = f"{status} t_alert_ms={t_alert_ms} ev={reason2}"
                else:
                    status = "FAIL_EVIDENCE"
                    detail = f"FAIL_EVIDENCE t_alert_ms={t_alert_ms} {reason2}"
        else:
            status = "FAIL_NO_ALERT"
            detail = f"no hit after {rule_timeout}s events={new_events}"

        try:
            gate.restore_all()
        except Exception:
            pass

        entry = {
            "rule": name,
            "status": status,
            "detail": detail,
            "t_alert_ms": t_alert_ms,
            "slo_ms": slo,
            "misses": misses,
            "boost_notes": boost_notes,
            "events": new_events,
            "alert_id": (alert_hit or {}).get("id"),
            "plate_text": plate_text(alert_hit) if alert_hit else "",
            "evidence_status": evidence_status(alert_hit) if alert_hit else "",
            "camera_id": cam_id,
            "video_id": video_id,
            "preflight": pf_detail,
        }
        report.append(entry)
        write_report(REPORT_PATH, t0=t0, notes=notes, report=report)
        print(f"{status}: {detail}", flush=True)
        if misses:
            print(f"  misses={misses}", flush=True)

    if DISABLE_END:
        print("\n=== disable all demo rules (1B) ===", flush=True)
        try:
            v.disable_all(token_box[0], org, demo)
        except Exception:
            subprocess.call(
                [
                    "docker", "exec", "citevision-v2-postgres",
                    "psql", "-U", "citevision", "-d", "citevision", "-c",
                    "UPDATE rules SET is_enabled=false WHERE name LIKE 'Démo%'",
                ]
            )

    try:
        notes.extend(gate.clear_retained_detect())
        notes.extend(gate.restore_all())
    except Exception as e:
        notes.append(f"gate_end:{e}")

    write_report(REPORT_PATH, t0=t0, notes=notes, report=report)
    print(f"\nreport: {REPORT_PATH}", flush=True)
    for r in report:
        print(
            f"  {r['status']:18} t={r.get('t_alert_ms')}ms  {r['rule']}",
            flush=True,
        )

    fails = sum(1 for r in report if not str(r["status"]).startswith("PASS"))
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
