#!/usr/bin/env bash
for i in $(seq 1 40); do
  code=$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8001/health 2>/dev/null)
  if [ "$code" = "200" ]; then
    echo "AI_HEALTHY after ${i}x3s"
    curl -s http://127.0.0.1:8001/health | python3 -c "
import sys, json
d = json.load(sys.stdin)
print('evidence_backend:', d.get('evidence_backend','?'))
print('cameras_running:', d.get('cameras_running',[]))
"
    exit 0
  fi
  echo "  attempt $i: HTTP $code — waiting..."
  sleep 3
done
echo "AI_HEALTH_TIMEOUT"
exit 1
