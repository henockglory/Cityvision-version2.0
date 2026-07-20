#!/usr/bin/env bash
set -euo pipefail
DIR=/tmp/cv_segments/37c7d7fa-12dc-450c-8c4b-ab63ed43a819
for _ in $(seq 1 20); do
  f=$(ls -t "$DIR"/*.mp4 2>/dev/null | grep -v evidence | head -1 || true)
  if [[ -n "${f:-}" ]]; then
    sz=$(stat -c%s "$f")
    if [[ "$sz" -gt 500000 ]]; then
      cp "$f" /tmp/orig.mp4
      cp "$f" /tmp/evidence.mp4
      cd ~/citevision-v2/ai-engine
      .venv/bin/python3 - <<'PY'
import cv2
from citevision_ai.evidence.service import extract_subclip_mp4, probe_media_duration
cap = cv2.VideoCapture('/tmp/orig.mp4')
dur = probe_media_duration('/tmp/evidence.mp4')
print('dur', dur, 'cap open', cap.isOpened())
clip = extract_subclip_mp4('/tmp/evidence.mp4', dur or 10, 6.0)
print('clip bytes', len(clip) if clip else None)
cap.release()
PY
      exit 0
    fi
  fi
  sleep 1
done
