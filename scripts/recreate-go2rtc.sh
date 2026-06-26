#!/usr/bin/env bash
set -euo pipefail
cd /mnt/c/Citevision
docker compose -f infra/docker-compose.yml up -d go2rtc --force-recreate
sleep 4
curl -s -X PUT 'http://localhost:1984/api/streams?dst=cam-3f36b8bb-efaf-4bbe-afba-5ea94ed6556b&src=ffmpeg:rtsp://admin:hids%2B1234@192.168.1.108:554/live%23video=h264'
echo
curl -s http://localhost:1984/api/streams
