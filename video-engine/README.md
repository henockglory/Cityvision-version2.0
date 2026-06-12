# Citévision Video Engine

C++17 RTSP ingest service with dual pipeline processing and HTTP health endpoint.

## Features

- **RTSP ingest** — TCP transport with automatic reconnect
- **Dual pipeline**
  - Analysis: adaptive low-res sampling (default 640×480 @ 5 fps)
  - Recording: 720p H.264 path (1280×720)
- **Adaptive frame sampling** — `FrameSampler` adjusts analysis rate from source FPS
- **Health HTTP** — JSON status on port 9000 (override via `VIDEO_ENGINE_HEALTH_PORT`)

## Prerequisites

```bash
# Debian/Ubuntu
sudo apt install build-essential cmake pkg-config \
  libavformat-dev libavcodec-dev libavutil-dev libswscale-dev
```

## Build

```bash
mkdir build && cd build
cmake ..
cmake --build .
```

## Run

```bash
./citevision-video-engine rtsp://user:pass@camera.local/stream
```

Health check:

```bash
curl http://localhost:9000/health
```

## Architecture

```
RTSP ──▶ RtspIngest ──▶ DualPipeline ──┬──▶ Analysis (low-res, sampled)
                                         └──▶ Record (720p)
HealthServer :9000 ◀── HealthStatus
```

See [docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md) for system-wide design.
