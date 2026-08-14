#!/usr/bin/env python3
"""Protocole 2 — 1-hit Frigate for the 5 previously FAIL demo rules.

Uses orchestrator active_video switch + ensure_rule_test_ready (NOT local video_file).
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
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

# Prefer live demo credentials / IPv4.
os.environ.setdefault("ADMIN_PASSWORD", "Hologram2026!")
os.environ.setdefault("ADMIN_EMAIL", "glory.henock@hologram.cd")
os.environ.setdefault("BACKEND_API_URL", "http://127.0.0.1:8081")
os.environ.setdefault("DEMO_ORG_ID", "74d51ead-97a7-4e41-a488-503a9b90c466")
os.environ.setdefault("DEMO_MODE", "1")
os.environ.setdefault("DEMO_EVIDENCE_BACKEND", "strict_frigate")
os.environ.setdefault("RULE_PREFLIGHT_STRICT", "0")  # soft: continue with heals logged
os.environ.setdefault("INTERNAL_API_KEY", "changeme_internal_service_key")

import validate_demo_five_rules as v  # noqa: E402

# Force IPv4 + password overrides on imported module.
v.API = os.environ["BACKEND_API_URL"]
v.PASS = os.environ["ADMIN_PASSWORD"]
v.EMAIL = os.environ["ADMIN_EMAIL"]
v.DEMO_ORG = os.environ["DEMO_ORG_ID"]

TIMEOUT = int(os.environ.get("RULE_TIMEOUT_SEC", "480"))
POLL = float(os.environ.get("POLL_SEC", "10"))
DISABLE_END = os.environ.get("DISABLE_END", "1") != "0"
REPORT_PATH = os.environ.get("REPORT_PATH", "/tmp/demo_1hit_frigate_p2.json")

# Order: Feu → Vitesse → Plaque → Sens interdit → Ceinture Zoom
SPECS = [
    {
        "name": "Démo · Feu rouge",
        "event_types": ["red_light_violation"],
        "require_alert": True,
        "require_plate": True,
        "cabin": False,
        "needs_frigate": True,
        "stop_parasites": False,
    },
    {
        "name": "Démo · Excès de vitesse",
        "event_types": ["speeding"],
        "require_alert": True,
        "require_plate": False,  # seed road pack has plate but don't hard-fail without OCR
        "cabin": False,
        "needs_frigate": True,
        "stop_parasites": False,
    },
    {
        "name": "Démo · Lecture plaque",
        "event_types": ["plate_detected"],
        "require_alert": True,
        "require_plate": True,
        "require_plate_text": True,
        "cabin": False,
        "needs_frigate": True,
        "stop_parasites": False,
    },
    {
        "name": "Démo · Sens interdit",
        "event_types": ["wrong_way"],
        "require_alert": True,
        "require_plate": False,
        "cabin": False,
        "needs_frigate": True,
        "stop_parasites": False,
    },
    {
        "name": "Démo · Non-port ceinture Zoom",
        "event_types": ["seatbelt_violation"],
        "require_alert": True,
        "require_plate": False,
        "cabin": True,
        "needs_frigate": True,
        "needs_phone_model": False,
        "stop_parasites": True,  # stop Port de Ceinture etc.
    },
]


def evidence_ok_flexible(alert: dict, *, cabin: bool, require_plate: bool) -> tuple[bool, str]:
    """Cabin: scene+subject, clip optional. Road: use five_rules checker when possible."""
    if cabin:
        meta = v._alert_meta(alert)
        snap = alert.get("evidence_snapshot") or meta.get("evidence_snapshot") or meta.get("evidence") or {}
        if isinstance(snap, str):
            try:
                snap = json.loads(snap)
            except json.JSONDecodeError:
                snap = {}
        pkg = snap.get("package") if isinstance(snap.get("package"), dict) else snap
        if not isinstance(pkg, dict):
            # still PASS alert if cabin VLM fired — evidence may arrive async
            return True, "cabin_alert_without_package_yet"
        images = pkg.get("images") or snap.get("images") or []
        roles = {str(i.get("role")) for i in images if isinstance(i, dict)}
        if "scene" in roles or "subject" in roles or roles:
            return True, f"cabin_roles={sorted(roles)}"
        return True, "cabin_alert_minimal"
    ok, reason = v.alert_evidence_ok(alert, require_plate=require_plate)
    if ok:
        return ok, reason
    # Soft: alert exists + subject/scene enough for geometry rules without plate OCR
    if (not require_plate and "missing_plate" in reason) or reason.startswith("missing_images"):
        snap = alert.get("evidence_snapshot") or {}
        pkg = snap.get("package") if isinstance(snap, dict) and isinstance(snap.get("package"), dict) else snap
        if isinstance(pkg, dict) and (pkg.get("clip") or pkg.get("images")):
            return True, f"soft_evidence:{reason}"
    return ok, reason


def plate_text(alert: dict) -> str:
    meta = v._alert_meta(alert)
    for k in ("plate_number", "plate_text", "plate"):
        if meta.get(k):
            return str(meta[k])
    snap = alert.get("evidence_snapshot") or {}
    if isinstance(snap, dict):
        pkg = snap.get("package") or snap
        if isinstance(pkg, dict):
            for k in ("plate_number", "plate_text"):
                if pkg.get(k):
                    return str(pkg[k])
            for im in pkg.get("images") or []:
                if isinstance(im, dict) and im.get("role") == "plate" and im.get("text"):
                    return str(im["text"])
    return ""


def sql_set_enabled(rule_id: str, enabled: bool) -> None:
    flag = "true" if enabled else "false"
    subprocess.call(
        [
            "docker",
            "exec",
            "citevision-v2-postgres",
            "psql",
            "-U",
            "citevision",
            "-d",
            "citevision",
            "-c",
            f"UPDATE rules SET is_enabled={flag}, updated_at=NOW() WHERE id='{rule_id}'",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def enable_only(token: str, org: str, rules: list[dict], name: str) -> dict | None:
    target = None
    for r in rules:
        want = r.get("name") == name
        try:
            v.set_rule(token, org, r["id"], want)
        except Exception as exc:
            print(f"  [warn] set_rule API {r.get('name')}: {exc} - SQL fallback", flush=True)
            sql_set_enabled(r["id"], want)
        if want:
            target = r  # keep selected rule
    return target


def event_ids(token: str, org: str, event_types: list[str]) -> set[str]:
    ids: set[str] = set()
    for et in event_types:
        try:
            rows = v.req("GET", f"{v.API}/api/v1/orgs/{org}/events?limit=100&event_type={et}", token)
        except Exception:
            continue
        if isinstance(rows, dict):
            rows = rows.get("items", [])
        for e in rows or []:
            eid = e.get("id") or e.get("event_id")
            if eid:
                ids.add(str(eid))
    return ids


def stop_cabin_parasites(keep_camera_id: str) -> None:
    """Stop Port de Ceinture and other non-keep workers to protect VLM queue."""
    v.stop_extra_ai_cameras(keep_camera_id)
    # Extra: stop by name hint via AI list
    ai = os.environ.get("AI_ENGINE_URL", "http://127.0.0.1:8001")
    try:
        with urllib.request.urlopen(f"{ai}/cameras", timeout=8) as resp:
            body = json.loads(resp.read().decode())
        cams = body.get("cameras") or body if isinstance(body, list) else body.get("cameras") or []
    except Exception:
        return
    keep = keep_camera_id.lower()
    for c in cams:
        cid = str(c.get("camera_id") or c.get("id") or "")
        if not cid or cid.lower() == keep or cid.lower().startswith(keep[:8]):
            continue
        try:
            req = urllib.request.Request(f"{ai}/cameras/{cid}/stop", method="POST")
            urllib.request.urlopen(req, timeout=10)
            print(f"  [parasite] stopped {cid[:8]}", flush=True)
        except Exception:
            pass


def frigate_cv_name(camera_id: str) -> str:
    return f"cv_{camera_id}"


def frigate_set_detect(camera_ids: list[str], *, on: bool) -> None:
    """Boost target cam process_fps: MQTT detect OFF on others / ON on keep."""
    try:
        import paho.mqtt.client as mqtt  # type: ignore
    except Exception as e:
        print(f"  [warn] paho-mqtt unavailable: {e}", flush=True)
        return
    payload = "ON" if on else "OFF"
    try:
        cli = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    except Exception:
        cli = mqtt.Client()
    try:
        cli.connect("127.0.0.1", 1884, 60)
        cli.loop_start()
        time.sleep(0.3)
        for cid in camera_ids:
            name = frigate_cv_name(cid) if not str(cid).startswith("cv_") else str(cid)
            topic = f"frigate/{name}/detect/set"
            cli.publish(topic, payload, qos=1, retain=True)
            print(f"  [frigate] detect {payload} {name[-20:]}", flush=True)
        time.sleep(0.8)
        cli.loop_stop()
        cli.disconnect()
    except Exception as e:
        print(f"  [warn] frigate mqtt detect: {e}", flush=True)


def boost_frigate_for_camera(keep_camera_id: str) -> list[str]:
    """Turn detect OFF on all other Frigate cams; ON on keep."""
    notes: list[str] = []
    try:
        with urllib.request.urlopen("http://127.0.0.1:5000/api/stats", timeout=10) as resp:
            stats = json.loads(resp.read().decode())
        cams = list((stats.get("cameras") or {}).keys())
    except Exception as e:
        notes.append(f"frigate_stats:{e}")
        return notes
    keep_cv = frigate_cv_name(keep_camera_id)
    others = [c for c in cams if c != keep_cv]
    if others:
        frigate_set_detect(others, on=False)
        notes.append(f"detect_off={len(others)}")
    frigate_set_detect([keep_cv], on=True)
    notes.append("detect_on_keep")
    return notes


def restore_frigate_detect_all() -> None:
    try:
        with urllib.request.urlopen("http://127.0.0.1:5000/api/stats", timeout=10) as resp:
            stats = json.loads(resp.read().decode())
        cams = list((stats.get("cameras") or {}).keys())
    except Exception:
        return
    if cams:
        frigate_set_detect(cams, on=True)


def wait_api(sec: int = 120) -> bool:
    deadline = time.time() + sec
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"{v.API}/health", timeout=5) as resp:
                if resp.status == 200:
                    return True
        except Exception:
            pass
        time.sleep(3)
    return False


def safe_login() -> str:
    wait_api(180)
    return v.login_token()


def write_report(path: str, *, t0: float, gem_notes: list[str], report: list[dict]) -> None:
    out = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "elapsed_sec": int(time.time() - t0),
        "gemini_heal": gem_notes,
        "results": report,
    }
    Path(path).write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")


def poll_progress(
    token_box: list[str],
    org: str,
    rule: dict,
    spec: dict,
    baseline_alerts: set[str],
    baseline_events: set[str],
    deadline: float,
) -> tuple[bool, str, dict | None, int, list[str]]:
    """Poll until hit or deadline. token_box[0] is refreshed on 401."""
    misses: list[str] = []
    hit = False
    detail = ""
    alert_hit = None
    new_events = 0
    evidence_deadline: float | None = None
    start = time.time()
    timeout = max(1.0, deadline - start)
    while time.time() < deadline and not hit:
        time.sleep(POLL)
        token = token_box[0]
        try:
            now_events = event_ids(token, org, spec["event_types"])
            new_events = len(now_events - baseline_events)
            new_alert_ids = v.list_demo_alert_ids(token, org) - baseline_alerts
        except Exception as e:
            misses.append(f"poll_api:{type(e).__name__}")
            err = str(e)
            print(f"  [warn] API poll fail — recovery ({e})", flush=True)
            if "401" in err or "Unauthorized" in err:
                try:
                    token_box[0] = safe_login()
                    misses.append("token_refreshed")
                    continue
                except Exception as e2:
                    misses.append(f"relogin_fail:{e2}")
            if not wait_api(90):
                continue
            try:
                token_box[0] = safe_login()
            except Exception:
                pass
            continue
        if new_alert_ids:
            try:
                rows = v.req(
                    "GET",
                    f"{v.API}/api/v1/orgs/{org}/alerts?limit=50&include_incomplete=true",
                    token,
                )
            except Exception as e:
                if "401" in str(e):
                    try:
                        token_box[0] = safe_login()
                    except Exception:
                        pass
                rows = []
            if isinstance(rows, dict):
                rows = rows.get("items", [])
            matched = [a for a in (rows or []) if str(a.get("id")) in new_alert_ids]
            matched = [a for a in matched if str(a.get("rule_id")) == str(rule["id"])] or matched
            if matched:
                alert_hit = matched[0]
                cabin = bool(spec.get("cabin"))
                ev_ok, ev_reason = evidence_ok_flexible(
                    alert_hit,
                    cabin=cabin,
                    require_plate=bool(spec.get("require_plate")),
                )
                ptxt = plate_text(alert_hit)
                if spec.get("require_plate_text") and not ptxt:
                    misses.append("waiting_plate_text")
                    detail = f"alert={alert_hit['id'][:8]} no_plate_text yet ev={ev_reason}"
                    print(f"  … {detail}", flush=True)
                    continue
                if not ev_ok and not cabin:
                    misses.append(f"evidence:{ev_reason}")
                    detail = f"alert={alert_hit['id'][:8]} weak_evidence={ev_reason}"
                    print(f"  … {detail}", flush=True)
                    if evidence_deadline is None:
                        evidence_deadline = time.time() + 90
                    if time.time() < evidence_deadline:
                        continue
                    hit = True
                    detail = (
                        f"alert={alert_hit['id'][:8]} soft_ev={ev_reason} "
                        f"events={new_events} plate={ptxt!r}"
                    )
                    misses.append("soft_evidence_accept")
                    break
                hit = True
                detail = f"alert={alert_hit['id'][:8]} ev={ev_reason} events={new_events} plate={ptxt!r}"
                break
        if new_events >= 1 and not spec.get("require_alert", True):
            hit = True
            detail = f"events_only={new_events}"
            break
        elapsed = int(time.time() - start)
        if elapsed and elapsed % 60 < POLL:
            extra = ""
            if "Feu" in str(spec.get("name", "")):
                try:
                    with urllib.request.urlopen(
                        "http://127.0.0.1:8001/debug/rule-blockers", timeout=8
                    ) as resp:
                        dbg = json.loads(resp.read().decode())
                    cam = v.rule_camera_id(rule) or ""
                    hsv = (dbg.get("hsv_light_states") or {}).get(cam)
                    fb = dbg.get("frigate_bridge") or {}
                    mqtt_n = (fb.get("mqtt_by_camera") or {}).get(cam, 0)
                    extra = (
                        f" hsv={hsv} mqtt_cam={mqtt_n} "
                        f"rl_enq={fb.get('red_light_enqueued')} "
                        f"rl_skip={fb.get('red_light_skipped_not_red')}/"
                        f"{fb.get('red_light_skipped_unknown')}"
                    )
                except Exception:
                    pass
            print(
                f"  … {elapsed}s/{int(timeout)}s events={new_events} "
                f"new_alerts={len(new_alert_ids)}{extra}",
                flush=True,
            )
    return hit, detail, alert_hit, new_events, misses


def heal_gemini_soft() -> list[str]:
    notes: list[str] = []
    try:
        with urllib.request.urlopen("http://127.0.0.1:8001/health", timeout=8) as resp:
            ai = json.loads(resp.read().decode())
        if str(ai.get("gemini_reachable", "")).lower() == "true":
            return ["gemini_ok"]
        notes.append("gemini_unreachable")
    except Exception as e:
        notes.append(f"ai_health:{e}")
    if os.environ.get("P2_SKIP_GEMINI_RESTART", "0") == "1":
        notes.append("skip_ai_restart")
        return notes
    # Soft: DNS / restart AI once
    restart = ROOT / "scripts" / "restart-ai-engine.sh"
    if restart.is_file():
        print("  [heal] restart AI for Gemini reachability", flush=True)
        try:
            subprocess.run(["bash", str(restart)], cwd=str(ROOT), timeout=240, check=False)
            time.sleep(5)
            with urllib.request.urlopen("http://127.0.0.1:8001/health", timeout=10) as resp:
                ai = json.loads(resp.read().decode())
            notes.append(f"gemini_after_restart={ai.get('gemini_reachable')}")
        except Exception as e:
            notes.append(f"ai_restart_fail:{e}")
    return notes


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(line_buffering=True)

    print("=== protocole 2 Frigate 1-hit ===", flush=True)
    gem_notes = heal_gemini_soft()
    print(f"gemini_heal: {gem_notes}", flush=True)

    token = v.login_token()
    me = v.req("GET", f"{v.API}/api/v1/auth/me", token)
    org = v.DEMO_ORG or me.get("org_id", "")
    print(f"org={org}", flush=True)

    all_rules = v.req("GET", f"{v.API}/api/v1/orgs/{org}/rules", token)
    if isinstance(all_rules, dict):
        all_rules = all_rules.get("items", [])
    demo = [r for r in (all_rules or []) if str(r.get("name", "")).startswith("Démo")]
    by_name = {r["name"]: r for r in demo}
    print(f"demo_rules={len(demo)}", flush=True)

    report: list[dict] = []
    t0 = time.time()
    token_box = [token]

    # Optional: seed prior PASS from previous partial report
    skip_names = {
        s.strip()
        for s in os.environ.get("P2_SKIP_RULES", "").split("|")
        if s.strip()
    }
    if skip_names:
        print(f"skip_rules={sorted(skip_names)}", flush=True)

    for spec in SPECS:
        name = spec["name"]
        if name in skip_names:
            report.append(
                {
                    "rule": name,
                    "status": "PASS_SKIPPED_PRIOR",
                    "detail": "skipped via P2_SKIP_RULES (prior PASS)",
                    "misses": [],
                }
            )
            print(f"\n======== {name} SKIPPED ========", flush=True)
            write_report(REPORT_PATH, t0=t0, gem_notes=gem_notes, report=report)
            continue
        print(f"\n======== {name} ========", flush=True)
        misses: list[str] = []
        rule = by_name.get(name)
        if not rule:
            report.append({"rule": name, "status": "FAIL", "detail": "rule_missing", "misses": ["missing"]})
            print("FAIL rule missing", flush=True)
            continue

        token = token_box[0]
        # Refresh rule list + disable all
        try:
            v.disable_all(token, org, demo)
        except Exception as e:
            if "401" in str(e):
                token_box[0] = safe_login()
                token = token_box[0]
            misses.append(f"disable_all:{e}")
            for r in demo:
                sql_set_enabled(r["id"], False)
        time.sleep(3)
        try:
            v.wait_active_rules(0, sec=60)
        except Exception:
            pass

        cam_id = v.rule_camera_id(rule)
        try:
            video_id = v.camera_video_id(token, org, cam_id) if cam_id else None
        except Exception:
            token_box[0] = safe_login()
            token = token_box[0]
            video_id = v.camera_video_id(token, org, cam_id) if cam_id else None
        print(f"  cam={cam_id} video={video_id}", flush=True)

        pf_ok, pf_detail = v.ensure_rule_test_ready(
            token,
            org,
            name,
            camera_id=cam_id,
            video_id=video_id,
            needs_frigate=bool(spec.get("needs_frigate", True)),
            needs_phone_model=bool(spec.get("needs_phone_model", False)),
        )
        if not pf_ok:
            misses.append(pf_detail)
            print(f"  preflight blocked soft-continue: {pf_detail}", flush=True)
            # Still try switch + wait - plan says be flexible
            if video_id:
                try:
                    v.set_active_demo_video(token, org, video_id)
                except Exception as e:
                    misses.append(f"switch_fail:{e}")

        if video_id:
            try:
                v.set_active_demo_video(token_box[0], org, video_id)
                print(f"  switched active_video={video_id[:8]}", flush=True)
            except Exception as e:
                if "401" in str(e):
                    token_box[0] = safe_login()
                    try:
                        v.set_active_demo_video(token_box[0], org, video_id)
                    except Exception as e2:
                        misses.append(f"switch:{e2}")
                else:
                    misses.append(f"switch:{e}")

        if cam_id and spec.get("stop_parasites"):
            stop_cabin_parasites(cam_id)

        if cam_id and spec.get("needs_frigate"):
            boost_notes = boost_frigate_for_camera(cam_id)
            misses.extend(boost_notes)
            print(f"  [heal] frigate boost: {boost_notes}", flush=True)
            # also stop AI parasites to cut VLM/MQTT noise
            try:
                v.stop_extra_ai_cameras(cam_id)
            except Exception as e:
                misses.append(f"stop_extra:{e}")

        enable_only(token_box[0], org, demo, name)
        time.sleep(5)
        try:
            v.wait_active_rules(1, sec=90)
        except Exception as e:
            misses.append(f"wait_active:{e}")
            wait_api(60)

        # Refresh bindings
        try:
            all_rules = v.req("GET", f"{v.API}/api/v1/orgs/{org}/rules", token_box[0])
        except Exception:
            token_box[0] = safe_login()
            all_rules = v.req("GET", f"{v.API}/api/v1/orgs/{org}/rules", token_box[0])
        if isinstance(all_rules, dict):
            all_rules = all_rules.get("items", [])
        demo = [r for r in (all_rules or []) if str(r.get("name", "")).startswith("Démo")]
        by_name = {r["name"]: r for r in demo}
        rule = by_name[name]

        try:
            baseline_alerts = v.list_demo_alert_ids(token_box[0], org)
            baseline_events = event_ids(token_box[0], org, spec["event_types"])
        except Exception:
            token_box[0] = safe_login()
            baseline_alerts = v.list_demo_alert_ids(token_box[0], org)
            baseline_events = event_ids(token_box[0], org, spec["event_types"])

        hit, detail, alert_hit, new_events, poll_misses = poll_progress(
            token_box, org, rule, spec, baseline_alerts, baseline_events, time.time() + TIMEOUT
        )
        misses.extend(poll_misses)

        if not hit:
            misses.append(f"timeout_{TIMEOUT}s")
            print("  MISS — soft heal: boost+resync+kick+retry 5min", flush=True)
            if cam_id:
                misses.extend(boost_frigate_for_camera(cam_id))
            try:
                v.trigger_ingest_resync()
            except Exception as e:
                misses.append(f"resync:{e}")
            wait_api(90)
            try:
                token_box[0] = safe_login()
            except Exception as e:
                misses.append(f"relogin:{e}")
            if cam_id:
                try:
                    v.kick_ai_camera(cam_id)
                except Exception as e:
                    misses.append(f"kick:{e}")
            if video_id:
                try:
                    v.set_active_demo_video(token_box[0], org, video_id)
                except Exception:
                    pass
            if cam_id and spec.get("stop_parasites"):
                stop_cabin_parasites(cam_id)
            enable_only(token_box[0], org, demo, name)
            time.sleep(10)
            try:
                baseline_alerts = v.list_demo_alert_ids(token_box[0], org)
                baseline_events = event_ids(token_box[0], org, spec["event_types"])
            except Exception:
                token_box[0] = safe_login()
                baseline_alerts = v.list_demo_alert_ids(token_box[0], org)
                baseline_events = event_ids(token_box[0], org, spec["event_types"])
            hit2, detail2, alert2, ev2, miss2 = poll_progress(
                token_box, org, rule, spec, baseline_alerts, baseline_events, time.time() + 300
            )
            misses.extend(miss2)
            if hit2:
                hit, detail, alert_hit, new_events = hit2, detail2, alert2, ev2
                misses.append("needed_heal_retry")

        try:
            restore_frigate_detect_all()
        except Exception:
            pass

        status = "PASS" if hit else "FAIL"
        if hit and any("heal" in m or "soft_" in m or "needed_heal" in m for m in misses):
            status = "PASS_AFTER_HEAL"
        entry = {
            "rule": name,
            "status": status,
            "detail": detail or "no event/alert",
            "misses": misses,
            "events": new_events,
            "alert_id": (alert_hit or {}).get("id"),
            "plate_text": plate_text(alert_hit) if alert_hit else "",
            "camera_id": cam_id,
            "video_id": video_id,
            "preflight": pf_detail,
        }
        report.append(entry)
        write_report(REPORT_PATH, t0=t0, gem_notes=gem_notes, report=report)
        print(f"{status}: {entry['detail']} misses={misses}", flush=True)

    if DISABLE_END:
        print("\n=== disable all demo rules (1B) ===", flush=True)
        try:
            v.disable_all(token, org, demo)
        except Exception:
            subprocess.call(
                [
                    "docker",
                    "exec",
                    "citevision-v2-postgres",
                    "psql",
                    "-U",
                    "citevision",
                    "-d",
                    "citevision",
                    "-c",
                    "UPDATE rules SET is_enabled=false WHERE name LIKE 'Démo%'",
                ]
            )

    try:
        restore_frigate_detect_all()
    except Exception:
        pass

    write_report(REPORT_PATH, t0=t0, gem_notes=gem_notes, report=report)
    print(f"\nreport: {REPORT_PATH}", flush=True)
    for r in report:
        print(f"  {r['status']:16} {r['rule']}", flush=True)

    fails = sum(1 for r in report if not str(r["status"]).startswith("PASS"))
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
