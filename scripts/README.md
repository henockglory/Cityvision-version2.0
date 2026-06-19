# Scripts — CitéVision v2

Scripts utilitaires pour le démarrage, l'arrêt, la configuration et la validation de l'environnement.

## Scripts principaux

| Script | OS | Description |
|--------|----|-------------|
| `setup-wsl.sh` | Linux/WSL | Installation complète de l'environnement (Docker, Go, Node, Python, venv, npm) |
| `install-headless.sh` | Linux/WSL | Installation complète sans interaction (bootstrap + setup + démarrage + gate IA) |
| `start-all.sh` | Linux/WSL | Démarre tous les services (Docker compose + backend + AI engine + frontend) |
| `stop-all.sh` | Linux/WSL | Arrête tous les services |
| `run-all-tests.sh` | Linux/WSL | Lance tous les tests (Go, Python, TypeScript) |
| `download-yolo-model.sh` | Linux/WSL | Télécharge le modèle yolov8n.onnx |
| `validate.ps1` | Windows | Validation rapide de l'environnement Windows/WSL |

## install-headless.sh

Installation sans navigateur pour serveur Linux headless (SSH, CI, VM sans GUI). Enchaîne bootstrap, setup, démarrage et vérification des services (gate `yolo_loaded` incluse).

```bash
# Installation complète (recommandé avec sudo pour apt + systemd)
sudo bash scripts/install-headless.sh

# Mode manuel (service créé, démarrage via systemctl)
sudo bash scripts/install-headless.sh --start-mode=manual

# Dépendances déjà installées, sans redémarrer les services
sudo bash scripts/install-headless.sh --skip-bootstrap --skip-start
```

| Option | Défaut | Description |
|--------|--------|-------------|
| `--start-mode=auto\|manual` | `auto` | Mode de démarrage du service systemd |
| `--skip-bootstrap` | — | Ignorer `installer/linux/bootstrap.sh` |
| `--skip-start` | — | Installation uniquement, sans démarrage |
| `--log-file=PATH` | `logs/install-headless.log` | Fichier de log unifié |

## setup-wsl.sh

```bash
# Installation complète
bash scripts/setup-wsl.sh

# Mode silencieux (pour l'installer automatique)
bash scripts/setup-wsl.sh --silent

# Avec log dans un fichier
bash scripts/setup-wsl.sh --silent --log-file=logs/installer.log

# Aide
bash scripts/setup-wsl.sh --help
```

**Actions effectuées :**
1. Mise à jour des paquets système (apt-get)
2. Installation de Docker Engine et Docker Compose plugin
3. Installation de Go 1.22
4. Installation de Node.js 20 LTS
5. Création du virtualenv Python pour l'AI engine
6. Installation des dépendances Python (`pip install -r requirements.txt`)
7. Installation des dépendances frontend (`npm install`)
8. Création des répertoires `ai-engine/models/` et `logs/`

## start-all.sh

```bash
bash scripts/start-all.sh
```

Démarre dans l'ordre :
1. Services infrastructure (docker compose) — PostgreSQL, Redis, MQTT, MinIO, go2rtc
2. Backend API (Go)
3. AI Engine (Python/FastAPI)
4. Frontend (Vite dev server)

## Validation

Scripts de validation par niveau (`validate-l1.sh` → `validate-l13.sh`) pour vérifier chaque couche de l'application :

```bash
bash scripts/validate-l1.sh   # Infrastructure Docker
bash scripts/validate-l2.sh   # Base de données
bash scripts/validate-l3.sh   # Backend API
# ...
bash scripts/validate-final.sh # Validation complète
```
