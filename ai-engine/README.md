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

| Tier | GPU | Modèle YOLO | Caméras max | Batch max | FPS cible |
|------|-----|-------------|-------------|-----------|-----------|
| CPU-only | Aucun | yolov8n.onnx | 2 | 1 | 3 |
| Standard | GTX 1060–2080 | yolov8n.onnx | 8 | 4 | 10 |
| High | RTX 3060–4060 | yolov8s.onnx | 16 | 8 | 15 |
| Ultra | RTX 4070–5060 | yolov8m.onnx | 24 | 16 | 25 |
| Max | RTX 4090/5090 | yolov8l.onnx | 48 | 32 | 30 |

- **Caméras max** = plafond dur (`ResourceBudgetManager.max_cameras`) ; au-delà, `POST /cameras/{id}/start` refuse la caméra (`ValueError`). La résolution d'ingestion (1080p → 640p → 320p) décroît aussi avec le nombre de caméras actives, indépendamment du tier (`budget/resource_budget.py`).
- **Batch max** = plafond réel du micro-batching GPU (`YoloOnnxDetector._max_batch_size`, câblé depuis `settings.batch_size` à la construction du détecteur dans `main.py`). Les appels `detect()` concurrents de plusieurs caméras arrivant dans une fenêtre de `YOLO_BATCH_WINDOW_MS` (défaut 12 ms) sont coalescés en un seul `session.run()`, jusqu'à ce plafond — pas au-delà, même avec plus de caméras actives.
- **FPS cible** = débit indicatif du tier (`target_fps`), utilisé par `ResourceBudgetManager` pour calculer le frame-skip standard. Les zones prioritaires (vitesse, feux) ne suivent **pas** cette valeur : elles sont plafonnées séparément à `PRIORITY_ZONE_TARGET_HZ` (8 Hz par défaut, env var du même nom) — fixe, indépendant du nombre de caméras actives — pour éviter qu'elles ne saturent le GPU partagé quand leur nombre augmente (`pipeline.priority_zone_skip`).

Forcer un tier : `CITEVISION_GPU_TIER=high` (env var)

Overrides indépendants du tier (utiles en test de charge) : `YOLO_MICROBATCH=0` désactive le micro-batching, `YOLO_BATCH_WINDOW_MS` / `YOLO_MAX_BATCH_SIZE` ajustent la fenêtre et le plafond de batch sans changer de tier.

### Architecture d'ingestion multi-caméra

Chaque caméra RTSP a son propre thread de lecture réseau, découplé de l'inférence par une file bornée (`queue.Queue(maxsize=2)`, politique drop-oldest) et un thread d'inférence dédié (`ingest/rtsp_worker.py`) — un flux lent ou une inférence momentanément saturée ne bloque jamais la lecture réseau des autres caméras. La session ONNX GPU reste unique et partagée entre toutes les caméras ; l'accès à `session.run()` est sérialisé par un verrou (`YoloOnnxDetector._run_lock`), et le micro-batching ci-dessus amortit le coût de lancement GPU sur plusieurs caméras à la fois.

`GET /cameras` et `GET /health/gpu` exposent les métriques réelles par caméra (frames lus/traités/perdus, profondeur de file, latence d'inférence) — pas seulement un benchmark synthétique mono-flux. Voir `scripts/load_test_multicamera.py` pour valider empiriquement la capacité 1→16 caméras sur le matériel courant avant de brancher des caméras réelles.

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
| GET | `/health/gpu` | Benchmark FPS mono-flux + charge GPU réelle multi-caméra (queue, latence, drops, batching) |
| GET | `/cameras` | Caméras actives + métriques par caméra (frames lus/traités/perdus, queue, latence) |
| POST | `/cameras/{id}/start` | Démarrer une caméra (RTSP ou `video_file` pour simulation) |
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

## Test de charge multi-caméra

```bash
# Depuis la racine du repo, AI engine démarré sur :8001
python scripts/load_test_multicamera.py --steps 1,2,4,8,12,16 --duration 20 --ai-fps 8
```

Démarre N caméras simulées (même vidéo démo dupliquée, `video_file=`) à chaque palier, mesure le FPS effectif/latence/pertes par caméra via `/cameras` et `/health/gpu`, puis affiche la capacité stable estimée pour le GPU courant — à faire tourner avant tout branchement de caméras réelles supplémentaires. Rapport détaillé en JSON (`scripts/_load_test_report.json`).
