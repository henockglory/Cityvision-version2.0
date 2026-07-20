#!/usr/bin/env bash
set -euo pipefail
ENV=/home/gheno/citevision-v2/.env
touch "$ENV"
patch() {
  local k="$1" v="$2"
  if grep -q "^${k}=" "$ENV"; then
    sed -i "s|^${k}=.*|${k}=${v}|" "$ENV"
  else
    echo "${k}=${v}" >> "$ENV"
  fi
}
patch FRIGATE_ENABLED true
patch FRIGATE_LIVE true
patch FRIGATE_EVIDENCE true
patch FRIGATE_EVENTS false
patch FRIGATE_URL http://127.0.0.1:5000
patch EVIDENCE_BACKEND frigate
patch OCR_URL http://127.0.0.1:8181/ocr
patch OCR_TIMEOUT 8
patch PLATE_MAX_FRAMES 6
patch PLATE_STOP_CONF 0.88
echo OK
