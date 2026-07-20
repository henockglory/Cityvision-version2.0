# Clarifications — 40 Questions with Defaults

Defaults apply until explicitly overridden in `.env` or architecture decisions.

| # | Question | Default |
|---|----------|---------|
| 1 | v1/v2 coexistence on same host? | Yes — v2 uses offset ports (5433, 6380, 1884, 9003, 8001, 9011) |
| 2 | Primary detection model? | YOLOv8n ONNX via ONNX Runtime CPU |
| 3 | Behavior when YOLO model missing? | Return empty detections; log warning; never fake data |
| 4 | Tracker implementation? | In-process ByteTrack-inspired IoU tracker |
| 5 | Upstream ByteTrack repo usage? | Reference only in `vendor/`; not runtime dependency |
| 6 | Max cameras per AI engine instance? | 12 |
| 7 | Adaptive resolution tiers? | 1 cam→1080p, 2–4→640p, 5–12→320p @ 5 FPS |
| 8 | MQTT broker? | Mosquitto in Docker, port 1884 |
| 9 | MQTT auth in dev? | Anonymous allowed |
| 10 | Detection topic pattern? | `cv/detections/{camera_id}` |
| 11 | Event topic pattern? | `cv/events/{camera_id}` |
| 12 | Rules logical operators? | ET (AND), OU (OR), NON (NOT) |
| 13 | Rules engine language? | Go 1.22 |
| 14 | Rule dedup TTL? | 60 seconds |
| 15 | Rule catalog vs DB? | Catalog JSON templates; instances in PostgreSQL |
| 16 | Temporal windows? | Hour range + optional day list on rule |
| 17 | PostgreSQL version? | 17 |
| 18 | Redis version? | 7 |
| 19 | Object storage? | MinIO S3-compatible |
| 20 | MinIO bucket name? | `citevision-recordings` |
| 21 | InsightFace required? | No — optional; empty results when disabled |
| 22 | PaddleOCR required? | No — optional; empty results when disabled |
| 23 | Video engine language? | C++17 + FFmpeg |
| 24 | Video health port? | 9011 |
| 25 | RTSP transport? | TCP |
| 26 | Dual pipeline meaning? | Separate analysis sampling vs recording counters |
| 27 | AI engine HTTP port? | 8001 |
| 28 | Rules engine HTTP port? | 8010 |
| 29 | Python version? | 3.12+ |
| 30 | CI matrix? | Ubuntu; go test + pytest + npm build |
| 31 | E2E framework? | Playwright in `tests/e2e/` |
| 32 | Dev on Windows without WSL? | Yes — Docker Desktop + `start-windows.ps1` |
| 33 | go2rtc port? | 1984 |
| 34 | Secrets in repo? | Never — `.env` gitignored; `.env.example` placeholders only |
| 35 | Camera probe multi-vendor? | Hikvision, Dahua, generic paths auto-tested |
| 36 | WebSocket alerts? | `/api/v1/ws/alerts` with JWT query param |
| 37 | Alert pipeline? | rules-engine MQTT `cv/alerts/{org_id}` → backend → WS |
| 38 | First boot data? | Empty DB; wizard creates org + super-admin only |
| 39 | Hologram UI background? | Canvas léger, non bloquant |
| 40 | Git remote canonical? | `henockglory/Cityvision-v2` tag `v2.0.1-validated` |

## Notes

- **Q3** is non-negotiable for production trust: stub modules must not synthesize detections.
- **Q12** French operator names align with operator UI locale; English aliases AND/OR/NOT accepted in evaluator.
- **Q15** distinguishes catalog templates from runtime rule instances stored in PostgreSQL.
- **Q32** WSL optional on Windows when Docker Desktop runs native containers.