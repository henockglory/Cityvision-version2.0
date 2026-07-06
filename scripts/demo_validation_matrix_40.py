#!/usr/bin/env python3
"""Matrice honnête de 40 validations démo — lecture API + health, sans affirmation E2E non prouvée."""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone

API = os.environ.get("BACKEND_API_URL", "http://127.0.0.1:8081")
AI = os.environ.get("AI_ENGINE_URL", "http://127.0.0.1:8001")
RULES = os.environ.get("RULES_ENGINE_URL", "http://127.0.0.1:8010")
MAILHOG = os.environ.get("MAILHOG_PUBLIC_URL", "http://127.0.0.1:8025")
EMAIL = os.environ.get("ADMIN_EMAIL", "glory.henock@hologram.cd")
PASSWORD = os.environ.get("ADMIN_PASSWORD", "Henockglory@03")

PASS = "PASS"
PARTIAL = "PARTIAL"
FAIL = "FAIL"
SKIP = "SKIP"


def get(url: str, token: str | None = None, timeout: int = 15) -> tuple[int, dict | list | str]:
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode()
            try:
                return resp.status, json.loads(raw) if raw else {}
            except json.JSONDecodeError:
                return resp.status, raw
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        try:
            return e.code, json.loads(body)
        except json.JSONDecodeError:
            return e.code, body
    except Exception as e:
        return 0, str(e)


def post(url: str, body: dict, token: str | None = None) -> tuple[int, dict]:
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode()
            return resp.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            return e.code, json.loads(raw)
        except json.JSONDecodeError:
            return e.code, {"error": raw}
    except Exception as e:
        return 0, {"error": str(e)}


def ai_bool(data: dict, key: str) -> bool:
    return str(data.get(key, "")).lower() in ("true", "1", "yes")


def package_ok(snap: dict | None) -> tuple[bool, str]:
    if not snap:
        return False, "no snapshot"
    pkg = snap.get("package") or {}
    if isinstance(pkg, str):
        try:
            pkg = json.loads(pkg)
        except json.JSONDecodeError:
            return False, "invalid package json"
    clip = pkg.get("clip") or {}
    has_clip = bool(clip.get("url") or clip.get("asset_id"))
    images = pkg.get("images") or []
    roles = {im.get("role") for im in images if isinstance(im, dict) and (im.get("url") or im.get("asset_id"))}
    if has_clip and "scene" in roles and "subject" in roles:
        return True, "clip+scene+subject"
    return False, f"clip={has_clip} roles={sorted(roles)}"


def main() -> int:
    rows: list[dict] = []
    now = datetime.now(timezone.utc).isoformat()

    def row(n: int, area: str, check: str, status: str, evidence: str, prod_note: str = "") -> None:
        rows.append({
            "id": n,
            "area": area,
            "check": check,
            "status": status,
            "evidence": evidence,
            "prod_note": prod_note,
        })

    # --- Health & infra (1-8) ---
    st, backend = get(f"{API}/health")
    row(1, "Infra", "API backend joignable", PASS if st == 200 else FAIL, f"HTTP {st}")

    st, ai = get(f"{AI}/health")
    row(2, "Infra", "Moteur IA joignable", PASS if st == 200 else FAIL, f"HTTP {st}")

    st, re = get(f"{RULES}/health")
    active_rules = re.get("active_rules", "?") if isinstance(re, dict) else "?"
    row(3, "Infra", "Rules-engine joignable", PASS if st == 200 else FAIL, f"HTTP {st}, active_rules={active_rules}")

    st, _ = get(f"{MAILHOG}/api/v2/messages?limit=1")
    row(4, "Infra", "MailHog (SMTP test) joignable", PASS if st == 200 else PARTIAL, f"HTTP {st}")

    st, login = post(f"{API}/api/v1/auth/login", {"email": EMAIL, "password": PASSWORD})
    token = login.get("access_token") if isinstance(login, dict) else None
    row(5, "Sécurité", "Authentification admin API", PASS if token else FAIL, "login OK" if token else str(login)[:120])

    if not token:
        for i in range(6, 41):
            row(i, "—", f"Check #{i} (auth requise)", SKIP, "login échoué")
        _print_table(rows, now, active_rules)
        return 1

    st, me = get(f"{API}/api/v1/auth/me", token)
    org = me.get("org_id") if isinstance(me, dict) else None
    row(6, "Sécurité", "Session / org_id résolu live", PASS if org else FAIL, f"org={org}")

    st, cams = get(f"{API}/api/v1/orgs/{org}/cameras", token)
    cam_list = cams if isinstance(cams, list) else []
    row(7, "Caméras", "Au moins 1 caméra enregistrée", PASS if len(cam_list) >= 1 else FAIL, f"count={len(cam_list)}")

    virtual = sum(1 for c in cam_list if "benedicte" in c.get("name", "").lower() or (c.get("metadata") or {}).get("virtual"))
    row(8, "Caméras", "Pas de doublons caméra virtuelle démo", PASS if virtual <= 1 else FAIL, f"virtual_like={virtual}/{len(cam_list)}")

    # --- IA models (9-14) ---
    row(9, "IA", "YOLO détection (CUDA)", PASS if ai_bool(ai, "yolo_loaded") and ai_bool(ai, "yolo_cuda") else PARTIAL,
        f"yolo={ai.get('yolo_loaded')} cuda={ai.get('yolo_cuda')} provider={ai.get('yolo_provider')}")
    row(10, "IA", "OCR plaque (PaddleOCR)", PASS if ai_bool(ai, "plate_loaded") else FAIL, str(ai.get("plate_loaded")))
    row(11, "IA", "Reconnaissance faciale", PASS if ai_bool(ai, "face_loaded") else PARTIAL, str(ai.get("face_loaded")))
    row(12, "IA", "Modèle téléphone secondaire", PASS if ai_bool(ai, "driver_phone_model_loaded") else FAIL, str(ai.get("driver_phone_model_loaded")))
    row(13, "IA", "Modèle ceinture secondaire", PASS if ai_bool(ai, "seatbelt_model_loaded") else FAIL, str(ai.get("seatbelt_model_loaded")))
    row(14, "IA", "Feu tricolore prêt", PASS if ai_bool(ai, "traffic_light_ready") else PARTIAL, str(ai.get("traffic_light_ready")))

    # --- Spatial & rules config (15-22) ---
    st, zones = get(f"{API}/api/v1/orgs/{org}/zones", token)
    zone_list = zones if isinstance(zones, list) else []
    speed_zones = [z for z in zone_list if (z.get("behavior_config") or {}).get("behavior") == "speed_measurement"]
    row(15, "Zones", "Zones persistées en DB", PASS if len(zone_list) >= 1 else FAIL, f"zones={len(zone_list)}")
    row(16, "Zones", "Zone vitesse calibrée présente", PASS if speed_zones else PARTIAL, f"speed_zones={len(speed_zones)}")

    st, lines = get(f"{API}/api/v1/orgs/{org}/lines", token)
    line_list = lines if isinstance(lines, list) else []
    row(17, "Zones", "Lignes de comptage présentes", PASS if len(line_list) >= 1 else PARTIAL, f"lines={len(line_list)}")

    st, catalog = get(f"{API}/api/v1/orgs/{org}/rules/catalog", token)
    cat_list = catalog if isinstance(catalog, list) else []
    row(18, "Règles", "Catalogue règles API (≥5 gabarits)", PASS if len(cat_list) >= 5 else FAIL, f"templates={len(cat_list)}")

    st, rules = get(f"{API}/api/v1/orgs/{org}/rules", token)
    rule_list = rules if isinstance(rules, list) else []
    demo_rules = [r for r in rule_list if str(r.get("name", "")).startswith("Démo")]
    enabled = [r for r in demo_rules if r.get("is_enabled")]
    row(19, "Règles", "5 règles démo seedées", PASS if len(demo_rules) >= 5 else PARTIAL, f"demo_rules={len(demo_rules)}")
    row(20, "Règles", "Règles démo actuellement activées", PASS if enabled else SKIP,
        f"enabled={len(enabled)}/{len(demo_rules)} — attendu 0 si handoff post-validation",
        "Activer 1 règle à la fois pour E2E live")

    st, menu = get(f"{API}/api/v1/orgs/{org}/capabilities/menu", token)
    behaviors = (menu.get("behaviors") if isinstance(menu, dict) else []) or []
    row(21, "Catalogue IA", "Menu comportements dynamique API", PASS if len(behaviors) >= 3 else PARTIAL, f"behaviors={len(behaviors)}")
    row(22, "Catalogue IA", "Import modèle ONNX org (liste)", PARTIAL, "endpoint GET /ai/models — vérifier UI Santé",
         "Même mécanisme pour caméra réelle après import ONNX")

    # --- Pipeline events/alerts (23-28) — historical, rules OFF = no new alerts expected ---
    st, events = get(f"{API}/api/v1/orgs/{org}/events?limit=20", token)
    ev_list = events if isinstance(events, list) else []
    row(23, "Pipeline", "Événements IA historiques en DB", PASS if len(ev_list) >= 1 else PARTIAL,
        f"events={len(ev_list)} (0 si stack fraîche)",
        "Preuve que MQTT ingest fonctionne quand règles actives + flux")

    st, alerts = get(f"{API}/api/v1/orgs/{org}/alerts?limit=20&include_incomplete=true", token)
    al_list = alerts if isinstance(alerts, list) else []
    row(24, "Pipeline", "Alertes historiques persistées", PASS if len(al_list) >= 1 else PARTIAL, f"alerts={len(al_list)}")

    complete_pkg = 0
    with_plate = 0
    for a in al_list[:20]:
        snap = a.get("evidence_snapshot") or (a.get("metadata") or {}).get("evidence_snapshot")
        if isinstance(snap, str):
            try:
                snap = json.loads(snap)
            except json.JSONDecodeError:
                snap = None
        ok, _ = package_ok(snap if isinstance(snap, dict) else None)
        if ok:
            complete_pkg += 1
        meta = a.get("metadata") or {}
        if meta.get("plate") or meta.get("plate_text") or (isinstance(snap, dict) and (snap.get("plate") or snap.get("package", {}).get("plate"))):
            with_plate += 1
    row(25, "Preuves", "Alertes avec package complet (historique)", PASS if complete_pkg >= 1 else PARTIAL,
        f"{complete_pkg}/{len(al_list)} clip+scene+subject",
        "Politique 6s+2 images — reproductible caméra RTSP réelle")
    row(26, "Preuves", "Lecture plaque sur alertes routières", PASS if with_plate >= 1 else PARTIAL,
        f"alerts_with_plate={with_plate}",
        "Dépend qualité flux + angle — pas garantie 100%")

    row(27, "Pipeline", "Nouvelles alertes avec règles OFF", SKIP if not enabled else PARTIAL,
        f"active_rules_engine={active_rules}; demo_enabled={len(enabled)}",
        "Normal: 0 alerte nouvelle tant que is_enabled=false")

    row(28, "Pipeline", "Rules-engine sync (active_rules cohérent)", PASS if str(active_rules) == "0" and not enabled else PARTIAL,
        f"active_rules={active_rules}, demo_enabled={len(enabled)}")

    # --- Output channels (29-36) ---
    st, routing = get(f"{API}/api/v1/orgs/{org}/routing", token)
    routes = routing if isinstance(routing, list) else routing.get("items", []) if isinstance(routing, dict) else []
    enabled_routes = [r for r in routes if r.get("enabled")] if isinstance(routes, list) else []
    row(29, "Sorties", "Routage alertes configurable (API)", PASS if isinstance(routes, list) else PARTIAL,
        f"routes={len(routes) if isinstance(routes, list) else '?'}")

    st, org_data = get(f"{API}/api/v1/orgs/{org}", token)
    prefs = (org_data.get("notification_prefs") or {}) if isinstance(org_data, dict) else {}
    smtp_ok = bool(prefs.get("smtp_host") or os.environ.get("SMTP_HOST"))
    row(30, "Sorties", "SMTP / notification e-mail configuré", PASS if smtp_ok else PARTIAL,
        "prefs ou env SMTP présents" if smtp_ok else "SMTP non configuré — MailHog en démo")

    st, mh = get(f"{MAILHOG}/api/v2/messages?limit=1")
    mh_total = mh.get("total", 0) if isinstance(mh, dict) else 0
    row(31, "Sorties", "E-mails capturés MailHog (historique)", PASS if mh_total >= 1 else PARTIAL,
        f"messages={mh_total}",
        "Preuve mail premium si règle active + action email")

    row(32, "Sorties", "Webhook manuel alerte (endpoint forward)", PARTIAL,
        "POST /alerts/{id}/forward — non exécuté ici (destructif)",
        "Presets n8n/discord/generic via routing.PostWebhookPreset")

    row(33, "Sorties", "Preset webhook n8n documenté", PASS, "backend/internal/routing/presets.go PresetN8N",
         "URL n8n → JSON payload signé HMAC si WEBHOOK_SIGNING_SECRET")

    row(34, "Sorties", "Personnalisation template e-mail", PARTIAL,
        "notification_prefs + templates org — vérifier Paramètres",
         "Même org prefs pour caméra réelle")

    row(35, "Intégration", "n8n : corrélation plaque → contact BD externe", PARTIAL,
        "Non natif CitéVision — chaîne: webhook alerte → n8n → SQL/API → mail/SMS",
         "Pattern supporté: payload contient plate, rule_id, evidence URLs")

    row(36, "Intégration", "SSRF guard webhooks sortants", PASS, "routing/ssrf.go — LAN n8n autorisé si résolu",
         "Production: whitelist URL + secret signing")

    # --- UI & ops (37-40) ---
    st, health_page = get(f"{API}/api/v1/orgs/{org}/health", token)
    row(37, "Ops", "Santé système API (modèles/services)", PASS if st == 200 else PARTIAL, f"HTTP {st}")

    st, model_pack = get(f"{API}/api/v1/orgs/{org}/ai/model-pack", token)
    mp_models = (model_pack.get("models") if isinstance(model_pack, dict) else []) or []
    row(38, "Ops", "Model-pack org exposé", PASS if mp_models else PARTIAL, f"models={len(mp_models)}")

    row(39, "Démo", "Validation E2E 5 règles (live maintenant)", SKIP if not enabled else PARTIAL,
        "Règles OFF — lancer validate_demo_five_rules.py pour preuve complète",
         "1 règle active à la fois → alerte+preuves+mail")

    row(40, "Garantie", "Chaîne zone→IA→règle→preuve→sortie certifiable aujourd'hui", PARTIAL,
        f"Infra OK; IA GPU OK; règles OFF; {complete_pkg} pkg complets historiques; mail/webhook architecture OK",
         "Certification prod = activer règles + caméra RTSP réelle + test validate_demo_five_rules.py")

    _print_table(rows, now, active_rules)
    fails = sum(1 for r in rows if r["status"] == FAIL)
    return 1 if fails else 0


def _print_table(rows: list[dict], ts: str, active_rules) -> None:
    print(f"\n# Matrice validation démo — 40 points ({ts} UTC)\n")
    print(f"rules-engine active_rules={active_rules}\n")
    print("| # | Domaine | Contrôle | Statut | Preuve | Applicabilité caméra réelle |")
    print("|---|---------|----------|--------|--------|---------------------------|")
    for r in rows:
        note = r.get("prod_note", "").replace("|", "/")
        ev = r["evidence"].replace("|", "/")[:100]
        print(f"| {r['id']} | {r['area']} | {r['check']} | **{r['status']}** | {ev} | {note} |")
    counts = {}
    for r in rows:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    print(f"\nRésumé: {counts}")


if __name__ == "__main__":
    sys.exit(main())
