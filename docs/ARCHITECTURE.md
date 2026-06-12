# Architecture

## Overview

Citévision 2.0 is an edge-first video analytics platform composed of three runtime services and shared infrastructure.

```
┌─────────────────┐     RTSP      ┌──────────────────┐
│  IP Cameras     │──────────────▶│  Video Engine    │
└─────────────────┘               │  (C++ / FFmpeg)  │
                                  └────────┬─────────┘
                                           │ frames (shared mem / socket)
                                           ▼
                                  ┌──────────────────┐
                                  │   AI Engine      │
                                  │ (Python/FastAPI) │
                                  │  YOLO + ByteTrack│
                                  └────────┬─────────┘
                                           │ MQTT
                                           ▼
┌──────────────┐  ┌──────────────┐  ┌──────────────────┐
│  PostgreSQL  │  │    Redis     │  │    Mosquitto     │
│  rules/events│  │  state cache │  │  cv/detections/* │
└──────────────┘  └──────────────┘  └──────────────────┘
                                           │
                                           ▼
                                  ┌──────────────────┐
                                  │  MinIO           │
                                  │  recordings      │
                                  └──────────────────┘
```

## AI Engine

- **Detection:** YOLOv8n ONNX via onnxruntime
- **Tracking:** ByteTrack
- **Events:** Zone enter/exit, line cross, loitering
- **Analytics:** Behavior heuristics, state engine, cross-camera correlation
- **Stubs:** InsightFace (face), PaddleOCR (ANPR)

## Video Engine

- RTSP ingest with reconnect
- Dual pipeline: analysis (adaptive low-res) + record (720p H.264)
- Adaptive frame sampling based on motion/scene complexity
- Health HTTP endpoint on port 9000

## Data Flow

1. Video engine ingests RTSP, samples frames for analysis
2. AI engine receives frames, runs detection + tracking
3. Detections published to MQTT topic `cv/detections/{camera_id}`
4. Event generator evaluates rules, emits events to `cv/events/{camera_id}`
5. Recording pipeline writes segments to MinIO

## Shared Schemas

JSON Schema definitions in `shared/schemas/` define the contract between components.
