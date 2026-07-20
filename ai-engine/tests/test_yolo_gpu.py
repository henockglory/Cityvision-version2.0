from citevision_ai.detection.yolo_onnx import resolve_onnx_providers, YoloOnnxDetector


def test_resolve_onnx_providers_cpu_fallback():
    providers, label = resolve_onnx_providers("cpu")
    assert providers == ["CPUExecutionProvider"]
    assert label == "cpu"


def test_yolo_missing_model_not_loaded(tmp_path):
    detector = YoloOnnxDetector(tmp_path / "missing.onnx", device="cpu")
    detector.load()
    assert not detector.is_loaded
    assert detector.benchmark_fps() == 0.0
