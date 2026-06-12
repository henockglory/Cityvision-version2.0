# Architecture Decisions

## ADR-001: Dual Pipeline Video Processing

**Decision:** Separate analysis (low-res, adaptive sampling) and recording (720p) pipelines in the video engine.

**Rationale:** Analysis does not need full resolution; recording must remain usable for forensic review. Splitting pipelines avoids contention and allows independent scaling.

## ADR-002: MQTT for Detection Transport

**Decision:** Publish detections to `cv/detections/{camera_id}` via Eclipse Mosquitto.

**Rationale:** Lightweight pub/sub fits edge deployments; decouples video engine from AI engine; supports multiple subscribers (dashboard, recorder, correlator).

## ADR-003: Resource Budget Manager

**Decision:** Adaptive resolution based on active camera count:

| Cameras | Resolution | Target FPS |
|---------|------------|------------|
| 1       | 1080p      | 5          |
| 2–4     | 640p       | 5          |
| 5–12    | 320p       | 5          |

**Rationale:** Fixed budget per edge node; prevents GPU/CPU saturation on multi-camera sites.

## ADR-004: ONNX Runtime for Inference

**Decision:** YOLOv8n exported to ONNX, executed via onnxruntime (CPU/GPU EP).

**Rationale:** Portable across x86 and ARM; no PyTorch runtime dependency in production.

## ADR-005: ByteTrack for Multi-Object Tracking

**Decision:** ByteTrack associating detections frame-to-frame.

**Rationale:** Strong baseline tracker without re-ID embeddings; sufficient for zone/line/loitering events.

## ADR-006: Stub Modules for Face and ANPR

**Decision:** Define InsightFace and PaddleOCR interfaces; implement stubs returning empty results.

**Rationale:** Allows pipeline integration and schema validation before GPU-heavy dependencies are added.
