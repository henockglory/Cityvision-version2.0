#!/usr/bin/env python3
"""Emit honest PASS/FAIL for 138 roadmap points from ROADMAP-138-STATUS.json."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
data = json.loads((ROOT / "docs/ROADMAP-138-STATUS.json").read_text(encoding="utf-8"))

# Dual phone_driving still in legacy path — not "unifié sans doute"
DOWNGRADE = {"F.58", "P.134"}

rows = []
for r in data["rows"]:
    ref = r["ref"]
    if ref in DOWNGRADE:
        verdict = "FAIL"
        note = "phone_driving legacy encore présent (detector.py)"
    elif r["status"] == "done":
        verdict = "PASS"
        note = r.get("evidence", "")[:80]
    else:
        verdict = "FAIL"
        note = f"{r['status']}: {r.get('evidence', '')[:60]}"
    rows.append((ref, r["title"], r["section"], verdict, note))

pass_n = sum(1 for *_, v, _ in rows if v == "PASS")
fail_n = len(rows) - pass_n
out = ROOT / "logs" / "audit-138-pass-fail.tsv"
out.parent.mkdir(exist_ok=True)
lines = [f"# Audit 138 — {data['generated_at']}", f"PASS={pass_n} FAIL={fail_n}", ""]
for ref, title, section, verdict, note in rows:
    lines.append(f"{ref}\t{verdict}\t{title}\t{section}\t{note}")
out.write_text("\n".join(lines), encoding="utf-8")
print(out)
print(f"PASS={pass_n} FAIL={fail_n}")
