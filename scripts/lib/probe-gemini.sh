#!/usr/bin/env bash
# Probe Gemini API key reachability (list models). Exit 0 = OK, 1 = FAIL.
# Never prints the API key. Used by start-full-stack + health_check STRICT.
#
# Candidate order: .env GEMINI/GOOGLE key, then ~/.citevision_gemini_key.tmp.
# If env key is present-but-invalid and keyfile works, sync keyfile → .env.
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
env_key="${GEMINI_API_KEY:-${GOOGLE_API_KEY:-}}"
env_key="$(printf '%s' "$env_key" | tr -d '\r\n' | sed -e 's/^["'\'']//' -e 's/["'\'']$//')"
model="${GEMINI_MODEL:-$model}"

kf="${GEMINI_KEY_FILE:-$HOME/.citevision_gemini_key.tmp}"
kf_key=""
if [[ -f "$kf" ]]; then
  kf_key="$(tr -d '\r\n' <"$kf")"
fi

probe_one() {
  local k="$1"
  curl -sS -o /tmp/citevision-gemini-probe.json -w '%{http_code}' -m 25 \
    "https://generativelanguage.googleapis.com/v1beta/models?key=${k}" 2>/dev/null || echo 000
}

sync_env_key() {
  local k="$1"
  GEMINI_API_KEY="$k" ENV_PATH="$ENV_FILE" python3 - <<'PY'
import os
from pathlib import Path
key = os.environ["GEMINI_API_KEY"].strip()
path = Path(os.environ["ENV_PATH"])
text = path.read_text(encoding="utf-8") if path.exists() else ""
lines, seen = [], False
for line in text.splitlines():
    if line.startswith("GEMINI_API_KEY="):
        lines.append("GEMINI_API_KEY=" + key)
        seen = True
    else:
        lines.append(line)
if not seen:
    lines.append("GEMINI_API_KEY=" + key)
path.write_text("\n".join(lines) + "\n", encoding="utf-8")
PY
}

try_key() {
  local src="$1"
  local k="$2"
  if [[ ${#k} -lt 20 ]]; then
    return 1
  fi
  local code
  code="$(probe_one "$k")"
  if [[ "$code" == "200" ]]; then
    key="$k"
    CHOSEN_SRC="$src"
    return 0
  fi
  return 1
}

CHOSEN_SRC=""
if try_key "env" "$env_key"; then
  :
elif try_key "keyfile" "$kf_key"; then
  # Env had a present-but-invalid key (or was empty): durable keyfile wins.
  sync_env_key "$kf_key" || true
  echo "[OK] gemini_probe: restored GEMINI_API_KEY from keyfile (env key was invalid/missing)"
else
  echo "[FAIL] gemini_probe: models HTTP fail (env_len=${#env_key} kf_len=${#kf_key}; key invalid, quota, or network)" >&2
  exit 1
fi

echo "[OK] gemini_probe: models HTTP 200 (src=${CHOSEN_SRC} key_len=${#key} model=${model})"
exit 0
