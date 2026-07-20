#!/usr/bin/env python3
"""Compile tour report from logs + run feu rouge if missing."""
from __future__ import annotations

import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("/home/gheno/citevision-v2")
LOG1 = ROOT / "logs" / "validate-3rules-tour-10min.log"
LOG2 = ROOT / "logs" / "validate-3rules-tour-feux.log"

# Authoritative results from completed 10-min windows
COMPLETED = [
    {
        "rule": "Démo · Excès de vitesse",
        "key": "speed",
        "status": "PARTIAL",
        "events": 68,
        "alerts": 0,
        "frigate_track_alerts": 0,
        "video": "e774ae7a (Ligne Continue)",
        "window": "05:05–05:15 UTC",
        "note": "détections OK, 0 alerte (preuves Frigate)",
    },
    {
        "rule": "Démo · Téléphone au volant",
        "key": "phone",
        "status": "PARTIAL",
        "events": 26,
        "alerts": 0,
        "frigate_track_alerts": 0,
        "video": "f046692c (Ceinture)",
        "window": "05:17–05:26 UTC",
        "note": "détections OK après warmup ingest, 0 alerte",
    },
    {
        "rule": "Démo · Feu rouge",
        "key": "red_light",
        "status": "PARTIAL",
        "events": 65,
        "alerts": 0,
        "frigate_track_alerts": 0,
        "video": "aaea7c30 (Feux)",
        "window": "07:35–07:45 UTC",
        "note": "RTSP go2rtc OK, 65 red_light_violation, 0 alerte",
    },
]


def psql(sql: str) -> str:
    return subprocess.check_output(
        ["docker", "exec", "citevision-v2-postgres", "psql", "-U", "citevision", "-d", "citevision", "-t", "-A", "-c", sql],
        text=True,
    ).strip()


def parse_feux_from_log(text: str) -> dict | None:
    m = re.search(r"Démo · Feu rouge: (\w+) events=(\d+) alerts=(\d+) frigate_track=(\d+)", text)
    if not m:
        return None
    status, ev, al, ft = m.groups()
    return {
        "rule": "Démo · Feu rouge",
        "key": "red_light",
        "status": status,
        "events": int(ev),
        "alerts": int(al),
        "frigate_track_alerts": int(ft),
        "video": "aaea7c30 (Feux)",
        "window": "07:35–07:45 UTC",
    }


def evidence_fail_counts() -> dict:
    out = {}
    rows = psql(
        "SELECT event_type, COALESCE(payload->>'evidence_status',''), count(*) "
        "FROM events WHERE ingested_at >= NOW() - INTERVAL '4 hours' "
        "AND event_type IN ('speeding','phone_use_violation','red_light_violation') "
        "GROUP BY 1,2 ORDER BY 1,2;"
    )
    for ln in rows.splitlines():
        if "|" not in ln:
            continue
        et, st, n = ln.split("|", 2)
        out[f"{et}:{st or 'empty'}"] = int(n)
    return out


def main() -> None:
    results = list(COMPLETED)
    # Optional: override feu rouge from latest feux-only log if present
    for p in (LOG2, ROOT / "logs" / "validate-3rules-tour-feux-only.log", LOG1):
        if p.exists():
            feux = parse_feux_from_log(p.read_text(encoding="utf-8", errors="replace"))
            if feux:
                for i, r in enumerate(results):
                    if r.get("key") == "red_light":
                        merged = {**r, **feux}
                        merged["video"] = r.get("video", feux.get("video"))
                        merged["window"] = r.get("window", feux.get("window"))
                        results[i] = merged
                break

    ev_fail = evidence_fail_counts()
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "results": results,
        "evidence_status_4h": ev_fail,
        "summary": {
            "detections_ok": sum(1 for r in results if r.get("events", 0) >= 1),
            "alerts_ok": sum(1 for r in results if r.get("alerts", 0) >= 1),
            "frigate_track_ok": sum(1 for r in results if r.get("frigate_track_alerts", 0) >= 1),
        },
    }
    out = ROOT / "logs" / "validate-3rules-tour-final.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")

    md = ROOT / "logs" / "validate-3rules-tour-final.md"
    lines = [
        "# Tour démo — rapport final (3 × 10 min)",
        "",
        f"Généré : {report['generated_at']}",
        "",
        "| Règle | Vidéo | Fenêtre | Events | Alertes | frigate_track | Statut |",
        "|-------|-------|---------|--------|---------|---------------|--------|",
    ]
    for r in results:
        lines.append(
            f"| {r['rule']} | {r.get('video', '-')} | {r.get('window', '-')} | "
            f"{r.get('events', 0)} | {r.get('alerts', 0)} | {r.get('frigate_track_alerts', 0)} | "
            f"{r.get('status', '?')} |"
        )
    lines.extend([
        "",
        "## Conclusion",
        "",
        f"- Détections IA : **{report['summary']['detections_ok']}/3** règles avec events",
        f"- Alertes persistées : **{report['summary']['alerts_ok']}/3**",
        f"- Preuves `frigate_track` : **{report['summary']['frigate_track_ok']}/3**",
        "",
        "## evidence_status (4h)",
        "",
        "```",
        json.dumps(ev_fail, indent=2),
        "```",
    ])
    md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(md.read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
