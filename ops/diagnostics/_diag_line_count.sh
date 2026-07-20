#!/usr/bin/env bash
set -euo pipefail
PSQL=(docker exec citevision-v2-postgres psql -U citevision -d citevision -t -A)

echo "=== Rules (Comptage) ==="
"${PSQL[@]}" -c "SELECT name, is_enabled, definition->'bindings' FROM rules WHERE name ILIKE '%comptage%' ORDER BY updated_at DESC LIMIT 5;"

echo ""
echo "=== Camera for copied rule ==="
"${PSQL[@]}" -c "SELECT id, name, host, port, status, is_active FROM cameras WHERE id = '37c7d7fa-12dc-450c-8c4b-ab63ed43a819';"

CAM_ID="37c7d7fa-12dc-450c-8c4b-ab63ed43a819"

echo ""
echo "=== Full rule definition (copie) ==="
"${PSQL[@]}" -c "SELECT definition FROM rules WHERE name = 'Démo · Comptage véhicules (copie)';" | head -c 2000

if [[ -n "$CAM_ID" ]]; then
  echo ""
  echo "=== Lines on camera ==="
  "${PSQL[@]}" -c "SELECT name, behavior_config, start_point, end_point FROM lines WHERE camera_id = '$CAM_ID';"

  echo ""
  echo "=== line_counters ==="
  "${PSQL[@]}" -c "SELECT line_id, count_total, count_in, count_out, updated_at FROM line_counters WHERE camera_id = '$CAM_ID' ORDER BY updated_at DESC LIMIT 5;"

  echo ""
  echo "=== Recent line_cross events ==="
  "${PSQL[@]}" -c "SELECT event_type, payload->>'line_id' as line_id, payload->>'class_name' as cls, occurred_at FROM events WHERE camera_id = '$CAM_ID' AND event_type = 'line_cross' ORDER BY occurred_at DESC LIMIT 5;"

  echo ""
  echo "=== Event counts (1h) ==="
  "${PSQL[@]}" -c "SELECT event_type, count(*) FROM events WHERE camera_id = '$CAM_ID' AND occurred_at > now() - interval '1 hour' GROUP BY event_type ORDER BY count DESC;"

  echo ""
  echo "=== Alerts for camera (recent) ==="
  "${PSQL[@]}" -c "SELECT a.title, a.status, a.created_at FROM alerts a JOIN events e ON e.id = a.event_id WHERE e.camera_id = '$CAM_ID' ORDER BY a.created_at DESC LIMIT 5;"

  echo ""
  echo "=== Rule id for copie ==="
  RULE_ID=$("${PSQL[@]}" -c "SELECT id FROM rules WHERE name = 'Démo · Comptage véhicules (copie)';")
  echo "RULE_ID=$RULE_ID"
  "${PSQL[@]}" -c "SELECT count(*) FROM alerts WHERE rule_id = '$RULE_ID';"
fi

echo ""
echo "=== AI ingest log tail ==="
tail -5 ~/citevision-v2/logs/ai-engine.log 2>/dev/null || true
