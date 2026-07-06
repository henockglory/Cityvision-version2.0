# Installation — Citévision v2

## Prérequis

### WSL Ubuntu 24.04 (recommandé pour dev local)
- WSL2 + virtualisation BIOS activée
- Docker Engine natif (installé par `setup-wsl.sh`)
- Go 1.22+, Node 20+, Python 3.12+
- FFmpeg (test caméra RTSP)

Guide complet : [WSL-MIGRATION.md](WSL-MIGRATION.md)

### Windows (alternative)
- **WSL2 requis** pour la stack IA (InsightFace / PaddleOCR) — `setup.bat` délègue à WSL
- Docker Desktop (PostgreSQL, Redis, MQTT, MinIO, go2rtc)
- Go 1.22+, Node 20+, Python 3.12+
- FFmpeg dans PATH

### Linux (production)
- Docker Compose v2
- Go, Node, Python, CMake, FFmpeg

## Installation headless (Linux natif, sans GUI)

Pour un serveur accessible uniquement en SSH (pas de navigateur sur la machine) :

```bash
cd /opt/citevision-v2   # ou le chemin de déploiement
sudo bash scripts/install-headless.sh
```

Le script enchaîne sans interaction :
1. `installer/linux/bootstrap.sh` — dépendances OS (Docker, Go, Node, Python…)
2. `scripts/setup-wsl.sh` — build, migrations, modèles IA (mode service persisté)
3. Démarrage des services (via `start-linux.sh` si systemd inactif)
4. Vérification séquentielle : backend :8081, AI :8001 (`yolo_loaded`, `face_loaded`, `plate_loaded`), rules :8010, frontend :5174
5. Enregistrement du service systemd (équivalent du clic « Ouvrir CitéVision »)

Options utiles :

```bash
sudo bash scripts/install-headless.sh --start-mode=manual    # service systemd sans auto-start
sudo bash scripts/install-headless.sh --skip-bootstrap       # deps déjà présentes
sudo bash scripts/install-headless.sh --skip-start           # install only
```

Accès distant à l'interface d'installation (port 7315) depuis une autre machine :

```bash
ssh -L 7315:localhost:7315 user@serveur
# Puis ouvrir http://localhost:7315 sur la machine locale
```

Sur WSL, préférer `setup.bat` / `setup.sh` (UI port 7315) ou les commandes manuelles ci-dessous.

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

## Service système (Windows / Linux)

Le **service CitéVision** (NSSM sous Windows, `citevision.service` sous Linux) n'est **pas** créé pendant l'installation. Il est enregistré au **premier accès** :

- **Installateur UI (port 7315)** : clic sur « Ouvrir CitéVision » après le gate IA
- **Installation headless** : automatiquement après vérification santé OK

Le mode de démarrage (`auto` / `manual`) choisi à l'installation est relu depuis `installer/.service_start_mode`.

Vérification :

```bash
# Linux
systemctl status citevision

# Windows
services.msc   # service « CitéVision »
```

## Désinstallation

### Depuis l'application

Paramètres → **Système** (administrateurs uniquement) : statut du service, désinstallation guidée avec progression.

Par défaut, les **volumes Docker sont supprimés**. Cochez « Conserver les données applicatives » pour les garder.

### En ligne de commande

```bash
# Linux / WSL
bash scripts/uninstall-all.sh --yes
bash scripts/uninstall-all.sh --keep-data --yes
```

```powershell
# Windows (administrateur)
powershell -ExecutionPolicy Bypass -File scripts\uninstall-all.ps1 -Yes
powershell -ExecutionPolicy Bypass -File scripts\uninstall-all.ps1 -KeepData -Yes
```

Après désinstallation, relancez `setup.bat` ou `bash scripts/setup-wsl.sh` pour réinstaller.

### Repartir from scratch (purge totale)

```bash
# WSL / Linux — supprime venv, node_modules, volumes Docker, logs
bash scripts/uninstall-all.sh --yes --from-scratch
```

```powershell
# Windows (administrateur)
powershell -ExecutionPolicy Bypass -File scripts\uninstall-all.ps1 -Yes -FromScratch
```

## Politique auto-fix (zéro échec local)

L'installateur et les scripts `setup-wsl.sh` / `start-linux.sh` **ne se contentent plus d'afficher des WARN** : ils exécutent `scripts/ensure-ai-stack.sh` → `scripts/install-ai-models.sh --fix`, qui :

1. Installe les extras Python (InsightFace + PaddleOCR) et ONNX Runtime GPU (CUDA)
2. Télécharge / construit **tous** les modèles (YOLO, buffalo_l, PaddleOCR, modèles secondaires ONNX)
3. Lance des smoke tests d'inférence (`verify_ai_stack.py`) avant tout démarrage de l'AI engine
4. Vérifie le `/health` complet via le registre (`shared/ai-stack-registry.json` + `shared/ai-models.json`) : `yolo_loaded`, `face_loaded`, `plate_loaded`, `yolo_cuda`, `driver_phone_model_loaded`, `seatbelt_model_loaded`
5. Réessaie automatiquement en cas d'échec (5–8 tentatives selon le contexte)

L'étape **Lancement** de l'installateur 7315 affiche les événements `Correction automatique…` en temps réel. Aucune commande manuelle (`pip install`, `download-models.sh`) n'est requise dans le parcours normal.

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

## Validation CI / smoke install

```bash
bash scripts/validate-install-smoke.sh --ci    # CI : shellcheck + pip + imports
bash scripts/validate-install-smoke.sh --fix   # local : inclut téléchargement modèles
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
