#!/usr/bin/env bash
# Bootstrap complet stack + E2E (WSL) — migrations, venv ML, LF scripts, services
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export PATH="/usr/local/go/bin:$PATH"

echo "╔══════════════════════════════════════════════════╗"
echo "║  CitéVision — ensure-e2e-ready                   ║"
echo "╚══════════════════════════════════════════════════╝"

bash "$ROOT/scripts/fix-sh-lf.sh"

# Docker infra
if ! docker ps --format '{{.Names}}' | grep -q citevision-v2-postgres; then
  echo "[INFO] Démarrage docker-compose…"
  docker compose -f "$ROOT/docker-compose.yml" up -d 2>/dev/null || \
    docker compose -f "$ROOT/docker-compose.wsl.yml" up -d 2>/dev/null || true
fi

# Migrations
if [ -f "$ROOT/backend/migrations/000016_zone_kind.up.sql" ]; then
  docker exec citevision-v2-postgres psql -U citevision -d citevision \
    -c "ALTER TABLE zones ADD COLUMN IF NOT EXISTS zone_kind TEXT NOT NULL DEFAULT '';" 2>/dev/null || true
fi

# Python venv + ML extras (toujours sur ext4 WSL, jamais /mnt/c)
if [ -f "$ROOT/ai-engine/.venv/pyvenv.cfg" ] && grep -q '/mnt/c/' "$ROOT/ai-engine/.venv/pyvenv.cfg" 2>/dev/null; then
  echo "[INFO] Recréation venv native WSL (évite lenteur /mnt/c)…"
  rm -rf "$ROOT/ai-engine/.venv"
fi
if [ ! -x "$ROOT/ai-engine/.venv/bin/python3" ]; then
  python3 -m venv "$ROOT/ai-engine/.venv"
fi
# shellcheck disable=SC1091
source "$ROOT/ai-engine/.venv/bin/activate"
pip install -q -U pip
pip install -q -e "$ROOT/ai-engine/.[identity,anpr,dev]" 2>/dev/null || \
  pip install -q -e "$ROOT/ai-engine/.[dev]"

# Pré-téléchargement modèle InsightFace (évite timeout health au 1er démarrage)
export INSIGHTFACE_HOME="$ROOT/ai-engine/models/insightface"
mkdir -p "$INSIGHTFACE_HOME"
if ! [ -d "$INSIGHTFACE_HOME/models/buffalo_l" ]; then
  echo "[INFO] Téléchargement modèle InsightFace buffalo_l (une fois)…"
  python3 -c "
import os
os.environ['INSIGHTFACE_HOME'] = os.environ.get('INSIGHTFACE_HOME', '')
from insightface.app import FaceAnalysis
fa = FaceAnalysis(name='buffalo_l', root=os.environ['INSIGHTFACE_HOME'])
fa.prepare(ctx_id=-1, det_size=(320, 320))
print('[OK] insightface buffalo_l ready')
" 2>/dev/null || echo "[WARN] insightface preload skipped" >&2
fi

# Env E2E + credentials démo
# shellcheck source=scripts/lib/env-utils.sh
source "$ROOT/scripts/lib/env-utils.sh"
ENV_FILE="$(ensure_env_file "$ROOT")"
ensure_kv() {
  local key="$1" val="$2"
  if grep -q "^${key}=" "$ENV_FILE" 2>/dev/null; then
    sed -i "s|^${key}=.*|${key}=${val}|" "$ENV_FILE" 2>/dev/null || \
      sed -i '' "s|^${key}=.*|${key}=${val}|" "$ENV_FILE" 2>/dev/null || true
  else
    echo "${key}=${val}" >> "$ENV_FILE"
  fi
}
ensure_kv E2E_MODE 1
ensure_kv ADMIN_EMAIL glory.henock@hologram.cd
ensure_kv ADMIN_PASSWORD 'Hologram2026!'

bash "$ROOT/scripts/restart-api-frontend.sh"
wait_http_ok "http://localhost:8081/health" 90 || {
  echo "[WARN] backend health slow — continuing" >&2
}

bash "$ROOT/scripts/ensure-rules-sync-env.sh"
bash "$ROOT/scripts/restart-ai-engine.sh"

LOGDIR="$ROOT/logs"
stop_from_pid "$LOGDIR/rules-engine.pid" 2>/dev/null || true
free_port 8010 2>/dev/null || true
sleep 1
go_bin="$(command -v go || echo /usr/local/go/bin/go)"
start_bg rules-engine "$ROOT/rules-engine" "$go_bin run ./cmd/rules-engine" "$LOGDIR" "$ENV_FILE"

for _ in $(seq 1 40); do
  curl -sf http://localhost:8081/health >/dev/null 2>&1 && break
  sleep 2
done
for _ in $(seq 1 40); do
  curl -sf http://localhost:8001/health >/dev/null 2>&1 && break
  sleep 2
done
for _ in $(seq 1 30); do
  curl -sf http://localhost:8010/health >/dev/null 2>&1 && break
  sleep 2
done

echo ""
echo "[OK] Stack prête — backend :8081, IA :8001, rules-engine :8010"
curl -sf http://localhost:8001/health | python3 -m json.tool 2>/dev/null || true
echo "=== ensure-e2e-ready OK ==="
