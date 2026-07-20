import os
import sys

sys.path.insert(0, "ai-engine/src")
from citevision_ai.detection.yolo_onnx import YoloOnnxDetector

d = YoloOnnxDetector(device=os.environ.get("YOLO_DEVICE", "cuda"))
d.load()
print("active_provider:", d.active_provider)
print("uses_cuda:", d.uses_cuda)
