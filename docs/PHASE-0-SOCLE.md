# Phase 0 — Validation socle local

Généré le 2026-06-16. Environnement WSL : `~/citevision-v2` (ext4, **828 Go libres**).

## Infrastructure Docker

| Service | Port | Statut |
|---------|------|--------|
| PostgreSQL 17 | 5433 | Up (healthy) |
| Redis 7 | 6380 | Up (healthy) |
| Mosquitto | 1884 | Up (healthy) |
| MinIO | 9003 / 9004 | Up (healthy) |
| go2rtc | 1984 / 8554 | Up (healthy) |

## Services applicatifs

| Service | Port | Health |
|---------|------|--------|
| Backend Go | 8081 | OK |
| AI engine | 8001 | OK — YOLO CUDA, ffmpeg |
| Rules-engine | 8010 | OK — 1 règle active |
| Frontend Vite | 5174 | HTTP 200 |

## Modèles et GPU

| Élément | Statut |
|---------|--------|
| `ai-engine/models/yolov8n.onnx` | Présent |
| `nvidia-smi` | RTX 4050 Laptop GPU |
| `validate-gpu.sh` | **PASS** — 10.4 FPS (seuil 10) |
| `verify-e2e-zone-alert.sh` | **PASS** — zone_presence, preuves H.264, playback |

## Dépendances optionnelles identité / ANPR

| Paquet | Statut | Commande |
|--------|--------|----------|
| `insightface` | Extra `pip install -e ai-engine/.[identity]` | requis pour visages |
| `paddleocr` | Extra `pip install -e ai-engine/.[anpr]` | requis pour plaques |

```bash
source ai-engine/.venv/bin/activate
pip install -e 'ai-engine/.[identity,anpr,dev]'
```

## Matrice de couverture

```bash
make coverage-matrix
```

Voir [`PLAN-REMAINING.md`](./PLAN-REMAINING.md) et [`RULE-COVERAGE-MATRIX.md`](./RULE-COVERAGE-MATRIX.md).
