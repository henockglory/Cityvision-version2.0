#!/usr/bin/env bash
curl -sf http://127.0.0.1:8001/cameras/726ff8a1-8442-4bdb-96ad-ec40a2fbb424/spatial | python3 -m json.tool
echo "--- cameras ---"
curl -sf http://127.0.0.1:8001/cameras | python3 -m json.tool | head -40
echo "--- mqtt 45s ---"
cd ~/citevision-v2
python3 scripts/mqtt_monitor_events.py 45 2>&1 | grep -E '726ff8|red_light|traffic_light' || echo "(no feu events in 45s)"
