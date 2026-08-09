#!/usr/bin/env bash
# Probe Gemini API key reachability (list models). Exit 0 = OK, 1 = FAIL.
# Never prints the API key. Used by start-full-stack + health_check STRICT.
set -euo pipefail

ROOT="${1:-}"
if [[ -z "$ROOT" ]]; then
  ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
fi
ENV_FILE="${2:-$ROOT/.env}"

key=""
model="gemini-2.0-flash"
if [[ -f "$ENV_FILE" ]]; then
  # shellcheck disable=SC1090
  set -a
  # Load only GEMINI_* lines to avoid side effects from other exports.
  while IFS= read -r line || [[ -n "$line" ]]; do
    case "$line" in
      GEMINI_API_KEY=*|GEMINI_MODEL=*|GOOGLE_API_KEY=*)
        export "$line" 2>/dev/null || true
        ;;
    esac
  done <"$ENV_FILE"
  set +a
fi
key="${GEMINI_API_KEY:-${GOOGLE_API_KEY:-}}"
key="$(printf '%s' "$key" | tr -d '\r\n' | sed -e 's/^["'\'']//' -e 's/["'\'']$//')"
model="${GEMINI_MODEL:-$model}"

if [[ ${#key} -lt 20 ]]; then
  kf="${GEMINI_KEY_FILE:-$HOME/.citevision_gemini_key.tmp}"
  if [[ -f "$kf" ]]; then
    key="$(tr -d '\r\n' <"$kf")"
  fi
fi

if [[ ${#key} -lt 20 ]]; then
  echo "[FAIL] gemini_probe: GEMINI_API_KEY missing/too short" >&2
  exit 1
fi

code="$(
  curl -sS -o /tmp/citevision-gemini-probe.json -w '%{http_code}' -m 25 \
    "https://generativelanguage.googleapis.com/v1beta/models?key=${key}" 2>/dev/null || echo 000
)"
if [[ "$code" != "200" ]]; then
  echo "[FAIL] gemini_probe: models HTTP ${code} (key invalid, quota, or network)" >&2
  exit 1
fi
echo "[OK] gemini_probe: models HTTP 200 (key_len=${#key} model=${model})"
exit 0
