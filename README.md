# Citévision 2.0

Plateforme de vidéosurveillance intelligente — React / Go / C++ / Python.

## Documentation principale

- **[Prompt agent IA](docs/PROMPT-AGENT.md)** — spec complète et 14 livrables
- **[État du projet](docs/STATE.md)** — reprise après interruption
- **[Installation](docs/INSTALL.md)** — déploiement from scratch

## Démarrage rapide

```bash
cp .env.example .env
docker compose up -d
bash scripts/start-all.sh    # WSL/Linux
powershell -File scripts/validate.ps1   # Windows
```

| Service | URL |
|---------|-----|
| Frontend | http://localhost:5173 |
| API | http://localhost:8080/api/v1 |
| AI Engine | http://localhost:8000 |

**Login seed:** `admin@citevision.local` / `Citevision123!`

## Composants

| Composant | Chemin |
|-----------|--------|
| Frontend | `frontend/` |
| Backend API | `backend/` |
| AI Engine | `ai-engine/` |
| Video Engine | `video-engine/` |
| Infrastructure | `docker-compose.yml` |

## Validation

```bash
bash scripts/validate-final.sh
# ou Windows:
powershell -File scripts/validate.ps1
```
