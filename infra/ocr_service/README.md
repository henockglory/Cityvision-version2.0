# CitéVision OCR service

Tiny HTTP service that exposes Fast-ALPR (YOLO license plate detector + ONNX OCR)
behind a FastAPI endpoint. CPU-only, no external API key required.

## Endpoints

- `GET /healthz` — readiness check; returns `{ok, detector, ocr}` once models are loaded
- `POST /ocr` — multipart form, field `file` (any common image format).
  Returns `{plate, plate_raw, confidence, bbox, candidates, latency_ms}`.
  `plate` is the best ASCII-normalised candidate (uppercase, alphanumeric only)
  whose confidence is above `OCR_MIN_CONFIDENCE` (default `0.30`).

## Configuration (env)

| Variable | Default | Effect |
|----------|---------|--------|
| `OCR_DETECTOR_MODEL` | `yolo-v9-t-384-license-plate-end2end` | Plate detector model id |
| `OCR_OCR_MODEL` | `global-plates-mobile-vit-v2-model` | OCR model id |
| `OCR_MIN_CONFIDENCE` | `0.30` | Threshold below which `plate` is empty |
| `OCR_NORMALIZE_REGEX` | `[^A-Z0-9]` | Characters stripped from `plate_norm` |
| `OCR_PORT` | `8181` | HTTP port |

Models are downloaded on first start to `/models/hf` (HuggingFace cache).

## Run locally

```bash
docker build -t citevision-ocr ./ocr_service
docker run --rm -p 8181:8181 citevision-ocr
curl -F "file=@some_plate.jpg" http://127.0.0.1:8181/ocr
```
