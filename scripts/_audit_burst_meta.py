#!/usr/bin/env python3
"""Audit burst events using DB metadata (subject_texture stored by AI)."""
import json
import subprocess

EVENTS = [
    "0dc2f099-8031-49cd-8231-3367ccec66f9",
    "d49abb8f-89b1-407e-a92b-e2f6a7beafca",
    "b4a45f1c-3822-41fc-ac16-f3d5280b187c",
    "986ad754-4d1c-4d29-a9ed-8f310bc295c7",
    "3cc02696-073a-4007-940c-f869239bad32",
    "48e8270f-a73a-47f0-917a-b893995f3f4b",
    "71478677-0c0e-489c-9e60-646cea48389a",
    "6b1dc4fa-13e9-497a-a2b6-03b1fb7844b5",
    "ff4e8617-e7f3-48c1-a33b-dd77b1a0423c",
    "176c7a02-656b-401c-b44f-a4c120a5e52d",
]

def q(sql):
    r = subprocess.run(
        ["docker", "exec", "citevision-v2-postgres", "psql", "-U", "citevision", "-d", "citevision", "-t", "-A", "-c", sql],
        capture_output=True, text=True,
    )
    return r.stdout.strip()

ok = 0
complete_bad = 0
for eid in EVENTS:
    raw = q(f"SELECT evidence_snapshot::text FROM events WHERE id='{eid}';")
    snap = json.loads(raw)
    meta = (snap.get("package") or {}).get("metadata") or {}
    tex = meta.get("subject_texture")
    src = meta.get("bbox_source")
    status = meta.get("evidence_status")
    sq = meta.get("subject_quality_ok")
    bq = meta.get("bbox_quality_ok")
    good = tex is not None and tex >= 50 and status != "complete" or (status == "complete" and tex is not None and tex >= 50 and bq is not False)
    # Plan: OK = texture >= 50; complete must not have texture < 50
    verdict = "OK" if tex is not None and tex >= 50 else "KO"
    if status == "complete" and tex is not None and tex < 50:
        complete_bad += 1
    if verdict == "OK":
        ok += 1
    print(f"{eid[:8]} status={status} src={src} tex={tex} subj_ok={sq} bbox_ok={bq} -> {verdict}")

print(f"\nOK={ok}/10 complete_with_low_tex={complete_bad}")
