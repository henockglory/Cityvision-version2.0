# Variables d'environnement plateforme CitéVision

Référence unifiée pour preflight, démo Frigate et rétention disque.

## Backend (Frigate)

| Variable | Défaut | Description |
|----------|--------|-------------|
| `FRIGATE_ENABLED` | `false` | Active l'intégration Frigate |
| `FRIGATE_CONFIG_SYNC` | `false` | Sync DB → YAML Frigate |
| `FRIGATE_EVIDENCE` | `false` | Preuves via clips Frigate |
| `FRIGATE_DEMO_MODE` | `true` | Démo : record event-only, pas continuous 24/7 |
| `FRIGATE_URL` | `http://127.0.0.1:5000` | API Frigate |
| `FRIGATE_DEMO_RETENTION_MIN` | `30` | Purge disque Frigate/MinIO (minutes) |
| `DEMO_RETENTION_MINUTES` | `60` | Purge Postgres démo (minutes) |
| `EVIDENCE_BACKEND` | `ring_buffer` | `ring_buffer` \| `frigate` \| `hybrid` |

## AI engine

| Variable | Défaut | Description |
|----------|--------|-------------|
| `FRIGATE_ENABLED` | `false` | Master switch preuve Frigate |
| `FRIGATE_EVIDENCE` | `false` | Capture track evidence |
| `EVIDENCE_BACKEND` | `ring_buffer` | Backend preuve |
| `FRIGATE_DEMO_ACCEPT_MAX_ALIGN_SEC` | `5` | Gate accept corrélation (s) |
| `FRIGATE_DEMO_MAX_ALIGN_SEC` | `5` | Fenêtre match démo (s) |
| `FRIGATE_CORRELATE_WAIT_SEC` | `35` | Budget poll corrélation |
| `FRIGATE_EVENT_MEDIA_WAIT_SEC` | `25` | Attente clip/snapshot |

## Validation Frigate 1-hit

| Variable | Défaut |
|----------|--------|
| `FRIGATE_MAX_ALIGN_MS` | `5000` |

## Health unifié

- Public : `GET /health/platform`
- Authentifié admin : `GET /api/v1/system/health`
- Repair : `POST /api/v1/internal/supervisor/repair` (clé interne)

## Runtime WSL

Édition : `C:\Users\gheno\citevision` → sync `~/citevision-v2` → restart services.

Voir [SOURCE-OF-TRUTH.md](./SOURCE-OF-TRUTH.md).
