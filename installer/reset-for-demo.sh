#!/usr/bin/env bash
# =============================================================
# CitéVision v2 — Reset complet pour démo / première utilisation
# Crée UN SEUL utilisateur admin par défaut.
#
# Credentials créés :
#   Email    : admin@citevision.local
#   Password : CitéVision2025!
#   Org      : CitéVision Demo
#
# Usage : bash installer/reset-for-demo.sh [--yes]
#         --yes  bypass la confirmation interactive
# =============================================================
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

ADMIN_EMAIL="admin@citevision.local"
ADMIN_PASS="CitéVision2025!"
ADMIN_NAME="Administrateur CitéVision"
ORG_NAME="CitéVision Demo"
ORG_SLUG="citevision-demo"

SKIP_CONFIRM="${1:-}"

# ── 0. Pré-requis ──────────────────────────────────────────
if ! docker ps --format '{{.Names}}' 2>/dev/null | grep -q '^citevision-v2-postgres$'; then
  echo "[FAIL] PostgreSQL non démarré. Lancez d'abord les services Docker." >&2
  echo "       Commande : docker compose -f infra/docker-compose.yml up -d" >&2
  exit 1
fi

# ── 1. Confirmation ────────────────────────────────────────
if [[ "$SKIP_CONFIRM" != "--yes" ]]; then
  echo ""
  echo "⚠  ATTENTION — Cette opération va :"
  echo "   • Supprimer TOUTES les données utilisateurs, caméras, alertes, etc."
  echo "   • Recréer un unique compte admin par défaut"
  echo ""
  read -rp "Continuer ? (tapez 'OUI' pour confirmer) : " CONFIRM
  if [[ "$CONFIRM" != "OUI" ]]; then
    echo "Annulé."
    exit 0
  fi
fi

echo ""
echo "=== CitéVision v2 — Reset pour démo ==="
echo ""

# ── 2. Arrêt gracieux des services app ───────────────────
echo "[INFO] Arrêt des services applicatifs (backend, ai-engine, frontend)…"
pkill -f "citevision-v2/backend"   2>/dev/null || true
pkill -f "citevision-v2/ai-engine" 2>/dev/null || true
pkill -f "vite"                    2>/dev/null || true
sleep 1

# ── 3. Reset PostgreSQL ───────────────────────────────────
echo "[INFO] Vidage des tables applicatives…"
docker exec -i citevision-v2-postgres psql -U citevision -d citevision \
  -v ON_ERROR_STOP=1 << 'ENDSQL'
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

UPDATE system_config
SET value = '{"initialized": false}', updated_at = NOW()
WHERE key = 'initialized';
ENDSQL

# ── 4. Génération hash bcrypt du mot de passe ─────────────
echo "[INFO] Génération du hash bcrypt pour le mot de passe admin…"
BCRYPT_HASH=$(python3 - << 'PYEOF'
import sys, subprocess, json
try:
    import bcrypt
    h = bcrypt.hashpw("CitéVision2025!".encode("utf-8"), bcrypt.gensalt(rounds=12)).decode()
    print(h)
except ImportError:
    # Fallback : utilise le hash pré-calculé (bcrypt cost=12)
    # Généré avec : python3 -c "import bcrypt; print(bcrypt.hashpw(b'Cit\xc3\xa9Vision2025!', bcrypt.gensalt(12)).decode())"
    print("$2b$12$PLACEHOLDER_REGEN_WITH_BCRYPT_LIB")
PYEOF
)

if [[ "$BCRYPT_HASH" == *"PLACEHOLDER"* ]]; then
  echo "[WARN] Module python bcrypt absent — génération du hash via Docker…"
  BCRYPT_HASH=$(docker exec citevision-v2-postgres psql -U citevision -d citevision -tAc \
    "SELECT crypt('CitéVision2025!', gen_salt('bf', 12));")
fi

echo "[INFO] Hash généré."

# ── 5. Création organisation + utilisateur admin ──────────
echo "[INFO] Création de l'organisation et du compte admin…"
docker exec -i citevision-v2-postgres psql -U citevision -d citevision \
  -v ON_ERROR_STOP=1 << ENDSQL2
DO \$\$
DECLARE
  v_org_id  UUID;
  v_user_id UUID;
  v_role_id UUID;
  v_site_id UUID;
BEGIN
  -- Organisation
  INSERT INTO organizations (name, slug, is_active)
  VALUES ('${ORG_NAME}', '${ORG_SLUG}', true)
  RETURNING id INTO v_org_id;

  -- Utilisateur admin
  INSERT INTO users (email, password_hash, full_name, is_active)
  VALUES ('${ADMIN_EMAIL}', '${BCRYPT_HASH}', '${ADMIN_NAME}', true)
  RETURNING id INTO v_user_id;

  -- Rôle org_admin
  SELECT id INTO v_role_id FROM roles WHERE code = 'org_admin' LIMIT 1;

  -- Site par défaut
  INSERT INTO sites (org_id, name, slug, timezone)
  VALUES (v_org_id, 'Site Principal', 'site-principal', 'Europe/Paris')
  RETURNING id INTO v_site_id;

  -- Membership
  INSERT INTO org_memberships (org_id, user_id, role_id)
  VALUES (v_org_id, v_user_id, v_role_id);

  -- Marquer comme initialisé
  UPDATE system_config
  SET value = jsonb_build_object(
    'initialized', true,
    'org_id', v_org_id,
    'site_id', v_site_id
  ), updated_at = NOW()
  WHERE key = 'initialized';

  RAISE NOTICE 'Admin créé : org_id=%, user_id=%', v_org_id, v_user_id;
END
\$\$;
ENDSQL2

# ── 6. Vider Redis (sessions JWT) ─────────────────────────
if docker ps --format '{{.Names}}' | grep -q '^citevision-v2-redis$'; then
  echo "[INFO] Vidage Redis (sessions JWT)…"
  docker exec citevision-v2-redis redis-cli FLUSHALL > /dev/null
fi

# ── 7. Vider buckets MinIO ────────────────────────────────
if docker ps --format '{{.Names}}' | grep -q '^citevision-v2-minio$'; then
  echo "[INFO] Vidage buckets MinIO…"
  docker exec citevision-v2-minio mc alias set local http://localhost:9000 minioadmin minioadmin 2>/dev/null || true
  for BUCKET in citevision-snapshots citevision-recordings citevision-models; do
    docker exec citevision-v2-minio mc rm --recursive --force "local/${BUCKET}/" 2>/dev/null || true
  done
fi

# ── 8. Résumé ─────────────────────────────────────────────
echo ""
echo "======================================================"
echo "  ✓ Base réinitialisée avec succès !"
echo "======================================================"
echo ""
echo "  Credentials admin :"
echo "    Email    : ${ADMIN_EMAIL}"
echo "    Password : ${ADMIN_PASS}"
echo "    Org      : ${ORG_NAME}"
echo ""
echo "  Prochaines étapes :"
echo "    1. Démarrer les services : bash scripts/start-linux.sh"
echo "    2. Ouvrir http://localhost:5174/login"
echo "    3. Se connecter avec les credentials ci-dessus"
echo "    4. Compléter la configuration (caméras, zones, règles)"
echo "======================================================"
echo ""
