# Backend API — CitéVision v2

API REST Go (Gin) qui gère l'ensemble de la logique métier : organisations, sites, caméras, événements, alertes, règles, audit, watchlist et état en temps réel.

## Stack

| Composant | Version |
|-----------|---------|
| Go | 1.22+ |
| Gin | v1.10 |
| PostgreSQL | 15 (via migrations golang-migrate) |
| Redis | 7 (état temps-réel, sessions) |
| MQTT | paho-go (événements AI → backend) |

## Structure

```
backend/
├── cmd/api/main.go          ← Point d'entrée (HTTP + migrations)
├── internal/
│   ├── auth/                ← JWT, TOTP, sessions
│   ├── camera/              ← CRUD caméras, découverte RTSP, chiffrement credentials
│   ├── events/              ← Réception événements AI, pagination, filtres
│   ├── alerts/              ← Moteur d'alertes, règles, notifications
│   ├── rules/               ← Moteur de règles (DSL JSON)
│   ├── correlation/         ← Corrélation spatiale et temporelle
│   ├── dashboard/           ← Métriques agrégées
│   ├── watchlist/           ← Gestion des listes de surveillance
│   ├── spatial/             ← Zones, lignes, calibration
│   ├── audit/               ← Journal d'audit immuable
│   ├── state/               ← État des caméras et du système (Redis)
│   ├── handler/             ← Handlers HTTP (routing)
│   ├── middleware/          ← Auth JWT, RBAC, rate-limit, CORS
│   ├── models/              ← Modèles partagés (structs Go)
│   ├── config/              ← Configuration (env vars)
│   ├── db/                  ← Pool PostgreSQL
│   ├── health/              ← Endpoint /health
│   └── seed/                ← Données de démarrage
├── migrations/              ← SQL up/down (golang-migrate)
├── go.mod
└── go.sum
```

## Démarrage rapide

```bash
# Depuis WSL, depuis la racine du projet
docker compose up -d postgres redis mosquitto

# Lancer l'API
cd backend
go run cmd/api/main.go
```

API disponible sur `http://localhost:8081`

## Variables d'environnement clés

| Variable | Défaut | Description |
|----------|--------|-------------|
| `BACKEND_PORT` | `8081` | Port HTTP |
| `DB_URL` | `postgres://...` | Connexion PostgreSQL |
| `REDIS_ADDR` | `localhost:6380` | Connexion Redis |
| `JWT_SECRET` | *(requis)* | Secret JWT (≥ 32 chars) |
| `MQTT_BROKER` | `tcp://localhost:1884` | Broker MQTT |

## Tests

```bash
cd backend
go test ./...
```

## Migrations

Les migrations SQL sont dans `migrations/` et s'appliquent automatiquement au démarrage si `AUTO_MIGRATE=true`.

Pour les appliquer manuellement :

```bash
migrate -path migrations -database "$DB_URL" up
```
