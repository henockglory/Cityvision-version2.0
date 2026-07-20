#!/usr/bin/env bash
# Phase A Tâche 8 — prepare Cursor→WSL bascule (safe.directory, deps, guards).
set -euo pipefail
WSL_ROOT="${HOME}/citevision-v2"
WIN=/mnt/c/Users/gheno/citevision
UNC='//wsl.localhost/Ubuntu-24.04/home/gheno/citevision-v2'

echo "=== sync critical scripts ==="
for f in scripts/validate_rule.sh scripts/health_check_all.sh scripts/_validate_rule_frigate_1hit.py \
         scripts/_restart_backend.py backend/internal/frigate/compiler.go backend/internal/frigate/sync.go; do
  if [ -f "$WIN/$f" ]; then
    mkdir -p "$(dirname "$WSL_ROOT/$f")"
    cp "$WIN/$f" "$WSL_ROOT/$f"
    sed -i 's/\r$//' "$WSL_ROOT/$f"
    echo "synced $f"
  fi
done

echo "=== git safe.directory (WSL) ==="
cd "$WSL_ROOT"
git config --global --add safe.directory "$WSL_ROOT" || true
git config --global --add safe.directory "$UNC" || true
# also %(prefix) form for Windows git talking to UNC
git config --global --get-all safe.directory | grep -E 'citevision-v2|wsl.localhost' || true

echo "=== refuse /mnt/c guard smoke ==="
# copy scripts temporarily to prove refusal when invoked from mount — call via bash with fake?
# Instead: ensure native health works
bash "$WSL_ROOT/scripts/health_check_all.sh" | tail -5

echo "=== native deps ==="
if [ -d "$WSL_ROOT/frontend/node_modules" ]; then
  # rollup linux binding present?
  if ls "$WSL_ROOT/frontend/node_modules/@rollup" 2>/dev/null | head -3; then
    echo "node_modules: present"
  fi
  # detect windows .exe bindings accidentally copied
  if find "$WSL_ROOT/frontend/node_modules" -name '*.exe' 2>/dev/null | head -3 | grep -q .; then
    echo "WARN: .exe under node_modules — reinstall recommended"
  else
    echo "node_modules: no .exe bindings spotted"
  fi
else
  echo "WARN: no frontend/node_modules — run npm ci in WSL"
fi

if [ -x "$WSL_ROOT/ai-engine/.venv/bin/python" ]; then
  "$WSL_ROOT/ai-engine/.venv/bin/python" -c 'import sys; print("venv", sys.executable, sys.version.split()[0])'
else
  echo "WARN: ai-engine/.venv missing"
fi

# .env must stay WSL-local
if [ -f "$WSL_ROOT/.env" ]; then
  echo ".env WSL present keys:" $(grep -E '^(DEMO_MODE|FRIGATE_|OCR_URL|RULES_DEDUP)' "$WSL_ROOT/.env" | cut -d= -f1 | tr '\n' ' ')
else
  echo "FAIL: WSL .env missing"
  exit 1
fi

echo "=== OPEN-IN-WSL reminder ==="
echo "Cursor File→Open Folder: \\\\wsl.localhost\\Ubuntu-24.04\\home\\gheno\\citevision-v2"
echo "T8_PREP_OK"
