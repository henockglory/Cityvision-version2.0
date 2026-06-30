#!/usr/bin/env bash
# Bootstrap demo stack on WSL citevision-v2 (idempotent).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
sed -i 's/\r$//' scripts/*.sh scripts/*.py 2>/dev/null || true

echo "==> Docker infra"
docker compose -f infra/docker-compose.yml --env-file .env up -d 2>/dev/null || true
sleep 3

echo "==> Env + paths"
bash scripts/ensure-rules-sync-env.sh
bash scripts/fix-demo-camera-paths.sh 2>/dev/null || true

echo "==> Secondary models (phone + seatbelt)"
if [[ ! -f /tmp/sbd/yolov8/content/runs/detect/train2/weights/best.pt ]]; then
  git clone --depth 1 --branch Yolov8 https://github.com/HayaAbdullahM/Seat-Belt-Detection.git /tmp/sbd 2>/dev/null || true
fi
if [[ ! -f ai-engine/models/secondary/driver_phone.onnx ]] || [[ ! -f ai-engine/models/secondary/seatbelt.onnx ]]; then
  bash scripts/build-secondary-models.sh 2>&1 | tail -10
fi

echo "==> InsightFace (if needed)"
if ! curl -sf http://127.0.0.1:${AI_ENGINE_PORT:-8001}/health 2>/dev/null | grep -q '"face_loaded":"true"'; then
  bash scripts/fix-insightface.sh || bash scripts/resume-after-ai-gate.sh 2>/dev/null || true
fi

echo "==> Restart ingest"
bash scripts/restart-ai-ingest.sh

echo "==> Rules engine"
bash scripts/_start-rules-engine.sh

echo "==> Seed demo rules"
bash scripts/seed-demo-rules.sh

echo "==> Gates"
curl -sf "http://127.0.0.1:${API_PORT:-8081}/health" && echo " backend OK"
curl -sf "http://127.0.0.1:${AI_ENGINE_PORT:-8001}/health" | python3 -m json.tool
curl -sf "http://127.0.0.1:${RULES_ENGINE_PORT:-8010}/health" && echo
curl -sf "http://127.0.0.1:8025/" >/dev/null && echo "mailhog OK"
curl -sf "http://127.0.0.1:8001/cameras" | python3 -m json.tool | grep camera_id
