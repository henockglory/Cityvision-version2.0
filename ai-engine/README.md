# AI Engine — CitéVision v2

Service Python FastAPI d'analyse vidéo : détection d'objets (YOLO ONNX), suivi multi-objet (ByteTrack), génération d'événements, analyse comportementale, ANPR et reconnaissance faciale.

## Stack

| Composant | Version |
|-----------|---------|
| Python | 3.12 |
| FastAPI | 0.115 |
| ONNX Runtime | 1.19 (CPU + GPU) |
| OpenCV | 4.x |
| paho-mqtt | 2.x |

## Structure

```
ai-engine/src/citevision_ai/
├── config.py              ← Settings (pydantic-settings)
├── hardware_profile.py    ← Détection GPU + élasticité par tier ★
├── main.py                ← FastAPI app, lifespan, endpoints
├── pipeline.py            ← Orchestration détection → tracking → événements
├── detection/             ← YOLO ONNX wrapper
├── tracking/              ← ByteTrack multi-objet
├── events/                ← Générateur d'événements (ligne, zone, loitering)
├── behavior/              ← Analyse comportementale (foule, démarche)
├── analytics/             ← Corrélation, état scène, comportements
├── correlation/           ← Corrélation spatiale et temporelle
├── state/                 ← État scène Redis
├── anpr/                  ← Reconnaissance plaques (PaddleOCR stub)
├── face/                  ← Reconnaissance faciale (InsightFace stub)
├── mqtt/                  ← Publisher MQTT
├── budget/                ← Gestion ressources (caméras, FPS)
└── models/                ← Schémas Pydantic
```

## Élasticité GPU (hardware_profile.py)

Au démarrage, le profil GPU est automatiquement détecté et configure les paramètres optimaux :

| Tier | GPU | Modèle YOLO | Caméras | Batch | FPS |
|------|-----|-------------|---------|-------|-----|
| CPU-only | Aucun | yolov8n.onnx | 2 | 1 | 3 |
| Standard | GTX 1060–2080 | yolov8n.onnx | 8 | 4 | 10 |
| High | RTX 3060–4060 | yolov8s.onnx | 16 | 8 | 15 |
| Ultra | RTX 4070–5060 | yolov8m.onnx | 24 | 16 | 25 |
| Max | RTX 4090/5090 | yolov8l.onnx | 48 | 32 | 30 |

Forcer un tier : `CITEVISION_GPU_TIER=high` (env var)

## Démarrage

```bash
cd ai-engine
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Télécharger le modèle YOLO
bash ../scripts/download-yolo-model.sh

uvicorn citevision_ai.main:app --host 0.0.0.0 --port 8001
```

API disponible sur `http://localhost:8001`

## Endpoints principaux

| Méthode | Endpoint | Description |
|---------|----------|-------------|
| GET | `/health` | État du service |
| GET | `/hardware/profile` | Profil GPU détecté |
| GET | `/health/gpu` | Benchmark FPS GPU |
| GET | `/cameras` | Caméras actives |
| POST | `/cameras/{id}/start` | Démarrer une caméra |
| POST | `/cameras/{id}/stop` | Arrêter une caméra |
| GET | `/budget` | Budget ressources |

## Tests

```bash
cd ai-engine
source .venv/bin/activate
pytest tests/ -v
```

## Modèles YOLO

Placer les modèles dans `ai-engine/models/` :
- `yolov8n.onnx` (6 Mo — mode CPU / Tier Standard)
- `yolov8s.onnx` (22 Mo — Tier High)
- `yolov8m.onnx` (52 Mo — Tier Ultra)
- `yolov8l.onnx` (87 Mo — Tier Max)
