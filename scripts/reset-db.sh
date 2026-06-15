#!/usr/bin/env bash
# Reset Citévision v2 database to pre-setup state (wizard from scratch)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "=== Citévision v2 — Reset base de données ==="
echo ""

if ! docker ps --format '{{.Names}}' | grep -q '^citevision-v2-postgres$'; then
  echo "[FAIL] PostgreSQL non démarré. Lance: bash scripts/start-linux.sh" >&2
  exit 1
fi

echo "[INFO] Vidage des tables applicatives..."
docker exec -i citevision-v2-postgres psql -U citevision -d citevision -v ON_ERROR_STOP=1 < "$ROOT/scripts/reset-db.sql"

if docker ps --format '{{.Names}}' | grep -q '^citevision-v2-redis$'; then
  echo "[INFO] Vidage Redis (sessions JWT)..."
  docker exec citevision-v2-redis redis-cli FLUSHALL >/dev/null
fi

echo ""
STATUS=$(curl -sf http://127.0.0.1:8081/api/v1/setup/status 2>/dev/null || echo '{"initialized":null}')
echo "[OK] Base réinitialisée"
echo "     setup/status: $STATUS"
echo ""
echo "Prochaines étapes:"
echo "  1. Vider le navigateur: localStorage cv-auth, cv_token, cv_org_id"
echo "     (ou navigation privée)"
echo "  2. Ouvrir http://localhost:5174/setup"
echo "  3. Créer organisation + compte admin (mot de passe 12+ chars)"
