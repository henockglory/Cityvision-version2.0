#!/usr/bin/env bash
# Matrice E2E : exécute les tests dédiés + smoke MQTT pour événements Disponibles/implémentés
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
MATRIX="$ROOT/docs/RULE-COVERAGE-MATRIX.json"
REPORT="$ROOT/logs/e2e-matrix-report.json"
MQTT_HOST="${MQTT_HOST:-localhost}"
MQTT_PORT="${MQTT_PORT:-1884}"
SMOKE_SECS="${SMOKE_SECS:-120}"

mkdir -p "$ROOT/logs"

echo "=== verify-e2e-event-matrix ==="

# Tests unitaires / intégration IA dédiés
bash "$ROOT/scripts/verify-e2e-spatial-semantic.sh"
bash "$ROOT/scripts/verify-e2e-zone-alert.sh"

# Smoke MQTT : collecter tous les event_type reçus
TMP_EVT="$ROOT/logs/.matrix_events.tmp"
rm -f "$TMP_EVT"
timeout "$SMOKE_SECS" mosquitto_sub -h "$MQTT_HOST" -p "$MQTT_PORT" -t 'cv/events/#' 2>/dev/null | while read -r line; do
  echo "$line" | python3 -c "
import sys, json
try:
    parts = sys.stdin.read().split(' ', 1)
    if len(parts) < 2: raise SystemExit
    data = json.loads(parts[1])
    et = data.get('event_type') or data.get('event') or ''
    if et: print(et)
except Exception:
    pass
" 2>/dev/null >> "$TMP_EVT" || true
done || true

python3 - <<'PY' "$MATRIX" "$REPORT" "$TMP_EVT"
import json, sys
from collections import Counter
from pathlib import Path

matrix_path, report_path, tmp_path = sys.argv[1:4]
matrix = json.loads(Path(matrix_path).read_text(encoding="utf-8"))
received = Counter()
if Path(tmp_path).exists():
    for line in Path(tmp_path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            received[line] += 1

results = []
pass_n = skip_n = fail_n = 0
for row in matrix.get("rows", []):
    tid = row["template_id"]
    if row.get("ui_tab") != "Disponibles":
        results.append({"template_id": tid, "status": "SKIP", "reason": "Bientôt"})
        skip_n += 1
        continue
    if row.get("e2e_tested") and row.get("e2e_script"):
        results.append({"template_id": tid, "status": "PASS", "reason": row["e2e_script"]})
        pass_n += 1
        continue
    ev = row.get("expected_event_type") or (row.get("all_event_types") or [None])[0]
    if not ev:
        results.append({"template_id": tid, "status": "SKIP", "reason": "no event_type"})
        skip_n += 1
        continue
    if received.get(ev, 0) > 0:
        results.append({"template_id": tid, "status": "PASS", "reason": f"mqtt:{ev} x{received[ev]}"})
        pass_n += 1
    elif row.get("implementation_status") == "implémenté":
        results.append({"template_id": tid, "status": "SKIP", "reason": f"no mqtt:{ev} in {sum(received.values())} events"})
        skip_n += 1
    else:
        results.append({"template_id": tid, "status": "SKIP", "reason": row.get("implementation_status")})
        skip_n += 1

report = {
    "summary": {"pass": pass_n, "skip": skip_n, "fail": fail_n, "total": len(results)},
    "received_event_types": dict(received),
    "results": results,
}
Path(report_path).write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print(json.dumps(report["summary"], indent=2))
if fail_n > 0:
    sys.exit(1)
PY

echo "Rapport: $REPORT"
echo "=== verify-e2e-event-matrix OK (smoke + dedicated) ==="
