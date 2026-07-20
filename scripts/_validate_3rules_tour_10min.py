#!/usr/bin/env python3
"""Tour démo : 3 règles × 10 min, switch vidéo entre chaque (vitesse → téléphone → feu rouge)."""
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
API = os.environ.get("BACKEND_API_URL", "http://127.0.0.1:8081")
EMAIL = os.environ.get("ADMIN_EMAIL", "glory.henock@hologram.cd")
PASS = os.environ.get("ADMIN_PASSWORD", "Hologram2026!")
INTERNAL = os.environ.get("INTERNAL_API_KEY", "changeme_internal_service_key")
RULE_DURATION_SEC = int(os.environ.get("RULE_DURATION_SEC", "600"))  # 10 min
SETTLE_SEC = int(os.environ.get("DEMO_SETTLE_SEC", "45"))
POLL_SEC = int(os.environ.get("POLL_SEC", "30"))

RULES = [
    {
        "name": "Démo · Excès de vitesse",
        "event_types": ["speeding"],
        "key": "speed",
    },
    {
        "name": "Démo · Téléphone au volant",
        "event_types": ["phone_use_violation", "phone_driving", "driver_phone"],
        "key": "phone",
    },
    {
        "name": "Démo · Feu rouge",
        "event_types": ["red_light_violation"],
        "key": "red_light",
    },
]


def log(msg: str) -> None:
    ts = datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)


def req(method: str, url: str, token: str | None = None, body: dict | None = None, internal: bool = False) -> object:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if internal:
        headers["X-Internal-Key"] = INTERNAL
    data = json.dumps(body).encode() if body is not None else None
    last_err: Exception | None = None
    for attempt in range(5):
        try:
            r = urllib.request.Request(url, data=data, headers=headers, method=method)
            with urllib.request.urlopen(r, timeout=120) as resp:
                raw = resp.read().decode()
                return json.loads(raw) if raw else {}
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as exc:
            last_err = exc
            time.sleep(min(30, 2 ** attempt))
    raise last_err  # type: ignore[misc]


def psql(sql: str) -> str:
    r = subprocess.run(
        ["docker", "exec", "citevision-v2-postgres", "psql", "-U", "citevision", "-d", "citevision", "-t", "-A", "-c", sql],
        capture_output=True, text=True, check=False,
    )
    return (r.stdout or "").strip()


def login() -> tuple[str, str, float]:
    login_data = req("POST", f"{API}/api/v1/auth/login", body={"email": EMAIL, "password": PASS})
    token = login_data["access_token"]
    me = req("GET", f"{API}/api/v1/auth/me", token=token)
    return token, me["org_id"], time.time()


def ensure_token(token: str, token_at: float) -> tuple[str, float]:
    if time.time() - token_at < 240:
        return token, token_at
    login_data = req("POST", f"{API}/api/v1/auth/login", body={"email": EMAIL, "password": PASS})
    return login_data["access_token"], time.time()


def disable_all_demo(token: str, org: str, rules: list[dict]) -> None:
    for r in rules:
        if str(r.get("name", "")).startswith("Démo"):
            req("PATCH", f"{API}/api/v1/orgs/{org}/rules/{r['id']}", token, {"is_enabled": False})


def rule_camera_id(rule: dict) -> str | None:
    definition = rule.get("definition")
    if isinstance(definition, str):
        definition = json.loads(definition)
    bindings = (definition or {}).get("bindings") or {}
    cam = bindings.get("camera_id") or (definition or {}).get("camera_id")
    return str(cam) if cam else None


def camera_video_id(token: str, org: str, camera_id: str) -> str | None:
    cams = req("GET", f"{API}/api/v1/orgs/{org}/cameras", token)
    if isinstance(cams, dict):
        cams = cams.get("items", [])
    for c in cams or []:
        if str(c.get("id")) != str(camera_id):
            continue
        meta = c.get("metadata") or {}
        if isinstance(meta, str):
            meta = json.loads(meta)
        vid = meta.get("demo_video_id")
        return str(vid) if vid else None
    return None


def set_active_video(token: str, org: str, video_id: str) -> None:
    req(
        "PATCH",
        f"{API}/api/v1/orgs/{org}/demo/settings",
        token,
        {"source_mode": "video", "active_video_id": video_id, "active_camera_id": None},
    )


def resync_ingest() -> None:
    try:
        req("POST", f"{API}/api/v1/internal/ingest/resync-spatial", internal=True)
    except urllib.error.HTTPError as exc:
        log(f"WARN resync-spatial: {exc}")


def count_events(org: str, event_types: list[str], since_iso: str) -> int:
    types_sql = ",".join(f"'{t}'" for t in event_types)
    out = psql(
        f"SELECT count(*) FROM events e "
        f"JOIN cameras c ON c.id = e.camera_id "
        f"WHERE c.org_id = '{org}'::uuid AND c.metadata->>'demo' = 'true' "
        f"AND e.event_type IN ({types_sql}) AND e.ingested_at >= '{since_iso}'::timestamptz;"
    )
    try:
        return int(out or "0")
    except ValueError:
        return 0


def count_alerts(org: str, event_types: list[str], since_iso: str) -> int:
    types_sql = ",".join(f"'{t}'" for t in event_types)
    out = psql(
        f"SELECT count(*) FROM alerts a JOIN events e ON e.id = a.event_id "
        f"WHERE e.org_id = '{org}'::uuid AND e.event_type IN ({types_sql}) "
        f"AND a.created_at >= '{since_iso}'::timestamptz;"
    )
    try:
        return int(out or "0")
    except ValueError:
        return 0


def frigate_evidence_stats(org: str, event_types: list[str], since_iso: str) -> dict:
    types_sql = ",".join(f"'{t}'" for t in event_types)
    rows = psql(
        f"SELECT COALESCE(a.evidence_snapshot->'package'->'metadata'->>'capture_source',''), "
        f"COALESCE(a.evidence_snapshot->'package'->'metadata'->>'bbox_source','') "
        f"FROM alerts a JOIN events e ON e.id = a.event_id "
        f"WHERE e.org_id = '{org}'::uuid AND e.event_type IN ({types_sql}) "
        f"AND a.created_at >= '{since_iso}'::timestamptz LIMIT 50;"
    )
    cap, bbox = {}, {}
    for ln in rows.splitlines():
        if "|" not in ln:
            continue
        src, bsrc = ln.split("|", 1)
        cap[src or "empty"] = cap.get(src or "empty", 0) + 1
        bbox[bsrc or "empty"] = bbox.get(bsrc or "empty", 0) + 1
    return {"capture_source": cap, "bbox_source": bbox}


def ai_camera_status(camera_id: str) -> dict:
    try:
        data = req("GET", "http://127.0.0.1:8001/cameras")
        for c in data.get("cameras", []):
            if c.get("camera_id") == camera_id:
                return c
    except Exception:
        pass
    return {}


def wait_active_rules(n: int, sec: int = 120) -> None:
    url = f"http://localhost:{os.environ.get('RULES_ENGINE_PORT', '8010')}/health"
    deadline = time.time() + sec
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=5) as resp:
                active = int(json.loads(resp.read()).get("active_rules", -1))
            if active == n:
                return
        except Exception:
            pass
        time.sleep(3)


def wait_for_camera_ingest(camera_id: str, sec: int | None = None) -> dict:
    """Poll AI until target demo camera processes frames (post video switch)."""
    deadline = time.time() + (sec if sec is not None else max(SETTLE_SEC, 90))
    last: dict = {}
    resync_at = 0.0
    while time.time() < deadline:
        last = ai_camera_status(camera_id)
        if int(last.get("frames_processed") or 0) >= 6:
            return last
        if time.time() - resync_at > 20:
            resync_ingest()
            resync_at = time.time()
        time.sleep(5)
    return last


def run_rule_window(
    token: str,
    token_at: float,
    org: str,
    spec: dict,
    rule: dict,
    all_rules: list[dict],
) -> tuple[dict, str, float]:
    name = spec["name"]
    event_types = spec["event_types"]
    cam_id = rule_camera_id(rule)
    video_id = camera_video_id(token, org, cam_id) if cam_id else None

    log(f"=== {name} — switch vidéo + 10 min ===")
    token, token_at = ensure_token(token, token_at)
    disable_all_demo(token, org, all_rules)
    time.sleep(5)
    wait_active_rules(0)

    if video_id:
        set_active_video(token, org, video_id)
        log(f"active_video_id={video_id[:8]}… camera={cam_id[:8] if cam_id else '?'}")
    else:
        log(f"WARN: pas de video_id pour caméra {cam_id}")

    resync_ingest()
    log(f"settle ingest (max {SETTLE_SEC}s)…")
    st = wait_for_camera_ingest(cam_id, sec=max(SETTLE_SEC, 120)) if cam_id else {}

    if cam_id:
        log(f"AI ingest: source={st.get('source') or st.get('rtsp_url', '')[:50]} "
            f"frames={st.get('frames_processed', 0)} err={st.get('last_error')}")

    window_start = datetime.now(timezone.utc)
    since_iso = window_start.strftime("%Y-%m-%d %H:%M:%S%z").replace("+0000", "+00")

    req("PATCH", f"{API}/api/v1/orgs/{org}/rules/{rule['id']}", token, {"is_enabled": True})
    wait_active_rules(1, sec=180)
    log(f"règle activée — fenêtre {RULE_DURATION_SEC}s")

    deadline = time.time() + RULE_DURATION_SEC
    last_log = 0.0
    peak_events = 0
    hit = False
    while time.time() < deadline:
        remaining = int(deadline - time.time())
        evt = count_events(org, event_types, since_iso)
        peak_events = max(peak_events, evt)
        alerts = count_alerts(org, event_types, since_iso)
        frigate = frigate_evidence_stats(org, event_types, since_iso)
        frigate_n = frigate.get("capture_source", {}).get("frigate_track", 0)
        if alerts >= 1 and frigate_n >= 1:
            log(f"  HIT: events={evt} alerts={alerts} frigate_track={frigate_n}")
            hit = True
            break
        if time.time() - last_log >= POLL_SEC:
            log(f"  … {remaining}s restantes | events={evt} alerts={alerts} frigate={frigate_n}")
            last_log = time.time()
        time.sleep(min(POLL_SEC, max(1, remaining)))

    token, token_at = ensure_token(token, token_at)
    evt_final = count_events(org, event_types, since_iso)
    alerts_final = count_alerts(org, event_types, since_iso)
    frigate = frigate_evidence_stats(org, event_types, since_iso)

    try:
        token, token_at = ensure_token(token, token_at)
        req("PATCH", f"{API}/api/v1/orgs/{org}/rules/{rule['id']}", token, {"is_enabled": False})
    except Exception as exc:
        log(f"WARN disable rule via API: {exc}")
    time.sleep(3)

    frigate_ok = frigate.get("capture_source", {}).get("frigate_track", 0) > 0
    status = "PASS" if evt_final >= 1 and alerts_final >= 1 and frigate_ok else "FAIL"
    if evt_final >= 1 and alerts_final < 1:
        status = "PARTIAL"
    if evt_final < 1:
        status = "FAIL"

    result = {
        "rule": name,
        "key": spec["key"],
        "status": status,
        "duration_sec": RULE_DURATION_SEC,
        "video_id": video_id,
        "camera_id": cam_id,
        "events": evt_final,
        "alerts": alerts_final,
        "frigate_track_alerts": frigate.get("capture_source", {}).get("frigate_track", 0),
        "capture_source": frigate.get("capture_source", {}),
        "bbox_source": frigate.get("bbox_source", {}),
        "window_start": since_iso,
    }
    log(f"{name}: {status} events={evt_final} alerts={alerts_final} "
        f"frigate_track={result['frigate_track_alerts']} caps={frigate.get('capture_source')}")
    return result, token, token_at


def main() -> int:
    only = [s.strip() for s in os.environ.get("VALIDATE_ONLY", "").split(",") if s.strip()]
    only_keys = {s.strip() for s in os.environ.get("VALIDATE_ONLY_KEYS", "").split(",") if s.strip()}
    log("=== Tour démo 3 règles × 10 min ===")
    req("GET", f"{API}/health")
    token, org, token_at = login()
    log(f"org={org}")

    all_rules = req("GET", f"{API}/api/v1/orgs/{org}/rules", token)
    if not isinstance(all_rules, list):
        all_rules = []
    by_name = {r["name"]: r for r in all_rules}

    original = req("GET", f"{API}/api/v1/orgs/{org}/demo/settings", token)
    orig_vid = (original or {}).get("active_video_id")

    disable_all_demo(token, org, all_rules)
    time.sleep(5)

    results = []
    for spec in RULES:
        if only and spec["name"] not in only:
            continue
        if only_keys and spec.get("key") not in only_keys:
            continue
        rule = by_name.get(spec["name"])
        if not rule:
            log(f"FAIL: règle absente {spec['name']}")
            results.append({"rule": spec["name"], "status": "FAIL", "detail": "rule missing"})
            continue
        result, token, token_at = run_rule_window(token, token_at, org, spec, rule, all_rules)
        results.append(result)

    disable_all_demo(token, org, all_rules)
    if orig_vid:
        try:
            set_active_video(token, org, str(orig_vid))
        except Exception:
            pass

    logs = ROOT / "logs"
    logs.mkdir(exist_ok=True)
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "duration_per_rule_sec": RULE_DURATION_SEC,
        "results": results,
        "pass": sum(1 for r in results if r.get("status") == "PASS"),
        "fail": sum(1 for r in results if r.get("status") in ("FAIL", "PARTIAL")),
    }
    out_json = logs / "validate-3rules-tour-10min.json"
    out_md = logs / "validate-3rules-tour-10min.md"
    out_json.write_text(json.dumps(report, indent=2), encoding="utf-8")

    lines = [
        "# Tour démo — 3 règles × 10 min",
        "",
        f"Généré : {report['generated_at']}",
        f"**PASS:** {report['pass']} / **FAIL+PARTIAL:** {report['fail']}",
        "",
        "| Règle | Status | Events | Alertes | frigate_track |",
        "|-------|--------|--------|---------|---------------|",
    ]
    for r in results:
        lines.append(
            f"| {r.get('rule', '?')} | {r.get('status', '?')} | {r.get('events', 0)} | "
            f"{r.get('alerts', 0)} | {r.get('frigate_track_alerts', 0)} |"
        )
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")

    log(f"Rapport: {out_json}")
    for r in results:
        log(f"  {r.get('rule')}: {r.get('status')}")
    return 0 if report["fail"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
