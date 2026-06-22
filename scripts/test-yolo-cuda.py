#!/usr/bin/env python3
from citevision_ai.detection.yolo_onnx import YoloOnnxDetector

d = YoloOnnxDetector("models/yolov8n.onnx", device="cuda")
d.load()
print("provider:", d.active_provider)
print("cuda:", d.uses_cuda)
print("fps:", round(d.benchmark_fps(20), 1))
