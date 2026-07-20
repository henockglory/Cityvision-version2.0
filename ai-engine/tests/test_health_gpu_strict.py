"""Sprint 3 — /health fails loud when CUDA required but inactive."""
from __future__ import annotations

from fastapi.testclient import TestClient


def test_health_gpu_required_inactive_returns_503(monkeypatch):
    import citevision_ai.main as main

    class _Det:
        is_loaded = True
        active_provider = "CPUExecutionProvider"
        uses_cuda = False

    class _Eng:
        is_loaded = True

    class _Pipe:
        detector = _Det()
        face_engine = _Eng()
        plate_engine = _Eng()

        class secondary:
            @staticmethod
            def health():
                return {}

    monkeypatch.setattr(main, "pipeline", _Pipe())
    monkeypatch.setattr(main.settings, "yolo_device", "cuda")
    monkeypatch.delenv("ALLOW_CPU_HEALTH", raising=False)

    client = TestClient(main.app)
    r = client.get("/health")
    assert r.status_code == 503
    body = r.json()
    assert body["gpu_active"] == "false"
    assert body["gpu_required"] == "true"
    assert body["status"] == "gpu_required_inactive"


def test_health_allow_cpu_bypass(monkeypatch):
    import citevision_ai.main as main

    class _Det:
        is_loaded = True
        active_provider = "CPUExecutionProvider"
        uses_cuda = False

    class _Eng:
        is_loaded = True

    class _Pipe:
        detector = _Det()
        face_engine = _Eng()
        plate_engine = _Eng()

        class secondary:
            @staticmethod
            def health():
                return {}

    monkeypatch.setattr(main, "pipeline", _Pipe())
    monkeypatch.setattr(main.settings, "yolo_device", "cuda")
    monkeypatch.setenv("ALLOW_CPU_HEALTH", "1")

    client = TestClient(main.app)
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["gpu_required"] == "false"
