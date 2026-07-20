# Exploitation — Citévision v2

## Première utilisation

1. Démarrer infra + services (`bash scripts/start-linux.sh`)
2. Preflight : `bash scripts/preflight_platform.sh`
3. Wizard `/setup` : organisation + super-admin
4. Login — dashboard vide (attendu)
5. Ajouter caméras, zones, règles manuellement

## Health unifié

| Endpoint | Usage |
|----------|--------|
| `GET /health/platform` | Preflight, UI, scripts (public) |
| `GET /api/v1/system/health` | Admin authentifié |
| `POST /api/v1/internal/supervisor/repair` | Auto-heal (clé interne) |

Composants agrégés : postgres, redis, ai_engine, rules_engine, frigate, minio, go2rtc, disk, retention.

## Playbooks supervisor (auto-réparation)

| Symptôme | Action automatique |
|----------|-------------------|
| `rules_engine active_rules=0` | `POST .../internal/sync-rules` |
| `ai_engine degraded` | resync-spatial |
| `frigate events stale` | frigate rebuild |
| `disk > 80%` | repair-streams + retention governor |

Test smoke : `bash scripts/inject_faults_test.sh` (≥ 9/10 attendu).

## Rétention disque

- Config unifiée : `DEMO_RETENTION_MINUTES` (Postgres + shell purge)
- Janitor Go : toutes les 60 s ([`retention.go`](../backend/internal/demo/retention.go))
- Purge Frigate/MinIO : [`demo-retention-purge.sh`](../scripts/demo-retention-purge.sh)
- Budget gate : `bash scripts/validate_disk_budget.sh 30`

Frigate démo : `FRIGATE_DEMO_MODE=true` — pas d'enregistrement continu 24/7.

## Sauvegarde

- PostgreSQL port 5433 : `pg_dump`
- MinIO bucket `citevision-evidence`

## Métriques

`GET http://localhost:8081/metrics` (clé interne sauf `METRICS_PUBLIC=1`)

## WSL

Source de vérité runtime : `~/citevision-v2` — voir [SOURCE-OF-TRUTH.md](./SOURCE-OF-TRUTH.md).

Si virtualisation désactivée : `scripts/check-wsl.sh` et activer Hyper-V / VMP.

## Validation produit

- Métier 5 règles : `python scripts/validate_demo_five_rules.py`
- Frigate 3 règles × 3 runs : `bash scripts/_run_validate_now.sh`
- DoD commercial : [PRODUCT-DOD.md](./PRODUCT-DOD.md)
