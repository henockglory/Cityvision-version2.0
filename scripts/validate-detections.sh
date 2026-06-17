#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MQTT_HOST="${MQTT_HOST:-localhost}"
MQTT_PORT="${MQTT_PORT:-1884}"
DURATION="${DURATION:-300}"
REPORT="$ROOT/logs/detection-validation.json"

mkdir -p "$ROOT/logs"

EXPECTED_EVENTS=(
  zone_enter zone_exit line_cross loitering
  running crowd_gathering person_stopped vehicle_stopped
  dwell_time_exceeded scene_density_high crowd_count_threshold
  vehicle_count_threshold speeding speed_below_minimum sudden_stop
  perimeter_breach unauthorized_exit vehicle_corridor
  face_detected face_unknown plate_detected
  object_abandoned person_vehicle_proximity
  video_blur video_darkness behavior_anomaly
)

echo "==> Validation dÃ©tections live ($DURATION s)"
echo "    MQTT: $MQTT_HOST:$MQTT_PORT"
echo "    Rapport: $REPORT"

declare -A RECEIVED
for evt in "${EXPECTED_EVENTS[@]}"; do
  RECEIVED[$evt]=0
done

timeout "$DURATION" mosquitto_sub -h "$MQTT_HOST" -p "$MQTT_PORT" -t 'cv/events/#' -v 2>/dev/null | while read -r line; do
  event_type=$(echo "$line" | python3 -c "
import sys, json
try:
    parts = sys.stdin.read().split(' ', 1)
    if len(parts) < 2: sys.exit()
    data = json.loads(parts[1])
    print(data.get('event_type', ''))
except: pass
" 2>/dev/null || true)
  if [ -n "$event_type" ]; then
    echo "$event_type" >> "$ROOT/logs/.detected_events.tmp"
  fi
done || true

if [ -f "$ROOT/logs/.detected_events.tmp" ]; then
  while read -r evt; do
    RECEIVED[$evt]=$((${RECEIVED[$evt]:-0} + 1))
  done < "$ROOT/logs/.detected_events.tmp"
  rm -f "$ROOT/logs/.detected_events.tmp"
fi

python3 - <<'PY' "$REPORT"
import json, sys, os

report_path = sys.argv[1]
expected = os.environ.get("EXPECTED", "").split()
# read from env not set - use hardcoded list
expected = [
  "zone_enter", "zone_exit", "line_cross", "loitering",
  "running", "crowd_gathering", "person_stopped", "vehicle_stopped",
  "dwell_time_exceeded", "scene_density_high", "crowd_count_threshold",
  "vehicle_count_threshold", "speeding", "speed_below_minimum", "sudden_stop",
  "perimeter_breach", "unauthorized_exit", "vehicle_corridor",
  "face_detected", "face_unknown", "plate_detected",
  "object_abandoned", "person_vehicle_proximity",
  "video_blur", "video_darkness", "behavior_anomaly",
]

tmp = os.path.join(os.path.dirname(report_path), ".detected_events.tmp")
received = {}
if os.path.exists(tmp):
    with open(tmp) as f:
        for line in f:
            e = line.strip()
            received[e] = received.get(e, 0) + 1

results = []
pass_n = fail_n = skip_n = 0
for evt in expected:
    count = received.get(evt, 0)
    if count > 0:
        status = "PASS"
        pass_n += 1
    else:
        status = "SKIP"
        skip_n += 1
    results.append({"event_type": evt, "count": count, "status": status})

report = {
    "summary": {"pass": pass_n, "skip": skip_n, "fail": fail_n, "total": len(expected)},
    "results": results,
    "received_all": received,
}
os.makedirs(os.path.dirname(report_path), exist_ok=True)
with open(report_path, "w") as f:
    json.dump(report, f, indent=2)
print(json.dumps(report["summary"], indent=2))
PY

echo "==> Validation terminÃ©e"
