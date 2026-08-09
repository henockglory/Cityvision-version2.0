#!/usr/bin/env bash
# Upsert GEMINI_API_KEY into WSL runtime .env + keyfile. Never echo the key.
# Usage: bash scripts/lib/set-gemini-key.sh '<api-key>'
set -euo pipefail

KEY="${1:-}"
if [[ "$KEY" == "saisissez votre nouvelle clé API" ]] || [[ ${#KEY} -lt 20 ]]; then
  echo "[FAIL] Remplacez le placeholder par une vraie cle Google AI Studio (len>=20)." >&2
  exit 2
fi

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ENV_PATH="${ROOT}/.env"

upsert_env_key() {
  local env_path="$1"
  [[ -f "$env_path" ]] || touch "$env_path"
  GEMINI_API_KEY="$KEY" ENV_PATH="$env_path" python3 - <<'PY'
from pathlib import Path
import os
p = Path(os.environ["ENV_PATH"])
key = os.environ["GEMINI_API_KEY"].strip()
text = p.read_text(encoding="utf-8", errors="replace") if p.exists() else ""
lines, seen = [], False
for line in text.splitlines():
    if line.startswith("GEMINI_API_KEY="):
        lines.append("GEMINI_API_KEY=" + key)
        seen = True
    else:
        lines.append(line.rstrip("\r"))
if not seen:
    lines.append("GEMINI_API_KEY=" + key)
# Ensure GEMINI_ENABLED=1
has_en = False
out = []
for line in lines:
    if line.startswith("GEMINI_ENABLED="):
        out.append("GEMINI_ENABLED=1")
        has_en = True
    else:
        out.append(line)
if not has_en:
    out.append("GEMINI_ENABLED=1")
p.write_text("\n".join(out) + "\n", encoding="utf-8")
print("upserted", p)
PY
}

write_keyfile() {
  local path="$1"
  printf '%s\n' "$KEY" >"$path"
  chmod 600 "$path" 2>/dev/null || true
  sed -i 's/\r$//' "$path" 2>/dev/null || true
  echo "keyfile ok path=$path len=$(wc -c <"$path" | tr -d ' ')"
}

upsert_env_key "$ENV_PATH"
write_keyfile "${HOME}/.citevision_gemini_key.tmp"
write_keyfile "${ROOT}/.citevision_gemini_key.tmp"

# Best-effort Windows mirrors (do not fail if absent).
for m in \
  /mnt/c/Users/gheno/citevision \
  /mnt/c/Users/gheno/citevision-v2 \
  /mnt/c/Citevision \
  /mnt/c/Users/gheno/citevision_optimized
do
  [[ -d "$m" ]] || continue
  [[ -f "$m/.env" ]] && upsert_env_key "$m/.env" || true
  write_keyfile "$m/.citevision_gemini_key.tmp" || true
done

echo "[OK] GEMINI_API_KEY updated (WSL runtime + keyfile). Relancez Start-CiteVision.ps1"
exit 0
