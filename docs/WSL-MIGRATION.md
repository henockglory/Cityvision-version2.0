# Migration WSL Ubuntu 24.04 — Citévision v2

Méthode recommandée pour le développement local : **WSL2 + Docker Engine natif** (sans Docker Desktop).

## Pourquoi WSL ?

- I/O disque 3–10× plus rapides que `/mnt/c/`
- Docker Engine natif, pas de lenteur Docker Desktop
- Scripts Linux alignés sur la production

## Prérequis Windows

1. **BIOS** : activer Intel VT-x / AMD-V
2. **PowerShell Admin** :

```powershell
cd C:\Users\gheno\citevision-v2
powershell -ExecutionPolicy Bypass -File scripts\enable-wsl-windows.ps1
```

3. Redémarrer Windows
4. Vérifier :

```powershell
wsl -l -v
# Ubuntu-24.04  Running  2
wsl -d Ubuntu-24.04 -- echo OK
```

## Installation dans WSL

```bash
# Depuis Windows, copier le projet dans le home WSL (recommandé)
wsl -d Ubuntu-24.04 -- bash /mnt/c/Users/gheno/citevision-v2/scripts/sync-to-wsl.sh

# Ou manuellement
cd ~/citevision-v2
bash scripts/setup-wsl.sh
```

Si `docker` échoue avec permission denied :

```bash
sudo usermod -aG docker $USER
newgrp docker
sudo service docker start
```

Configurer `.env` (copier depuis Windows ou recréer) :

```bash
cp .env.example .env
# Éditer CAMERA_TEST_* si besoin
```

## Démarrer la stack

```bash
cd ~/citevision-v2
bash scripts/start-linux.sh
```

- Setup : http://localhost:5174/setup
- Backend : http://localhost:8081/health
- go2rtc : http://localhost:1984

Arrêt :

```bash
bash scripts/stop-linux.sh
```

Diagnostic :

```bash
bash scripts/doctor-linux.sh
```

## Source unique du projet

**Répertoire actif : `citevision-v2` uniquement** (`C:\Users\gheno\citevision-v2` sous Windows, `~/citevision-v2` sous WSL).

L'ancienne copie `C:\Users\gheno\citevision` a été supprimée après migration du pipeline live. Ne pas la recréer.

Après toute modification sous Windows :

```bash
bash scripts/sync-to-wsl.sh && bash scripts/stop-linux.sh && bash scripts/start-linux.sh
```

Puis recharger le navigateur (Ctrl+Shift+R) sur http://localhost:5174/login

## Synchroniser après modifications Windows

```bash
bash scripts/sync-to-wsl.sh
```

Le script exclut `node_modules`, `.venv`, `logs`, `.env`.

## Setup wizard

- Mot de passe admin : min 12 caractères, majuscule + minuscule + chiffre
- Exemple : `Hologram2026!`
- Organisation : slug auto-généré si omis

## Dépannage

| Symptôme | Solution |
|----------|----------|
| `HCS_E_HYPERV_NOT_INSTALLED` | Activer virtualisation BIOS + `enable-wsl-windows.ps1` |
| `permission denied` docker | `sudo usermod -aG docker $USER && newgrp docker` |
| Backend timeout | `docker compose -f infra/docker-compose.yml ps` |
| Port occupé | `bash scripts/stop-linux.sh` puis relancer |
| Lent sur `/mnt/c/` | Toujours travailler dans `~/citevision-v2` |

## Ports v2

| Service | Port |
|---------|------|
| PostgreSQL | 5433 |
| Redis | 6380 |
| MQTT | 1884 |
| MinIO | 9003/9004 |
| go2rtc | 1984 |
| Backend | 8081 |
| AI Engine | 8001 |
| Rules Engine | 8010 |
| Frontend | 5174 |
