#!/usr/bin/env bash
set -euo pipefail
CAM=37c7d7fa-12dc-450c-8c4b-ab63ed43a819
curl -s -X POST "http://127.0.0.1:8001/cameras/${CAM}/stop"
sleep 2
curl -s -X POST "http://127.0.0.1:8001/cameras/${CAM}/start" \
  -H "Content-Type: application/json" \
  -d "{\"rtsp_url\":\"rtsp://admin:hids+1234@192.168.1.108:554/live\",\"ai_fps\":8}"
echo
curl -s "http://127.0.0.1:8001/cameras" | python3 -m json.tool
