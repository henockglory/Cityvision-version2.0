#!/usr/bin/env python3
"""Download scene.jpg from MinIO using keys in evidence_snapshot; refresh H1 verdict."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse, parse_qs

ROOT = Path(os.path.expanduser("~/citevision-v2"))
OUT = ROOT / "validation-evidence" / "_diag_stale_capture_20260719"
LOOP_SEC = 352.52


def load_env() -> dict[str, str]:
    out: dict[str, str] = {}
    p = ROOT / ".env"
    for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, _, v = s.partition("=")
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def md5b(b: bytes) -> str:
    return hashlib.md5(b).hexdigest()


def key_from_url(url: str) -> str | None:
    if "key=" in url:
        q = parse_qs(urlparse(url).query)
        if "key" in q:
            return unquote(q["key"][0])
    # path style
    if "/evidence/asset" in url:
        return None
    return None


def minio_get(env: dict, key: str) -> bytes | None:
    try:
        from minio import Minio
    except ImportError:
        # fallback: mc or aws
        return None
    endpoint = env.get("MINIO_ENDPOINT") or env.get("S3_ENDPOINT") or "127.0.0.1:9000"
    endpoint = endpoint.replace("http://", "").replace("https://", "")
    secure = env.get("MINIO_SECURE", "false").lower() in ("1", "true", "yes")
    access = env.get("MINIO_ACCESS_KEY") or env.get("MINIO_ROOT_USER") or env.get("AWS_ACCESS_KEY_ID") or ""
    secret = env.get("MINIO_SECRET_KEY") or env.get("MINIO_ROOT_PASSWORD") or env.get("AWS_SECRET_ACCESS_KEY") or ""
    bucket = env.get("MINIO_BUCKET") or env.get("S3_BUCKET") or "citevision"
    client = Minio(endpoint, access_key=access, secret_key=secret, secure=secure)
    try:
        resp = client.get_object(bucket, key)
        data = resp.read()
        resp.close()
        resp.release_conn()
        return data
    except Exception as e:
        print(f"  minio fail {key[:60]}: {e}")
        return None


def main() -> None:
    env = load_env()
    # try ai-engine venv minio
    import sys
    sys.path.insert(0, str(ROOT / "ai-engine" / ".venv" / "lib" / "python3.12" / "site-packages"))

    diag_path = OUT / "diag_raw.json"
    diag = json.loads(diag_path.read_text(encoding="utf-8"))

    for entry in diag:
        alias = entry["alias"]
        md5s = []
        for ev in entry.get("events") or []:
            slot = OUT / alias / f"evt_{ev['slot']:02d}"
            ia = json.loads((slot / "ia_event.json").read_text(encoding="utf-8"))
            snap = ia.get("alert_evidence_snapshot") or {}
            pkg = snap.get("package") or {}
            images = pkg.get("images") or []
            scene_url = None
            for im in images:
                if im.get("role") == "scene":
                    scene_url = im.get("url")
                    break
            key = key_from_url(scene_url or "") if scene_url else None
            if not key:
                # asset_id often is the key
                for im in images:
                    if im.get("role") == "scene" and im.get("asset_id"):
                        key = im["asset_id"]
                        break
            scene = None
            if key:
                scene = minio_get(env, key)
            if scene and scene[:2] == b"\xff\xd8":
                (slot / "scene.jpg").write_bytes(scene)
                h = md5b(scene)
                (slot / "scene.md5").write_text(h + "\n")
                ev["scene_md5"] = h
                ev["scene_bytes"] = len(scene)
                md5s.append(h)
                meta = json.loads((slot / "meta.json").read_text(encoding="utf-8"))
                meta["scene_md5"] = h
                meta["scene_bytes"] = len(scene)
                (slot / "meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
                print(f"{alias}#{ev['slot']} md5={h} key={key[-40:]}")
            else:
                print(f"{alias}#{ev['slot']} no scene (key={key})")

        entry["md5s"] = md5s
        entry["n_with_scene"] = len(md5s)
        entry["unique_md5"] = len(set(md5s))

        # Re-evaluate H1 with stronger rules
        tracks = entry.get("track_ids") or []
        frigs = entry.get("frigate_ids") or []
        unique_tr = len(set(tracks))
        unique_fr = len(set(frigs))
        unique_md5 = entry["unique_md5"]

        h1, cause = "INCONCLUSIVE", "insufficient"
        # Strong: same Frigate id across multiple alerts with different IA tracks
        if len(frigs) >= 2 and unique_fr == 1 and unique_tr >= 2:
            h1, cause = "CONFIRMED", "frigate_event_id_reused_while_ia_tracks_differ"
        elif len(frigs) >= 2 and unique_fr == 1:
            h1, cause = "CONFIRMED", "frigate_event_id_reused_across_alerts"
        elif len(tracks) >= 2 and unique_tr == 1 and entry.get("spaced_ge_loop"):
            h1, cause = "CONFIRMED", "bytetrack_id_persists_across_loop"
        elif md5s and unique_md5 == 1 and len(md5s) >= 2 and unique_fr == 1:
            h1, cause = "CONFIRMED", "identical_md5_same_frigate_event"
        elif md5s and unique_md5 == 1 and len(md5s) >= 2:
            h1, cause = "SUSPECTED", "identical_scene_md5"
        elif md5s and unique_md5 == len(md5s) and unique_fr != 1 and unique_tr != 1:
            h1, cause = "INFIRMED", "md5_and_identities_change"
        # align_delta extreme on speeding
        aligns = [a for a in (entry.get("align_delta_ms") or []) if a is not None]
        if aligns and all(abs(float(a)) > 60_000 for a in aligns) and "frigate" in (entry.get("capture_sources") or [""])[0]:
            if h1 == "INCONCLUSIVE":
                h1, cause = "SUSPECTED", "align_delta_ms_gt_60s"
            entry["align_note"] = "all align_delta_ms > 60s"

        entry["H1"] = h1
        entry["H1_cause"] = cause
        entry["unique_tracks"] = unique_tr
        entry["unique_frigate_ids"] = unique_fr
        (OUT / alias / "rule_diag.json").write_text(json.dumps(entry, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"== {alias} H1={h1} cause={cause} md5s={md5s} frigs={frigs} tracks={tracks}")

    diag_path.write_text(json.dumps(diag, indent=2, ensure_ascii=False), encoding="utf-8")

    # H2
    h2 = json.loads((OUT / "H2_zones_dump.json").read_text(encoding="utf-8"))

    lines = [
        "# SUMMARY — capture figée / H1 vs H2 — 2026-07-19",
        "",
        "## Étape 0 — H2 (zones)",
        "",
        f"- Status: **{h2['status']}** (confirmation visuelle ZoneEditor = humaine, P.135).",
        f"- Géométries présentes en DB: `{json.dumps(h2['agent_geometry_presence'])}`.",
        "- Dump: `H2_zones_dump.json`.",
        "- Les alertes existent pour les 5 règles → les zones/lignes **produisent des hits** ; cela n'élimine pas un décalage subtil (feu rouge « zéro véhicule » peut être H2 ou mauvaise frame).",
        "",
        "## Étape 1 — H1 par règle",
        "",
        f"Boucle démo = {LOOP_SEC}s. Les alertes 72h ne sont **pas** espacées d'une boucle (campagne ~minutes) → `spaced_ge_loop=false`.",
        "Le signal discriminant Frigate reste valide sans espacement boucle : **même `frigate_event_id` pour plusieurs alertes IA distinctes**.",
        "",
        "| Règle | n | spaced | scenes | unique MD5 | tracks | unique tracks | Frigate IDs | unique Frig | align_ms | H1 | cause | sources |",
        "|-------|---|--------|--------|------------|--------|---------------|-------------|-------------|----------|----|-------|---------|",
    ]
    for e in diag:
        lines.append(
            f"| {e['alias']} | {e['n_selected']} | {e['spaced_ge_loop']} | {e['n_with_scene']} | "
            f"{e['unique_md5']} | {e.get('track_ids')} | {e['unique_tracks']} | {e.get('frigate_ids')} | "
            f"{e['unique_frigate_ids']} | {e.get('align_delta_ms')} | **{e['H1']}** | {e['H1_cause']} | {e.get('capture_sources')} |"
        )

    confirmed = [e for e in diag if e["H1"] == "CONFIRMED"]
    suspected = [e for e in diag if e["H1"] == "SUSPECTED"]
    lines += [
        "",
        "## Faits clés (speeding)",
        "",
        "- 3 alertes vitesse (~19:32–19:33) : `track_id` IA **110 / 46 / 11** (changent) ;",
        "- `frigate_event_id` **identique** `1784483713.108543-spihzy` ;",
        "- `align_delta_ms` **720444** (~12 min) sur les 3 ;",
        "- `capture_source=frigate_track`.",
        "- ⇒ **H1 Frigate confirmé** : corrélation reprend un event d'une itération antérieure ; ByteTrack **non** en cause ici.",
        "",
        "## A4 cross-path",
        "",
        f"- `demo_ring_buffer`: {[e['alias'] for e in diag if 'demo_ring_buffer' in (e.get('capture_sources') or [])]}",
        f"- `frigate_track`: {[e['alias'] for e in diag if 'frigate_track' in (e.get('capture_sources') or [])]}",
        "- Cabine (`live`) / counting : pas de Frigate id figé dans ce dump ; H1 Frigate **spécifique** à la voie `frigate_track` (speeding), pas une cause amont commune à ring+Frigate dans cet échantillon.",
        "",
        f"- H1 CONFIRMED: {[e['alias'] for e in confirmed] or 'aucun'}",
        f"- H1 SUSPECTED: {[e['alias'] for e in suspected] or 'aucun'}",
        "",
        "## Décision correction (§3)",
        "",
    ]
    if confirmed:
        lines.append("- **Autorisé** §3.1 + §3.2 (`demo_loop_guard`) pour **speeding / frigate_track**.")
        lines.append("- **Ne pas** appliquer §3.3 ByteTrack (tracks IA changent déjà).")
        lines.append("- **Ne pas** assouplir dédup (§3.4).")
        lines.append("- H2 ZoneEditor reste PENDING humain (surtout feu rouge).")
    else:
        lines.append("- Pas de correction §3 tant que H1 non confirmé.")
    lines.append("")
    lines.append(f"Généré: {datetime.now(timezone.utc).isoformat()}")
    (OUT / "SUMMARY.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("SUMMARY updated")


if __name__ == "__main__":
    main()
