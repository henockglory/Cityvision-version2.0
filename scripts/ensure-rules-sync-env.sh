#!/usr/bin/env bash
# Ensure rules-engine can sync active rules from the backend API.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=scripts/lib/env-utils.sh
source "$ROOT/scripts/lib/env-utils.sh"
ENV_FILE="$(ensure_env_file "$ROOT")"
load_dotenv "$ENV_FILE"

API="${BACKEND_API_URL:-http://localhost:8081}"
EMAIL="${ADMIN_EMAIL:-glory.henock@hologram.cd}"
PASS="${ADMIN_PASSWORD:-Hologram2026!}"

touch "$ENV_FILE"
if ! grep -q '^INTERNAL_API_KEY=.' "$ENV_FILE" 2>/dev/null; then
  if grep -q '^INTERNAL_API_KEY=' "$ENV_FILE" 2>/dev/null; then
    sed -i 's/^INTERNAL_API_KEY=.*/INTERNAL_API_KEY=changeme_internal_service_key/' "$ENV_FILE"
  else
    echo "INTERNAL_API_KEY=changeme_internal_service_key" >> "$ENV_FILE"
  fi
  echo "[OK] INTERNAL_API_KEY set"
fi
if ! grep -q '^BACKEND_API_URL=.' "$ENV_FILE" 2>/dev/null; then
  if grep -q '^BACKEND_API_URL=' "$ENV_FILE" 2>/dev/null; then
    sed -i 's|^BACKEND_API_URL=.*|BACKEND_API_URL=http://localhost:8081|' "$ENV_FILE"
  else
    echo "BACKEND_API_URL=http://localhost:8081" >> "$ENV_FILE"
  fi
  echo "[OK] BACKEND_API_URL set"
fi

CURRENT_ORG="$(grep '^DEFAULT_ORG_ID=' "$ENV_FILE" 2>/dev/null | cut -d= -f2- | tr -d ' \r' || true)"
if [[ -z "$CURRENT_ORG" ]]; then
  TOKEN=""
  LOGIN_RESP="$(curl -sf -X POST "$API/api/v1/auth/login" -H 'Content-Type: application/json' \
    -d "{\"email\":\"$EMAIL\",\"password\":\"$PASS\"}" 2>/dev/null || true)"
  if [[ -n "$LOGIN_RESP" ]]; then
    TOKEN="$(echo "$LOGIN_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin).get('access_token',''))" 2>/dev/null || true)"
  fi
  if [[ -n "$TOKEN" ]]; then
    ORG="$(curl -sf "$API/api/v1/auth/me" -H "Authorization: Bearer $TOKEN" 2>/dev/null \
      | python3 -c "import sys,json; print(json.load(sys.stdin).get('org_id',''))" 2>/dev/null || true)"
  else
    ORG=""
  fi
  if [[ -n "$ORG" ]]; then
    if grep -q '^DEFAULT_ORG_ID=' "$ENV_FILE" 2>/dev/null; then
      sed -i "s/^DEFAULT_ORG_ID=.*/DEFAULT_ORG_ID=$ORG/" "$ENV_FILE"
    else
      echo "DEFAULT_ORG_ID=$ORG" >> "$ENV_FILE"
    fi
    echo "[OK] DEFAULT_ORG_ID=$ORG"
  else
    echo "[WARN] Could not resolve DEFAULT_ORG_ID — rules-engine sync disabled" >&2
  fi
else
  echo "[OK] DEFAULT_ORG_ID=$CURRENT_ORG"
fi

# MinIO evidence storage (backend + AI engine upload)
MINIO_ENDPOINT_VAL="${MINIO_ENDPOINT:-http://localhost:9003}"
MINIO_ACCESS_VAL="${MINIO_ACCESS_KEY:-${MINIO_ROOT_USER:-citevision}}"
MINIO_SECRET_VAL="${MINIO_SECRET_KEY:-${MINIO_ROOT_PASSWORD:-changeme_minio}}"
MINIO_BUCKET_VAL="${MINIO_BUCKET:-citevision-evidence}"
PUBLIC_API_VAL="${PUBLIC_API_BASE:-http://localhost:8081}"

ensure_kv() {
  local key="$1" val="$2"
  if grep -q "^${key}=." "$ENV_FILE" 2>/dev/null; then
  : # already set
  elif grep -q "^${key}=" "$ENV_FILE" 2>/dev/null; then
    sed -i "s|^${key}=.*|${key}=${val}|" "$ENV_FILE"
    echo "[OK] ${key} set"
  else
    echo "${key}=${val}" >> "$ENV_FILE"
    echo "[OK] ${key} set"
  fi
}

ensure_kv MINIO_ENDPOINT "$MINIO_ENDPOINT_VAL"
ensure_kv MINIO_ACCESS_KEY "$MINIO_ACCESS_VAL"
ensure_kv MINIO_SECRET_KEY "$MINIO_SECRET_VAL"
ensure_kv PUBLIC_API_BASE "$PUBLIC_API_VAL"

# Evidence bucket (distinct from recordings bucket in docker-compose init)
CURRENT_BUCKET="$(grep '^MINIO_BUCKET=' "$ENV_FILE" 2>/dev/null | cut -d= -f2- | tr -d ' \r' || true)"
if [[ -z "$CURRENT_BUCKET" || "$CURRENT_BUCKET" == "citevision-recordings" ]]; then
  if grep -q '^MINIO_BUCKET=' "$ENV_FILE" 2>/dev/null; then
    sed -i 's/^MINIO_BUCKET=.*/MINIO_BUCKET=citevision-evidence/' "$ENV_FILE"
  else
    echo "MINIO_BUCKET=citevision-evidence" >> "$ENV_FILE"
  fi
  echo "[OK] MINIO_BUCKET=citevision-evidence"
else
  echo "[OK] MINIO_BUCKET=$CURRENT_BUCKET"
fi
