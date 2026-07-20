#!/usr/bin/env bash
set -euo pipefail
DIR=/tmp/cv_segments/37c7d7fa-12dc-450c-8c4b-ab63ed43a819
for _ in $(seq 1 30); do
  f=$(ls -t "$DIR"/*.mp4 2>/dev/null | head -1 || true)
  if [[ -n "${f:-}" ]]; then
    sz=$(stat -c%s "$f" 2>/dev/null || echo 0)
    if [[ "$sz" -gt 500000 ]]; then
      cp "$f" /tmp/seg_hold.mp4
      echo "copied $f size=$sz"
      ffprobe -v error -show_entries format=duration -of default=nw=1 /tmp/seg_hold.mp4
      cd ~/citevision-v2/ai-engine
      .venv/bin/python3 - <<'PY'
from citevision_ai.evidence.service import extract_subclip_mp4
for pts in (5.0, 9.0, 10.0):
    data = extract_subclip_mp4("/tmp/seg_hold.mp4", pts, 6.0)
    print("pts", pts, "bytes", len(data) if data else None)
PY
      exit 0
    fi
  fi
  sleep 1
done
echo "no complete segment found"
