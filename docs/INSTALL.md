# Installation — Citévision v2

## Prérequis

### WSL Ubuntu 24.04 (recommandé pour dev local)
- WSL2 + virtualisation BIOS activée
- Docker Engine natif (installé par `setup-wsl.sh`)
- Go 1.22+, Node 20+, Python 3.12+
- FFmpeg (test caméra RTSP)

Guide complet : [WSL-MIGRATION.md](WSL-MIGRATION.md)

### Windows (alternative)
- Docker Desktop (PostgreSQL, Redis, MQTT, MinIO, go2rtc)
- Go 1.22+, Node 20+, Python 3.12+
- FFmpeg dans PATH

### Linux (production)
- Docker Compose v2
- Go, Node, Python, CMake, FFmpeg

## Démarrage rapide WSL (recommandé)

```bash
# Depuis WSL, après sync du projet vers ~/citevision-v2
cd ~/citevision-v2
bash scripts/setup-wsl.sh
bash scripts/start-linux.sh
```

Depuis Windows (première sync) :

```powershell
wsl -d Ubuntu-24.04 -- bash /mnt/c/Users/gheno/citevision-v2/scripts/sync-to-wsl.sh
```

- Frontend: http://localhost:5174/setup (première visite)
- Backend: http://localhost:8081/health
- go2rtc: http://localhost:1984

Arrêt :

```bash
bash scripts/stop-linux.sh
```

Diagnostic :

```bash
bash scripts/doctor-linux.sh
```

## Démarrage rapide Windows (Docker Desktop)

```powershell
cd C:\Users\gheno\citevision-v2
powershell -File scripts\doctor-windows.ps1
powershell -File scripts\start-windows.ps1
```

Arrêt :

```powershell
powershell -File scripts\stop-windows.ps1
```

## Configuration

```powershell
copy .env.example .env
# start-windows.ps1 génère JWT_SECRET, AUDIT_SIGNING_KEY, CAMERA_CREDENTIAL_KEY si absents
```

Caméra test (`.env` local uniquement, jamais committer):

```
CAMERA_TEST_IP=192.168.1.108
CAMERA_TEST_USER=admin
CAMERA_TEST_PASSWORD=<secret>
```

## Validation

```powershell
powershell -File scripts\validate.ps1
powershell -File scripts\validate-full.ps1 -SkipLiveStack
powershell -File scripts\validate-full.ps1   # avec stack démarrée
```

## Ports v2 (isolation v1)

| Service | Port |
|---------|------|
| PostgreSQL | 5433 |
| Redis | 6380 |
| MQTT | 1884 |
| MinIO API | 9003 |
| MinIO Console | 9004 |
| go2rtc | 1984 |
| Backend | 8081 |
| AI Engine | 8001 |
| Rules Engine | 8010 |
| Frontend | 5174 |
