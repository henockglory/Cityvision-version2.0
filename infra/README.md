# Infrastructure — CitéVision v2

Configuration des services infrastructure gérés par Docker Compose.

## Services

| Service | Image | Port | Description |
|---------|-------|------|-------------|
| `postgres` | postgres:15 | 5433 | Base de données principale |
| `redis` | redis:7 | 6380 | Cache et état temps-réel |
| `mosquitto` | eclipse-mosquitto | 1884 | Broker MQTT (événements AI → backend) |
| `minio` | minio/minio | 9000/9001 | Stockage objet (preuves vidéo/images) |
| `go2rtc` | alexxit/go2rtc | 1984 | Proxy RTSP/WebRTC pour le live view |

## Fichiers de configuration

```
infra/
├── mosquitto.conf     ← Configuration Mosquitto (auth, logging, persistence)
└── init-minio.sh      ← Initialisation du bucket MinIO (citevision-evidence)
```

## Démarrage

```bash
# Depuis la racine du projet (WSL)
docker compose up -d

# Vérifier l'état
docker compose ps

# Logs d'un service
docker compose logs -f postgres
```

## Connexions par défaut

| Service | URL / Connexion |
|---------|----------------|
| PostgreSQL | `postgres://citevision:changeme@localhost:5433/citevision` |
| Redis | `localhost:6380` |
| MQTT | `tcp://localhost:1884` (anonymous) |
| MinIO API | `http://localhost:9000` (user: `citevision`, password: dans `.env`) |
| MinIO Console | `http://localhost:9001` |
| go2rtc | `http://localhost:1984` |

## Volumes persistants

Les données sont stockées dans des volumes Docker nommés :
- `citevision_postgres_data`
- `citevision_redis_data`
- `citevision_minio_data`
- `citevision_mosquitto_data`

Pour réinitialiser complètement :
```bash
docker compose down -v
```
