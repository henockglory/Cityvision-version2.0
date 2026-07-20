#!/usr/bin/env python3
"""Diagnostic H1/H2 stale capture — read-only dump dated 20260719."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(os.path.expanduser("~/citevision-v2"))
OUT = ROOT / "validation-evidence" / "_diag_stale_capture_20260719"
LOOP_SEC = 352.52
ORG = "74d51ead-97a7-4e41-a488-503a9b90c466"

ALIASES = ("speeding", "red_light", "phone", "seatbelt", "counting")


def load_env() -> dict[str, str]:
    out: dict[str, str] = {}
    p = ROOT / ".env"
    if not p.is_file():
        return out
    for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, _, v = s.partition("=")
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def pg(sql: str) -> list[list[str]]:
    r = subprocess.run(
        [
            "docker", "exec", "citevision-v2-postgres",
            "psql", "-U", "citevision", "-d", "citevision",
            "-t", "-A", "-F", "\t", "-c", sql,
        ],
        capture_output=True, text=True, timeout=120,
    )
    if r.returncode != 0:
        raise RuntimeError(r.stderr or r.stdout)
    rows = []
    for line in r.stdout.splitlines():
        if line.strip():
            rows.append(line.split("\t"))
    return rows


def dig(obj: Any, *keys: str) -> Any:
    if not isinstance(obj, dict):
        return None
    for k in keys:
        if k in obj and obj[k] is not None:
            return obj[k]
    for v in obj.values():
        if isinstance(v, dict):
            got = dig(v, *keys)
            if got is not None:
                return got
    return None


def md5b(data: bytes) -> str:
    return hashlib.md5(data).hexdigest()


def http_get(url: str, headers: dict | None = None, timeout: int = 45) -> bytes | None:
    req = urllib.request.Request(url, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read()
    except Exception as e:
        print(f"  GET fail {url[:100]}: {e}")
        return None


def classify(et: str, title: str) -> str | None:
    s = f"{et} {title}".lower()
    if "speed" in s or "vitesse" in s:
        return "speeding"
    if "red_light" in s or "feu" in s:
        return "red_light"
    if "phone" in s or "téléphone" in s or "telephone" in s:
        return "phone"
    if "seatbelt" in s or "ceinture" in s:
        return "seatbelt"
    if "line_cross" in s or "compt" in s or "count" in s or "décompte" in s or "decompte" in s:
        return "counting"
    return None


def parse_ts(raw: str) -> float | None:
    try:
        s = str(raw).strip()
        if " " in s and "T" not in s:
            s = s.replace(" ", "T", 1)
        if s.endswith("+00"):
            s = s + ":00"
        if "+" not in s[10:] and "Z" not in s:
            s += "+00:00"
        return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()
    except Exception:
        return None


def login(env: dict) -> str | None:
    email = env.get("DEMO_EMAIL") or env.get("ADMIN_EMAIL") or "glory.henock@hologram.cd"
    for key in ("DEMO_PASS", "ADMIN_PASSWORD", "DEMO_PASSWORD"):
        pw = env.get(key) or ""
        if not pw:
            continue
        body = json.dumps({"email": email, "password": pw}).encode()
        req = urllib.request.Request(
            "http://127.0.0.1:8081/api/v1/auth/login",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                tok = json.loads(resp.read().decode()).get("access_token")
                if tok:
                    print(f"login OK ({email})")
                    return tok
        except Exception as e:
            print(f"login fail {key}: {e}")
    return None


def select_spaced(rows: list[list[str]], n: int = 5) -> tuple[list[tuple[list[str], float | None]], bool]:
    """rows: [id, created, et, event_id, cam, title, snap, payload]"""
    selected: list[tuple[list[str], float | None]] = []
    last = None
    for row in rows:
        ts = parse_ts(row[1])
        if last is None or ts is None or abs(ts - last) >= LOOP_SEC * 0.9:
            selected.append((row, ts))
            if ts is not None:
                last = ts
        if len(selected) >= n:
            break
    if len(selected) < n:
        selected = [(r, parse_ts(r[1])) for r in rows[:n]]
    spaced = False
    if len(selected) >= 2:
        gaps = []
        for i in range(1, len(selected)):
            a, b = selected[i - 1][1], selected[i][1]
            if a is not None and b is not None:
                gaps.append(abs(a - b))
        spaced = bool(gaps) and all(g >= LOOP_SEC * 0.9 for g in gaps)
    return selected, spaced


def main() -> None:
    env = load_env()
    OUT.mkdir(parents=True, exist_ok=True)
    print("OUT", OUT)

    # --- H2 zones ---
    h2: dict[str, Any] = {
        "status": "PENDING_HUMAN_ZONEEDITOR",
        "note": "P.135 — dump lecture seule; confirmation visuelle ZoneEditor = action humaine",
        "loop_sec": LOOP_SEC,
        "cameras": [],
        "zones": [],
        "lines": [],
    }
    cams = pg(
        """SELECT id::text, name FROM cameras
           WHERE name ILIKE '%Démo%' OR name ILIKE '%Demo%'
              OR name ILIKE '%Feux%' OR name ILIKE '%Ceinture%'
              OR name ILIKE '%Décompte%' OR name ILIKE '%Ligne Continue%'
           ORDER BY name;"""
    )
    h2["cameras"] = [{"id": r[0], "name": r[1]} for r in cams]
    zones = pg(
        """SELECT c.name, z.name, z.zone_kind, z.polygon::text
           FROM zones z JOIN cameras c ON c.id=z.camera_id
           WHERE c.name ILIKE '%Démo%' OR c.name ILIKE '%Demo%'
              OR c.name ILIKE '%Feux%' OR c.name ILIKE '%Ceinture%'
              OR c.name ILIKE '%Décompte%' OR c.name ILIKE '%Ligne%'
           ORDER BY c.name, z.name;"""
    )
    for r in zones:
        poly = []
        try:
            poly = json.loads(r[3])
        except Exception:
            poly = r[3][:200]
        # bbox of polygon for human sanity
        xs = [float(p["x"]) for p in poly] if isinstance(poly, list) and poly and isinstance(poly[0], dict) else []
        ys = [float(p["y"]) for p in poly] if xs else []
        h2["zones"].append({
            "camera": r[0], "zone": r[1], "kind": r[2],
            "x_range": [min(xs), max(xs)] if xs else None,
            "y_range": [min(ys), max(ys)] if ys else None,
            "n_points": len(xs),
            "polygon": poly,
        })
    lines = pg(
        """SELECT c.name, l.name, l.start_point::text, l.end_point::text
           FROM lines l JOIN cameras c ON c.id=l.camera_id
           WHERE c.name ILIKE '%Démo%' OR c.name ILIKE '%Demo%'
              OR c.name ILIKE '%Décompte%' OR c.name ILIKE '%Ligne%'
           ORDER BY c.name, l.name;"""
    )
    for r in lines:
        h2["lines"].append({"camera": r[0], "line": r[1], "start": r[2], "end": r[3]})
    # Agent cannot confirm visual framing — flag geometry presence only
    h2["agent_geometry_presence"] = {
        "feux_has_observation_and_light": any(z["zone"] == "Zone_Observation" for z in h2["zones"])
            and any(z["zone"] == "Zone_des_feux" for z in h2["zones"]),
        "speed_has_distance_zone": any(z["zone"] == "Zone_distance_parcourue" for z in h2["zones"]),
        "cabin_has_phone_and_seatbelt": any(z["zone"] == "Zone_bbox" for z in h2["zones"])
            and any(z["zone"] == "Zone_bbox2" for z in h2["zones"]),
        "counting_has_line": any(ln["line"] == "Ligne_count" for ln in h2["lines"]),
    }
    (OUT / "H2_zones_dump.json").write_text(json.dumps(h2, indent=2, ensure_ascii=False), encoding="utf-8")
    print("H2 cameras", len(h2["cameras"]), "zones", len(h2["zones"]), "lines", len(h2["lines"]))

    token = login(env)
    headers = {}
    if token:
        headers = {"Authorization": f"Bearer {token}", "X-Org-ID": ORG}

    # --- Alerts last 72h ---
    alerts = pg(
        f"""
        SELECT a.id::text,
               a.created_at AT TIME ZONE 'UTC',
               COALESCE(e.event_type, '')::text,
               COALESCE(e.id::text, ''),
               COALESCE(e.camera_id::text, ''),
               COALESCE(a.title, ''),
               COALESCE(a.evidence_snapshot::text, '{{}}'),
               COALESCE(e.payload::text, '{{}}'),
               COALESCE(e.evidence_snapshot::text, '{{}}')
        FROM alerts a
        LEFT JOIN events e ON e.id = a.event_id
        WHERE a.org_id = '{ORG}'::uuid
          AND a.created_at > NOW() - INTERVAL '72 hours'
        ORDER BY a.created_at DESC
        LIMIT 200;
        """
    )
    print("alerts", len(alerts))

    by: dict[str, list] = {a: [] for a in ALIASES}
    for row in alerts:
        alias = classify(row[2], row[5])
        if alias:
            by[alias].append(row)
    for k, v in by.items():
        print(f"  {k}: {len(v)}")

    frigate = (env.get("FRIGATE_URL") or "http://127.0.0.1:5000").rstrip("/")
    diag: list[dict] = []

    for alias in ALIASES:
        adir = OUT / alias
        adir.mkdir(parents=True, exist_ok=True)
        selected, spaced = select_spaced(by[alias], 5)
        rule_events: list[dict] = []
        md5s: list[str] = []
        tracks: list[str] = []
        frigs: list[str] = []
        sources: list[str] = []

        for i, (row, ts) in enumerate(selected):
            slot = adir / f"evt_{i+1:02d}"
            slot.mkdir(parents=True, exist_ok=True)
            alert_id, created, et, event_id, cam_id, title = row[0], row[1], row[2], row[3], row[4], row[5]
            snap_a, payload, snap_e = {}, {}, {}
            for raw, target in ((row[6], "a"), (row[7], "p"), (row[8], "e")):
                try:
                    obj = json.loads(raw) if raw else {}
                except Exception:
                    obj = {"_raw": str(raw)[:300]}
                if target == "a":
                    snap_a = obj
                elif target == "p":
                    payload = obj
                else:
                    snap_e = obj

            ia = {
                "alert_id": alert_id,
                "event_id": event_id,
                "event_type": et,
                "created_at": str(created),
                "camera_id": cam_id,
                "title": title,
                "payload": payload,
                "alert_evidence_snapshot": snap_a,
                "event_evidence_snapshot": snap_e,
            }
            (slot / "ia_event.json").write_text(json.dumps(ia, indent=2, ensure_ascii=False, default=str), encoding="utf-8")

            meta: dict[str, Any] = {
                "alias": alias,
                "slot": i + 1,
                "alert_id": alert_id,
                "event_id": event_id,
                "event_type": et,
                "created_at": str(created),
                "created_ts": ts,
                "camera_id": cam_id,
                "title": title,
                "capture_source": None,
                "frigate_event_id": None,
                "track_id": None,
                "align_delta_ms": None,
                "bbox_ts": None,
                "bbox": None,
                "scene_md5": None,
                "scene_bytes": 0,
            }
            for blob in (snap_a, snap_e, payload, snap_a.get("package") if isinstance(snap_a.get("package"), dict) else {}):
                if not isinstance(blob, dict):
                    continue
                meta["capture_source"] = meta["capture_source"] or dig(blob, "capture_source")
                meta["frigate_event_id"] = meta["frigate_event_id"] or dig(blob, "frigate_event_id", "frigate_id")
                meta["track_id"] = meta["track_id"] if meta["track_id"] is not None else dig(blob, "track_id")
                ad = dig(blob, "align_delta_ms", "align_delta")
                if ad is not None and meta["align_delta_ms"] is None:
                    # normalize to ms
                    try:
                        fv = float(ad)
                        meta["align_delta_ms"] = fv if abs(fv) > 1000 else fv * 1000.0
                    except Exception:
                        meta["align_delta_ms"] = ad
                meta["bbox_ts"] = meta["bbox_ts"] or dig(blob, "bbox_ts")
                meta["bbox"] = meta["bbox"] or dig(blob, "bbox")

            # track_id often on payload
            if meta["track_id"] is None:
                meta["track_id"] = payload.get("track_id")
            if meta["bbox_ts"] is None:
                meta["bbox_ts"] = payload.get("bbox_ts") or dig(payload, "bbox_ts")

            # Download scene
            scene_url = None
            images = []
            for snap in (snap_a, snap_e):
                pkg = snap.get("package") if isinstance(snap, dict) else None
                if isinstance(pkg, dict) and isinstance(pkg.get("images"), list):
                    images = pkg["images"]
                    break
                if isinstance(snap, dict) and isinstance(snap.get("images"), list):
                    images = snap["images"]
                    break
            for im in images:
                if str(im.get("role") or "") == "scene" and im.get("url"):
                    scene_url = im["url"]
                    break
            if not scene_url and images:
                scene_url = images[0].get("url")

            scene_bytes = None
            if scene_url and headers:
                url = scene_url.replace("http://localhost:8081", "http://127.0.0.1:8081")
                scene_bytes = http_get(url, headers)
            if scene_bytes and scene_bytes[:2] == b"\xff\xd8":
                (slot / "scene.jpg").write_bytes(scene_bytes)
                meta["scene_md5"] = md5b(scene_bytes)
                meta["scene_bytes"] = len(scene_bytes)
                md5s.append(meta["scene_md5"])
                (slot / "scene.md5").write_text(meta["scene_md5"] + "\n")

            # Frigate
            fid = meta["frigate_event_id"]
            if fid:
                frigs.append(str(fid))
                raw = http_get(f"{frigate}/api/events/{fid}")
                if raw:
                    (slot / "frigate_event.json").write_bytes(raw)
                    try:
                        fe = json.loads(raw.decode())
                        meta["frigate_start_time"] = fe.get("start_time")
                        meta["frigate_end_time"] = fe.get("end_time")
                        meta["frigate_box"] = (fe.get("data") or {}).get("box")
                        meta["frigate_label"] = fe.get("label")
                    except Exception:
                        pass

            if meta["track_id"] is not None:
                tracks.append(str(meta["track_id"]))
            if meta["capture_source"]:
                sources.append(str(meta["capture_source"]))

            (slot / "meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
            rule_events.append(meta)
            print(
                f"  {alias}#{i+1} {str(created)[:19]} md5={meta['scene_md5']} "
                f"track={meta['track_id']} frig={meta['frigate_event_id']} "
                f"src={meta['capture_source']} align_ms={meta['align_delta_ms']}"
            )

        # H1 signals
        unique_md5 = len(set(md5s))
        unique_tr = len(set(tracks))
        unique_fr = len(set(frigs))
        h1 = "INCONCLUSIVE"
        cause = "insufficient_fields"
        if len(rule_events) == 0:
            h1, cause = "NO_DATA", "no_alerts_72h"
        elif spaced and tracks and unique_tr == 1 and len(tracks) >= 2:
            h1, cause = "CONFIRMED", "bytetrack_id_persists_across_loop"
        elif spaced and frigs and unique_fr == 1 and len(frigs) >= 2:
            h1, cause = "CONFIRMED", "frigate_event_id_reused_across_loop"
        elif (not spaced) and md5s and unique_md5 == 1 and len(md5s) >= 2:
            h1, cause = "SUSPECTED", "identical_scene_md5_but_events_not_loop_spaced"
        elif md5s and unique_md5 == 1 and len(md5s) >= 2 and (unique_fr == 1 or unique_tr == 1):
            h1, cause = "CONFIRMED", "identical_md5_with_frozen_identity"
        elif md5s and unique_md5 == len(md5s) and (unique_tr == len(tracks) or not tracks) and (unique_fr == len(frigs) or not frigs):
            h1, cause = "INFIRMED", "identities_and_md5_change"
        elif not md5s:
            h1, cause = "INCONCLUSIVE", "no_scene_downloaded"

        entry = {
            "alias": alias,
            "n_alerts_72h": len(by[alias]),
            "n_selected": len(selected),
            "spaced_ge_loop": spaced,
            "n_with_scene": len(md5s),
            "unique_md5": unique_md5,
            "md5s": md5s,
            "track_ids": tracks,
            "unique_tracks": unique_tr,
            "frigate_ids": frigs,
            "unique_frigate_ids": unique_fr,
            "capture_sources": sorted(set(sources)),
            "align_delta_ms": [e.get("align_delta_ms") for e in rule_events],
            "H1": h1,
            "H1_cause": cause,
            "events": rule_events,
        }
        diag.append(entry)
        (adir / "rule_diag.json").write_text(json.dumps(entry, indent=2, ensure_ascii=False, default=str), encoding="utf-8")

    (OUT / "diag_raw.json").write_text(json.dumps(diag, indent=2, ensure_ascii=False, default=str), encoding="utf-8")

    # SUMMARY.md
    lines = [
        "# SUMMARY — capture figée / H1 vs H2 — 2026-07-19",
        "",
        "## Étape 0 — H2 (zones)",
        "",
        f"- Status: **{h2['status']}** (confirmation visuelle ZoneEditor = humaine, P.135).",
        f"- Géométries présentes en DB: `{json.dumps(h2['agent_geometry_presence'])}`.",
        "- Dump: `H2_zones_dump.json`.",
        "- Agent: **ne peut pas** valider le cadrage pixel ; H2 **non éliminé définitivement** sans review humaine.",
        "- Pour la suite: H1 testé quand même sur les artefacts d'alertes (les alertes existent → zones ont produit des hits).",
        "",
        "## Étape 1 — H1 par règle",
        "",
        f"Critère d'espacement cible: ≥ {LOOP_SEC}s (1 boucle). Si non respecté → noté `spaced_ge_loop=false`.",
        "",
        "| Règle | n | spaced | scenes | unique MD5 | tracks | unique tracks | Frigate IDs | unique Frig | H1 | cause | A4 sources |",
        "|-------|---|--------|--------|------------|--------|---------------|-------------|-------------|----|-------|------------|",
    ]
    for e in diag:
        lines.append(
            f"| {e['alias']} | {e['n_selected']} | {e['spaced_ge_loop']} | {e['n_with_scene']} | "
            f"{e['unique_md5']} | {e['track_ids']} | {e['unique_tracks']} | {e['frigate_ids']} | "
            f"{e['unique_frigate_ids']} | **{e['H1']}** | {e['H1_cause']} | {e['capture_sources']} |"
        )
    lines += [
        "",
        "## Interprétation A4 (cross-path)",
        "",
    ]
    ring = [e for e in diag if "demo_ring_buffer" in e.get("capture_sources", [])]
    frig = [e for e in diag if "frigate_track" in e.get("capture_sources", [])]
    lines.append(f"- Règles avec `demo_ring_buffer`: {[e['alias'] for e in ring]}")
    lines.append(f"- Règles avec `frigate_track`: {[e['alias'] for e in frig]}")
    lines.append("")
    confirmed = [e for e in diag if e["H1"] == "CONFIRMED"]
    infirm = [e for e in diag if e["H1"] == "INFIRMED"]
    lines.append(f"- H1 CONFIRMED: {[e['alias'] for e in confirmed] or 'aucun'}")
    lines.append(f"- H1 INFIRMED: {[e['alias'] for e in infirm] or 'aucun'}")
    lines.append("")
    lines.append("## Décision correction (§3)")
    lines.append("")
    if confirmed:
        lines.append("- **Autorisé** à appliquer §3 uniquement sur: " + ", ".join(e["alias"] for e in confirmed))
        causes = {e["H1_cause"] for e in confirmed}
        if any("frigate" in c for c in causes):
            lines.append("- Système Frigate: §3.1 + §3.2")
        if any("bytetrack" in c for c in causes):
            lines.append("- Système ByteTrack: §3.3")
    else:
        lines.append("- **Pas de correction §3** tant que H1 n'est pas CONFIRMED (données insuffisantes / H1 infirmé / H2 pending).")
    lines.append("")
    lines.append(f"Généré: {datetime.utcnow().isoformat()}Z")
    (OUT / "SUMMARY.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("Wrote SUMMARY.md")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
