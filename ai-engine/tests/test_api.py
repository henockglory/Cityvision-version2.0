import pytest
from httpx import ASGITransport, AsyncClient

from citevision_ai.main import app


@pytest.mark.asyncio
async def test_health_endpoint():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_health_gpu_reports_real_multi_camera_metrics(monkeypatch):
    """/health/gpu must report the actual multi-camera load (queue depth,
    dropped frames, per-camera latency) — not just a synthetic mono-stream
    benchmark number that hides real GPU contention at scale."""
    from citevision_ai import main as main_module

    class FakeDetector:
        is_loaded = True
        active_provider = "CPUExecutionProvider"
        _microbatch_enabled = True
        _batch_window_sec = 0.012
        _max_batch_size = 16

        @property
        def uses_cuda(self):
            return False

        def benchmark_fps(self, _n):
            return 42.0

    class FakeBudget:
        camera_count = 3

    class FakePipeline:
        detector = FakeDetector()
        budget = FakeBudget()

    class FakeWorkerManager:
        def list_status(self):
            return [
                {"camera_id": "a", "queue_depth": 1, "infer_latency_ms": 50.0, "frames_dropped": 2},
                {"camera_id": "b", "queue_depth": 2, "infer_latency_ms": 30.0, "frames_dropped": 0},
            ]

    monkeypatch.setattr(main_module, "pipeline", FakePipeline())
    monkeypatch.setattr(main_module, "worker_manager", FakeWorkerManager())

    result = main_module.health_gpu()

    assert result["active_cameras"] == 3
    assert result["avg_queue_depth"] == 1.5
    assert result["max_queue_depth"] == 2
    assert result["total_frames_dropped"] == 2
    assert result["avg_infer_latency_ms"] == 40.0
    assert result["max_infer_latency_ms"] == 50.0
    assert result["microbatch_enabled"] is True
    assert result["batch_window_ms"] == 12.0
    assert result["max_batch_size"] == 16


def test_health_gpu_handles_no_cameras_active(monkeypatch):
    from citevision_ai import main as main_module

    class FakeDetector:
        is_loaded = True
        active_provider = "CPUExecutionProvider"
        _microbatch_enabled = True
        _batch_window_sec = 0.012
        _max_batch_size = 16

        @property
        def uses_cuda(self):
            return False

        def benchmark_fps(self, _n):
            return 10.0

    class FakeBudget:
        camera_count = 0

    class FakePipeline:
        detector = FakeDetector()
        budget = FakeBudget()

    class FakeWorkerManager:
        def list_status(self):
            return []

    monkeypatch.setattr(main_module, "pipeline", FakePipeline())
    monkeypatch.setattr(main_module, "worker_manager", FakeWorkerManager())

    result = main_module.health_gpu()
    assert result["avg_queue_depth"] == 0
    assert result["total_frames_dropped"] == 0
