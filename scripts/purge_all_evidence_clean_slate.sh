#!/usr/bin/env bash
# Purge complète des preuves (WSL runtime + reliquats Windows) — base vierge pour re-tests Frigate démo.
# Conforme [P.135] : purge données opérationnelles uniquement (alertes/événements/médias), pas de géométrie zones.
set -euo pipefail

export PATH="/usr/local/go/bin:/usr/bin:/bin:${PATH:-}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="${CITEVISION_ROOT:-$HOME/citevision-v2}"
API="${API:-http://127.0.0.1:8081}"
EMAIL="${ADMIN_EMAIL:-glory.henock@hologram.cd}"
PASS="${ADMIN_PASSWORD:-Henockglory@03}"
REENABLE_DEMO_RULES="${REENABLE_DEMO_RULES:-1}"

psql() {
  docker exec citevision-v2-postgres psql -U citevision -d citevision -v ON_ERROR_STOP=1 "$@"
}

du_path() {
  du -sh "$1" 2>/dev/null | awk '{print $1}' || echo "?"
}

echo "=============================================="
echo " PURGE EVIDENCE — base vierge"
echo " ROOT=$ROOT"
echo "=============================================="

echo ""
echo "=== AVANT (tailles) ==="
echo "MinIO data: $(docker exec citevision-v2-minio du -sh /data 2>/dev/null | awk '{print $1}' || echo '?')"
echo "MinIO evidence: $(docker exec citevision-v2-minio du -sh /data/citevision-evidence 2>/dev/null | awk '{print $1}' || echo '?')"
echo "Clips WSL: $(du_path "$ROOT/backend/data/clips")"
echo "Frigate recordings vol: $(docker run --rm -v infra_frigate_recordings:/v:ro alpine du -sh /v 2>/dev/null | awk '{print $1}' || echo '?')"

echo ""
echo "=== Comptes DB ==="
psql -t -c "
SELECT 'alerts', count(*) FROM alerts
UNION ALL SELECT 'events', count(*) FROM events;
" || true

echo ""
echo "=== Stop IA (libère buffers) ==="
pkill -f citevision-ai 2>/dev/null || true
pkill -f run-ai-engine 2>/dev/null || true
sleep 2

echo ""
echo "=== Purge DB alertes + événements (toutes orgs) ==="
psql -c "DELETE FROM alerts;"
psql -c "DELETE FROM events;"
if psql -t -c "SELECT to_regclass('public.evidence_objects');" | grep -q evidence_objects; then
  psql -c "DELETE FROM evidence_objects;"
fi
# Réinitialise compteurs observation liés aux événements
if psql -t -c "SELECT to_regclass('public.rule_counters');" | grep -q rule_counters; then
  psql -c "UPDATE rule_counters SET count=0, last_event_type='', updated_at=NOW();" || true
fi

echo ""
echo "=== Purge MinIO citevision-evidence (bucket entier) ==="
docker exec citevision-v2-minio sh -c '
  rm -rf /data/citevision-evidence
  mkdir -p /data/citevision-evidence
  echo "minio bucket reset"
'

echo ""
echo "=== Purge enregistrements Frigate (volume Docker) ==="
docker run --rm -v infra_frigate_recordings:/v alpine sh -c '
  rm -rf /v/* 2>/dev/null || true
  echo "frigate recordings cleared"
' || echo "WARN: frigate_recordings volume absent"

echo ""
echo "=== Purge clips locaux WSL ==="
mkdir -p "$ROOT/backend/data/clips"
find "$ROOT/backend/data/clips" -mindepth 1 -maxdepth 1 -type f -delete 2>/dev/null || true
find "$ROOT/backend/data/clips" -mindepth 1 -maxdepth 1 -type d -exec rm -rf {} + 2>/dev/null || true

echo ""
echo "=== Purge reliquats Windows (C:) ==="
WIN_ROOT="/mnt/c/Users/gheno/citevision"
for d in \
  "$WIN_ROOT/backend/data/clips" \
  "/mnt/c/Citevision/backend/data/clips" \
  "/mnt/c/Citevision/backend/data/evidence" \
  "$WIN_ROOT/backend/data/evidence"; do
  if [ -d "$d" ]; then
    find "$d" -mindepth 1 -delete 2>/dev/null || true
    echo "  cleared $d"
  fi
done

# API purge org (MinIO belt-and-suspenders via service) si backend up
if curl -sf "$API/health" >/dev/null 2>&1; then
  echo ""
  echo "=== API maintenance purge (MinIO org prefix) ==="
  LOGIN=$(curl -sf -X POST "$API/api/v1/auth/login" -H 'Content-Type: application/json' \
    -d "{\"email\":\"$EMAIL\",\"password\":\"$PASS\"}" || true)
  TOKEN=$(echo "$LOGIN" | python3 -c "import sys,json; print(json.load(sys.stdin).get('access_token',''))" 2>/dev/null || true)
  ORG=$(curl -sf "$API/api/v1/auth/me" -H "Authorization: Bearer $TOKEN" 2>/dev/null | python3 -c "import sys,json; print(json.load(sys.stdin).get('org_id',''))" 2>/dev/null || true)
  if [ -n "${TOKEN:-}" ] && [ -n "${ORG:-}" ]; then
    curl -sf -X POST "$API/api/v1/orgs/$ORG/maintenance/purge" \
      -H "Authorization: Bearer $TOKEN" \
      -H "Content-Type: application/json" | python3 -m json.tool || true
  else
    echo "  skip API purge (login failed)"
  fi
fi

echo ""
echo "=== Réactivation règles démo (si demandé) ==="
if [ "$REENABLE_DEMO_RULES" = "1" ] && curl -sf "$API/health" >/dev/null 2>&1; then
  python3 "$SCRIPT_DIR/enable-demo-rules.py" || python3 "$ROOT/scripts/enable-demo-rules.py" || true
  docker exec citevision-v2-postgres psql -U citevision -d citevision -c \
    "UPDATE rules SET is_enabled=true, updated_at=NOW() WHERE name LIKE 'Démo%';" 2>/dev/null || true
fi

echo ""
echo "=== Redémarrage IA ==="
python3 "$ROOT/scripts/_restart_ai.py" || bash "$ROOT/scripts/restart-ai-engine.sh" || true

echo ""
echo "=== APRÈS (tailles + comptes) ==="
echo "MinIO evidence: $(docker exec citevision-v2-minio du -sh /data/citevision-evidence 2>/dev/null | awk '{print $1}' || echo '?')"
echo "Clips WSL: $(du_path "$ROOT/backend/data/clips")"
echo "Frigate recordings vol: $(docker run --rm -v infra_frigate_recordings:/v:ro alpine du -sh /v 2>/dev/null | awk '{print $1}' || echo '?')"
psql -t -c "
SELECT 'alerts', count(*) FROM alerts
UNION ALL SELECT 'events', count(*) FROM events;
" || true

echo ""
echo "=== Frigate config (caméras démo) ==="
grep -E '^  cv_' "$ROOT/infra/frigate-config/config.yml" 2>/dev/null | head -8 || true

echo ""
echo "[OK] Purge evidence terminée — base vierge prête pour nouveaux tests frigate_track"
echo "Prochaine étape: laisser tourner la démo puis auditer capture_source=frigate_track"
