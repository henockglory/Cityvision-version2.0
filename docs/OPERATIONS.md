# Exploitation — Citévision v2

## Première utilisation

1. Démarrer infra + services
2. Wizard `/setup` : organisation + super-admin
3. Login — dashboard vide (attendu)
4. Ajouter caméras, zones, règles manuellement

## Sauvegarde

- PostgreSQL port 5433 : `pg_dump`
- MinIO bucket `citevision-evidence`

## Métriques

`GET http://localhost:8081/metrics`

## WSL

Si virtualisation désactivée, exécuter `scripts/check-wsl.sh` et activer Hyper-V / VMP.
