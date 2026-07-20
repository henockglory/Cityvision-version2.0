# CitéVision v2

**Plateforme d'analyse vidéo intelligente** — Détection d'objets temps-réel, tracking multi-objet, règles métier configurables, gestion multi-sites et multi-organisations.

[![Go](https://img.shields.io/badge/Backend-Go%201.22-00ADD8?logo=go)](backend/)
[![Python](https://img.shields.io/badge/AI%20Engine-Python%203.12-3776AB?logo=python)](ai-engine/)
[![React](https://img.shields.io/badge/Frontend-React%2018-61DAFB?logo=react)](frontend/)
[![Docker](https://img.shields.io/badge/Infrastructure-Docker%20Compose-2496ED?logo=docker)](docker-compose.yml)

## Installation rapide

### Windows (recommandé)

Double-cliquez `setup.bat` à la racine du projet.  
L'assistant d'installation s'ouvre dans le navigateur et guide tout le processus.

### Linux / macOS

```bash
chmod +x setup.sh && ./setup.sh
```

### Installation manuelle (WSL / Linux)

```bash
# 1. Copier et configurer les variables d'environnement
cp .env.example .env

# 2. Installer les dépendances système + Python + Node.js
bash scripts/setup-wsl.sh

# 3. Démarrer l'infrastructure Docker
docker compose up -d

# 4. Démarrer tous les services
bash scripts/start-all.sh
```

Frontend : `http://localhost:5174`

## Architecture

```
citevision-v2/
├── frontend/        React 18 + TypeScript + Vite + Tailwind CSS
├── backend/         Go 1.22 + Gin — API REST complète
├── ai-engine/       Python 3.12 + FastAPI — YOLO ONNX + ByteTrack
├── video-engine/    C++ + FFmpeg — Ingestion RTSP dual-pipeline
├── rules-engine/    Go — Moteur de règles DSL
├── infra/           Docker Compose (PostgreSQL, Redis, MQTT, MinIO, go2rtc)
├── installer/       Assistant d'installation premium (Python stdlib)
├── shared/          Schémas JSON partagés + templates de règles
├── scripts/         Scripts de démarrage, validation, purge
└── docs/            Documentation technique
```

## Ports des services

| Service | Port | Description |
|---------|------|-------------|
| Frontend | 5174 | Interface utilisateur React (dev) |
| Backend API | 8081 | API REST Go |
| AI Engine | 8001 | Analyse vidéo YOLO |
| Rules Engine | 8010 | Moteur de règles |
| Video Engine | 9011 | Ingestion RTSP |
| PostgreSQL | 5433 | Base de données |
| Redis | 6380 | Cache / état |
| MQTT | 1884 | Bus événements |
| MinIO | 9000/9001 | Stockage preuves |
| go2rtc | 1984 | Proxy RTSP/WebRTC |
| Installer | 7315 | Assistant d'installation |

## Fonctionnalités

- **Analyse vidéo IA** — Détection personnes, véhicules, objets (YOLO v8 ONNX)
- **Tracking multi-objet** — ByteTrack pour le suivi de trajectoires
- **Événements intelligents** — Intrusion de zone, franchissement de ligne, loitering, crowd
- **Élasticité GPU automatique** — Configuration adaptée au GPU détecté (Tier CPU/Standard/High/Ultra/Max)
- **Règles configurables** — DSL visuel, templates prêts à l'emploi
- **Alertes temps-réel** — Notifications multi-canaux avec preuves vidéo
- **Multi-organisations** — RBAC complet, sites multiples
- **Live View** — Streams RTSP/WebRTC en temps-réel
- **ANPR & Reconnaissance faciale** — Optionnel (PaddleOCR + InsightFace)
- **Audit complet** — Journal immuable de toutes les actions

## Prérequis matériels

| Critère | Minimum | Recommandé |
|---------|---------|------------|
| CPU | 4c/8t @ 2.0 GHz | 8c/16t @ 3.0 GHz+ |
| RAM | 8 Go | 16 Go+ |
| Stockage | 50 Go libres | 200 Go+ |
| GPU | Optionnel | NVIDIA CUDA 11+ |
| OS | Windows 10 build 19041+ / Ubuntu 20.04+ | Windows 11 / Ubuntu 24.04 |

## Tests

```bash
# Tous les tests
bash scripts/run-all-tests.sh

# Par composant
cd backend && go test ./...
cd ai-engine && pytest tests/ -v
cd frontend && npx tsc --noEmit && npm run build
```

## Documentation

- [Architecture](docs/ARCHITECTURE.md)
- [Installation](docs/INSTALL.md)
- [Ports](docs/PORTS.md)
- [Opérations](docs/OPERATIONS.md)
- [Décisions techniques](docs/DECISIONS.md)
