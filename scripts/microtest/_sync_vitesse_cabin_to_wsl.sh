#!/usr/bin/env bash
# Sync vitesse/cabine sprint files from Windows citevision → WSL citevision-v2
set -euo pipefail
SRC="/mnt/c/Users/gheno/citevision"
DEST="${HOME}/citevision-v2"
rsync -a --no-group --no-owner \
  "${SRC}/backend/internal/frigate/compiler.go" \
  "${SRC}/backend/internal/frigate/compiler_test.go" \
  "${DEST}/backend/internal/frigate/"
rsync -a --no-group --no-owner \
  "${SRC}/ai-engine/src/citevision_ai/frigate_bridge/bridge.py" \
  "${DEST}/ai-engine/src/citevision_ai/frigate_bridge/"
rsync -a --no-group --no-owner \
  "${SRC}/ai-engine/src/citevision_ai/evidence/frigate_track_evidence.py" \
  "${DEST}/ai-engine/src/citevision_ai/evidence/"
rsync -a --no-group --no-owner \
  "${SRC}/ai-engine/src/citevision_ai/vlm/queue.py" \
  "${SRC}/ai-engine/src/citevision_ai/vlm/gemini_client.py" \
  "${DEST}/ai-engine/src/citevision_ai/vlm/"
rsync -a --no-group --no-owner \
  "${SRC}/ai-engine/src/citevision_ai/pipeline.py" \
  "${DEST}/ai-engine/src/citevision_ai/pipeline.py"
rsync -a --no-group --no-owner \
  "${SRC}/scripts/microtest/_export_1hit_vitesse_gallery.py" \
  "${SRC}/scripts/microtest/_run_1hit_vitesse_isolated.sh" \
  "${SRC}/scripts/microtest/_export_1hit_cabin_gallery.py" \
  "${SRC}/scripts/microtest/_run_1hit_cabin_isolated.sh" \
  "${DEST}/scripts/microtest/"
chmod +x \
  "${DEST}/scripts/microtest/_run_1hit_vitesse_isolated.sh" \
  "${DEST}/scripts/microtest/_run_1hit_cabin_isolated.sh"
sed -i 's/\r$//' \
  "${DEST}/scripts/microtest/_run_1hit_vitesse_isolated.sh" \
  "${DEST}/scripts/microtest/_run_1hit_cabin_isolated.sh"
# Doc honesty
if [[ -f "${SRC}/docs/FRIGATE-SYNC-HONESTY.md" ]]; then
  rsync -a --no-group --no-owner \
    "${SRC}/docs/FRIGATE-SYNC-HONESTY.md" \
    "${DEST}/docs/FRIGATE-SYNC-HONESTY.md" || true
fi
echo "SYNC_OK"
ls -la "${DEST}/scripts/microtest/_run_1hit_vitesse_isolated.sh" \
  "${DEST}/scripts/microtest/_export_1hit_cabin_gallery.py" \
  "${DEST}/ai-engine/src/citevision_ai/vlm/queue.py"
