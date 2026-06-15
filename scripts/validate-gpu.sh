#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
AI_URL="${AI_URL:-http://localhost:8001}"
MIN_FPS="${YOLO_MIN_FPS:-10}"
MIN_FPS_CPU="${YOLO_MIN_FPS_CPU:-5}"
ALLOW_CPU="${COMMERCIAL_ALLOW_CPU:-0}"

echo "==> GPU validation (CitéVision AI Engine)"

if command -v nvidia-smi >/dev/null 2>&1; then
  echo "[OK] nvidia-smi:"
  nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv,noheader || true
else
  echo "[WARN] nvidia-smi not found — CUDA gate may fail (see docs/GPU-WSL2.md)"
fi

HEALTH=$(curl -sf "$AI_URL/health" 2>/dev/null || echo '{}')
echo "$HEALTH" | python3 -m json.tool 2>/dev/null || echo "$HEALTH"

LOADED=$(echo "$HEALTH" | python3 -c "import sys,json; print(json.load(sys.stdin).get('yolo_loaded','false'))" 2>/dev/null || echo "false")
if [[ "$LOADED" != "true" ]]; then
  echo "[FAIL] yolo_loaded is not true — run export-yolo-onnx.sh and restart ai-engine"
  exit 1
fi

GPU=$(curl -sf "$AI_URL/health/gpu" 2>/dev/null || echo '{}')
echo "$GPU" | python3 -m json.tool 2>/dev/null || echo "$GPU"

python3 - <<PY
import json, os, sys
gpu = json.loads('''$GPU''')
loaded = "$LOADED"
provider = gpu.get("provider", "unknown")
fps = float(gpu.get("benchmark_fps", 0))
min_fps = float(os.environ.get("YOLO_MIN_FPS", "$MIN_FPS"))
min_fps_cpu = float(os.environ.get("YOLO_MIN_FPS_CPU", "$MIN_FPS_CPU"))
allow_cpu = os.environ.get("COMMERCIAL_ALLOW_CPU", "$ALLOW_CPU") == "1"
cuda_raw = gpu.get("cuda", False)
cuda = cuda_raw is True or cuda_raw == 1 or str(cuda_raw).lower() in ("true", "1", "1.0")
if loaded != "true":
    sys.exit(1)
if cuda and fps < min_fps:
    print(f"[FAIL] CUDA benchmark {fps:.1f} fps < {min_fps} fps minimum")
    sys.exit(1)
if cuda:
    print(f"[OK] CUDA inference {fps:.1f} fps (provider={provider})")
    print("[OK] GPU validation passed")
    sys.exit(0)
if allow_cpu and fps >= min_fps_cpu:
    print(f"[WARN] CPU fallback {fps:.1f} fps (provider={provider}) — CUDA libs incomplete, demo OK")
    print("[OK] GPU validation passed (CPU fallback)")
    sys.exit(0)
print(f"[WARN] Running on CPU ({provider}) {fps:.1f} fps")
print("[FAIL] Commercial gate requires CUDA or COMMERCIAL_ALLOW_CPU=1 with fps >= min")
sys.exit(1)
PY
