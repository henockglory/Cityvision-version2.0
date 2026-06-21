#!/usr/bin/env bash
# Ensure rules-engine can sync active rules from the backend API.
# Usage:
#   bash ensure-rules-sync-env.sh              # static keys + org resolution
#   bash ensure-rules-sync-env.sh --static-only
#   bash ensure-rules-sync-env.sh --resolve-org
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=scripts/lib/env-utils.sh
source "$ROOT/scripts/lib/env-utils.sh"
ENV_FILE="$(ensure_env_file "$ROOT")"
load_dotenv "$ENV_FILE"

MODE="all"
for arg in "$@"; do
  case "$arg" in
    --static-only) MODE="static" ;;
    --resolve-org) MODE="org" ;;
    --help)
      echo "Usage: bash scripts/ensure-rules-sync-env.sh [--static-only|--resolve-org]"
      exit 0
      ;;
  esac
done

API="${BACKEND_API_URL:-http://localhost:8081}"
EMAIL="${ADMIN_EMAIL:-glory.henock@hologram.cd}"
PASS="${ADMIN_PASSWORD:-Hologram2026!}"

ensure_static_keys() {
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

  ensure_kv() {
    local key="$1" val="$2"
    if grep -q "^${key}=." "$ENV_FILE" 2>/dev/null; then
      :
    elif grep -q "^${key}=" "$ENV_FILE" 2>/dev/null; then
      sed -i "s|^${key}=.*|${key}=${val}|" "$ENV_FILE"
      echo "[OK] ${key} set"
    else
      echo "${key}=${val}" >> "$ENV_FILE"
      echo "[OK] ${key} set"
    fi
  }

  MINIO_ENDPOINT_VAL="${MINIO_ENDPOINT:-http://localhost:9003}"
  MINIO_ACCESS_VAL="${MINIO_ACCESS_KEY:-${MINIO_ROOT_USER:-citevision}}"
  MINIO_SECRET_VAL="${MINIO_SECRET_KEY:-${MINIO_ROOT_PASSWORD:-changeme_minio}}"
  MINIO_BUCKET_VAL="${MINIO_BUCKET:-citevision-evidence}"
  PUBLIC_API_VAL="${PUBLIC_API_BASE:-http://localhost:8081}"

  ensure_kv MINIO_ENDPOINT "$MINIO_ENDPOINT_VAL"
  ensure_kv MINIO_ACCESS_KEY "$MINIO_ACCESS_VAL"
  ensure_kv MINIO_SECRET_KEY "$MINIO_SECRET_VAL"
  ensure_kv PUBLIC_API_BASE "$PUBLIC_API_VAL"

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
}

backend_reachable() {
  curl -sf "${API}/health" >/dev/null 2>&1
}

setup_initialized() {
  local resp
  resp="$(curl -sf "${API}/api/v1/setup/status" 2>/dev/null || true)"
  [[ -n "$resp" ]] && echo "$resp" | grep -q '"initialized"[[:space:]]*:[[:space:]]*true'
}

resolve_org_id() {
  CURRENT_ORG="$(grep '^DEFAULT_ORG_ID=' "$ENV_FILE" 2>/dev/null | cut -d= -f2- | tr -d ' \r' || true)"
  if [[ -n "$CURRENT_ORG" ]]; then
    echo "[OK] DEFAULT_ORG_ID=$CURRENT_ORG"
    return 0
  fi

  if ! backend_reachable; then
    echo "[INFO] Backend not ready — org resolution deferred"
    return 0
  fi

  if ! setup_initialized; then
    echo "[INFO] Setup wizard pending — rules sync will activate after first configuration"
    return 0
  fi

  TOKEN=""
  LOGIN_RESP="$(curl -sf -X POST "$API/api/v1/auth/login" -H 'Content-Type: application/json' \
    -d "{\"email\":\"$EMAIL\",\"password\":\"$PASS\"}" 2>/dev/null || true)"
  if [[ -n "$LOGIN_RESP" ]]; then
    TOKEN="$(echo "$LOGIN_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin).get('access_token',''))" 2>/dev/null || true)"
  fi

  ORG=""
  if [[ -n "$TOKEN" ]]; then
    ORG="$(curl -sf "$API/api/v1/auth/me" -H "Authorization: Bearer $TOKEN" 2>/dev/null \
      | python3 -c "import sys,json; print(json.load(sys.stdin).get('org_id',''))" 2>/dev/null || true)"
  fi

  if [[ -n "$ORG" ]]; then
    if grep -q '^DEFAULT_ORG_ID=' "$ENV_FILE" 2>/dev/null; then
      sed -i "s/^DEFAULT_ORG_ID=.*/DEFAULT_ORG_ID=$ORG/" "$ENV_FILE"
    else
      echo "DEFAULT_ORG_ID=$ORG" >> "$ENV_FILE"
    fi
    echo "[OK] DEFAULT_ORG_ID=$ORG"
    return 0
  fi

  echo "[WARN] Could not resolve DEFAULT_ORG_ID — rules-engine sync disabled" >&2
  return 1
}

case "$MODE" in
  static)
    ensure_static_keys
    ;;
  org)
    resolve_org_id || true
    ;;
  all)
    ensure_static_keys
    resolve_org_id || true
    ;;
esac
