#!/usr/bin/env python3
"""Export Demo5 evidence gallery — images only for vitesse, feu, ceinture."""
from __future__ import annotations

import html
import json
import os
import shutil
import subprocess
import sys
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(os.environ.get("MICROTEST_ROOT", Path.home() / "citevision-v2"))
ORG = os.environ.get("DEMO_ORG_ID", "74d51ead-97a7-4e41-a488-503a9b90c466")
API = os.environ.get("BACKEND_API_URL", "http://127.0.0.1:8081").rstrip("/")
EMAIL = os.environ.get("ADMIN_EMAIL", "glory.henock@hologram.cd")
PASS = os.environ.get("ADMIN_PASSWORD", "Hologram2026!")
TS = os.environ.get("DEMO5_TS") or os.environ.get("TS") or ""

RULES = [
    ("vitesse", "Démo · Excès de vitesse", ["speeding"]),
    ("feu", "Démo · Feu rouge", ["red_light_violation"]),
    ("ceinture", "Démo · Non-port ceinture", ["seatbelt_violation"]),
]


def psql(sql: str) -> str:
    r = subprocess.run(
        [
            "docker", "exec", "citevision-v2-postgres",
            "psql", "-U", "citevision", "-d", "citevision", "-t", "-A", "-c", sql,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    return (r.stdout or "").strip()


def req(method: str, url: str, token: str | None = None, body: dict | None = None) -> dict:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(request, timeout=120) as resp:
        raw = resp.read().decode()
        return json.loads(raw) if raw else {}


def download_asset(token: str, asset_id: str, dest: Path) -> bool:
    if not asset_id:
        return False
    key = urllib.parse.quote(asset_id, safe="")
    url = f"{API}/api/v1/orgs/{ORG}/evidence/asset?key={key}"
    try:
        request = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
        with urllib.request.urlopen(request, timeout=120) as resp:
            data = resp.read()
        if not data or len(data) < 200:
            return False
        dest.write_bytes(data)
        return True
    except Exception as exc:
        print(f"  asset fail {asset_id[:48]}: {exc}", flush=True)
        return False


def main() -> int:
    if not TS:
        print("DEMO5_TS or TS required", file=sys.stderr)
        return 1
    out_wsl = ROOT / "validation-evidence" / f"demo5-{TS}"
    out_win = Path("/mnt/c/Users/gheno/citevision/validation-evidence") / f"demo5-{TS}"
    out_wsl.mkdir(parents=True, exist_ok=True)

    login = req("POST", f"{API}/api/v1/auth/login", body={"email": EMAIL, "password": PASS})
    tok = login["access_token"]

    cards: list[dict] = []
    summary: dict = {"ts": TS, "rules": []}

    for slug, rule_name, event_types in RULES:
        esc = rule_name.replace("'", "''")
        rule_row = psql(
            f"SELECT id::text FROM rules WHERE org_id='{ORG}'::uuid "
            f"AND name='{esc}' LIMIT 1;"
        )
        print(f"\n=== export {slug} rule={rule_name} ===", flush=True)
        rows: list[str] = []
        if rule_row:
            sql_alerts = (
                "SELECT a.id::text, a.created_at::text, coalesce(a.evidence_snapshot::text,'null'), "
                "coalesce(a.title,'') "
                f"FROM alerts a WHERE a.org_id='{ORG}'::uuid AND a.rule_id='{rule_row}'::uuid "
                "ORDER BY a.created_at DESC LIMIT 1;"
            )
            rows = [r for r in psql(sql_alerts).splitlines() if r.strip()]
            if not rows and event_types:
                types_sql = ",".join(f"'{t}'" for t in event_types)
                sql_events = (
                    "SELECT e.id::text, e.occurred_at::text, coalesce(e.evidence_snapshot::text,'null'), "
                    "coalesce(e.event_type,'') "
                    f"FROM events e WHERE e.org_id='{ORG}'::uuid "
                    f"AND e.event_type IN ({types_sql}) "
                    "AND e.evidence_snapshot IS NOT NULL "
                    "ORDER BY e.occurred_at DESC LIMIT 1;"
                )
                rows = [r for r in psql(sql_events).splitlines() if r.strip()]

        rule_summary: dict = {"slug": slug, "rule": rule_name, "hits": len(rows), "items": []}
        for idx, line in enumerate(rows, 1):
            parts = line.split("|")
            if len(parts) < 3:
                continue
            eid, ts, snap_raw = parts[0], parts[1], parts[2]
            try:
                snap = json.loads(snap_raw) if snap_raw and snap_raw != "null" else {}
            except json.JSONDecodeError:
                snap = {}
            pkg = snap.get("package") or snap or {}
            meta = pkg.get("metadata") or {}
            folder = out_wsl / slug / f"{idx:02d}_{eid[:8]}"
            folder.mkdir(parents=True, exist_ok=True)
            media: list[dict] = []
            for im in pkg.get("images") or []:
                role = str(im.get("role") or im.get("kind") or "image")
                aid = str(im.get("asset_id") or "")
                dest = folder / f"{role}.jpg"
                if download_asset(tok, aid, dest):
                    rel = str(dest.relative_to(out_wsl)).replace("\\", "/")
                    media.append({"role": role, "path": rel, "kind": "image"})
            for key in ("scene_asset_id", "subject_asset_id", "plate_asset_id"):
                aid = str(meta.get(key) or "")
                if not aid:
                    continue
                dest = folder / f"{key.replace('_asset_id', '')}.jpg"
                if dest.exists():
                    continue
                if download_asset(tok, aid, dest):
                    rel = str(dest.relative_to(out_wsl)).replace("\\", "/")
                    media.append({"role": key, "path": rel, "kind": "image"})
            item = {
                "id": eid,
                "ts": ts,
                "status": meta.get("evidence_status") or snap.get("status") or "",
                "capture_source": meta.get("capture_source"),
                "frigate_event_id": meta.get("frigate_event_id"),
                "media": media,
                "meta": meta,
            }
            rule_summary["items"].append(item)
            cards.append({"slug": slug, "rule": rule_name, **item})
            print(f"  {slug}#{idx} id={eid[:8]} images={len(media)}", flush=True)
        summary["rules"].append(rule_summary)

    (out_wsl / "summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8",
    )

    parts = [
        "<!doctype html><html><head><meta charset='utf-8'>",
        f"<title>Demo5 preuves — {html.escape(TS)}</title>",
        "<style>",
        "body{font-family:Segoe UI,system-ui,sans-serif;margin:24px;background:#0f1115;color:#e8eaed}",
        "h1{font-size:1.5rem} h2{font-size:1.15rem;margin:28px 0 12px;border-bottom:1px solid #333;padding-bottom:6px}",
        ".card{border:1px solid #2a2f3a;border-radius:12px;padding:16px;margin:0 0 20px;background:#171a21}",
        ".grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:12px}",
        "img{max-width:100%;background:#000;border:1px solid #333;border-radius:8px}",
        ".tag{display:inline-block;padding:2px 8px;border-radius:999px;background:#2a3140;margin:0 6px 6px 0;font-size:12px}",
        "pre{background:#0a0c10;padding:10px;border-radius:8px;overflow:auto;font-size:12px}",
        "a{color:#8ab4f8}",
        "</style></head><body>",
        f"<h1>Demo5 — preuves images (vitesse / feu / ceinture)</h1>",
        f"<p>Run <code>{html.escape(TS)}</code></p>",
    ]
    by_slug: dict[str, list] = {}
    for c in cards:
        by_slug.setdefault(c["slug"], []).append(c)
    for slug, rule_name, _ in RULES:
        parts.append(f"<h2>{html.escape(rule_name)}</h2>")
        items = by_slug.get(slug) or []
        if not items:
            parts.append("<div class='card'><p>Aucune alerte exportée pour cette règle.</p></div>")
            continue
        for it in items:
            parts.append("<div class='card'>")
            parts.append(
                f"<div><span class='tag'>status={html.escape(str(it.get('status') or ''))}</span>"
                f"<span class='tag'>src={html.escape(str(it.get('capture_source') or ''))}</span>"
                f"<span class='tag'>id={html.escape(str(it.get('id') or '')[:12])}</span></div>"
            )
            parts.append(f"<p>{html.escape(str(it.get('ts') or ''))}</p>")
            imgs = [m for m in (it.get("media") or []) if m.get("kind") == "image"]
            if imgs:
                parts.append("<div class='grid'>")
                for m in imgs:
                    pth = html.escape(m["path"])
                    role = html.escape(m["role"])
                    parts.append(f"<div><div>{role}</div><img src='{pth}' alt='{role}'></div>")
                parts.append("</div>")
            else:
                parts.append("<p><i>Pas d'image téléchargée.</i></p>")
            meta_show = {
                k: it["meta"].get(k)
                for k in (
                    "frigate_event_id", "align_delta_ms", "bbox_source",
                    "evidence_status", "vlm_reason", "speed_kmh",
                )
                if it.get("meta") and it["meta"].get(k) is not None
            }
            if meta_show:
                parts.append(
                    f"<pre>{html.escape(json.dumps(meta_show, indent=2, ensure_ascii=False))}</pre>"
                )
            parts.append("</div>")
    parts.append("<p><a href='summary.json'>summary.json</a></p>")
    parts.append("</body></html>")
    (out_wsl / "index.html").write_text("\n".join(parts), encoding="utf-8")

    if out_win.resolve() != out_wsl.resolve():
        out_win.parent.mkdir(parents=True, exist_ok=True)
        if out_win.exists():
            shutil.rmtree(out_win)
        shutil.copytree(out_wsl, out_win)

    print(f"\nWSL_OUT={out_wsl}", flush=True)
    print(f"WIN_OUT={out_win}", flush=True)
    print(f"Open: C:\\Users\\gheno\\citevision\\validation-evidence\\demo5-{TS}\\index.html", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
