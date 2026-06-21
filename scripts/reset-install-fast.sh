#!/usr/bin/env bash
# Reset rapide pour retester setup.bat sans retélécharger modèles/venv/node_modules.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "=== CitéVision — reset installation rapide ==="

echo "[INFO] Sentinels installateur…"
rm -f installer/.bootstrap_done installer/.service_start_mode ai-engine/.venv/.installed_ok
rm -f logs/*.pid 2>/dev/null || true

echo "[INFO] Remise à zéro état setup (PostgreSQL)…"
docker compose -f infra/docker-compose.yml up -d postgres
sleep 4

if docker ps --format '{{.Names}}' | grep -q '^citevision-v2-postgres$'; then
  docker exec -i citevision-v2-postgres psql -U citevision -d citevision -v ON_ERROR_STOP=0 <<'ENDSQL'
TRUNCATE TABLE
  audit_logs,
  refresh_tokens,
  alerts,
  incidents,
  events,
  rules,
  cameras,
  zones,
  lines,
  org_memberships,
  sites,
  users,
  organizations
RESTART IDENTITY CASCADE;
INSERT INTO system_config (key, value, updated_at)
VALUES ('initialized', '{"initialized": false}', NOW())
ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = NOW();
ENDSQL
  echo "[OK] Base prête pour /setup"
else
  echo "[WARN] PostgreSQL non démarré — la base sera vierge au prochain setup"
fi

docker compose -f infra/docker-compose.yml down 2>/dev/null || true

echo ""
echo "[OK] Reset terminé — conservé : modèles IA, venv, node_modules, images Docker"
echo "     Relancez : setup.bat puis register-service.bat après le lancement"
echo ""
