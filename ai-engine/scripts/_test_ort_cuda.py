"""Quick ONNX CUDA session smoke test (run from ai-engine/ cwd)."""
import os
import sys

import onnxruntime as ort

print("LD (trunc):", (os.environ.get("LD_LIBRARY_PATH") or "")[:240])
print("ORT:", ort.__version__, ort.get_available_providers())
model = "models/yolov8n.onnx"
if not os.path.isfile(model):
    model = "models/yolov8s.onnx"
try:
    sess = ort.InferenceSession(
        model,
        providers=["CUDAExecutionProvider", "CPUExecutionProvider"],
    )
    print("SESSION OK:", sess.get_providers())
except Exception as exc:
    print("SESSION FAIL:", exc, file=sys.stderr)
    sys.exit(1)
