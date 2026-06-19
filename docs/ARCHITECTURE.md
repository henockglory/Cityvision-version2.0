# Architecture — Citévision v2

## Overview

```
┌─────────────┐     RTSP      ┌────────────────┐
│   Cameras   │──────────────▶│  Video Engine  │
└─────────────┘               │  (C++/FFmpeg)  │
                              └───────┬────────┘
                                      │ frames
                                      ▼
                              ┌────────────────┐
                              │   AI Engine    │
                              │ FastAPI + YOLO │
                              │   ByteTrack    │
                              └───────┬────────┘
                                      │ MQTT
                    cv/detections/*   │   cv/events/*
                                      ▼
                              ┌────────────────┐
                              │ Rules Engine   │
                              │  ET/OU/NON     │
                              │  dedup/window  │
                              └───────┬────────┘
                                      │ alerts
                                      ▼
                              ┌────────────────┐
                              │ Postgres/Redis │
                              │     MinIO      │
                              └────────────────┘
```

## AI Engine

- **YOLO ONNX**: Real inference via ONNX Runtime; empty list when model absent.
- **ByteTrack**: IoU-based multi-object tracking per camera.
- **ResourceBudgetManager**: Adaptive resolution/FPS by camera count.
- **EventGenerator**: Zone enter/exit, line cross, loitering.
- **Optional**: InsightFace, PaddleOCR — return `[]` when disabled.

## Rules Engine

- Subscribes to `cv/events/#` and `cv/detections/#`.
- Evaluates declarative rules with **ET** (AND), **OU** (OR), **NON** (NOT).
- Temporal windows (hour/day) and anti-dedup cache.

## Video Engine

Dual pipeline:
1. **Analysis path** — downsampled frames at target FPS for AI.
2. **Recording path** — full-rate 720p H.264 encode (stub counters in Phase 1).

Health HTTP server on port **9011**.

## Shared Contracts

JSON schemas in `shared/schemas/` define MQTT payloads and rule definitions.
Rule catalog in `shared/rule-catalog/` provides templates only (not DB seeds).
