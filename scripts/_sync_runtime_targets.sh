#!/usr/bin/env bash
set -euo pipefail
WIN=/mnt/c/Users/gheno/citevision
DEST=~/citevision-v2
mkdir -p "$DEST"
for d in backend rules-engine frontend shared scripts ai-engine docs installer tests .github; do
  if [ -d "$WIN/$d" ]; then
    rsync -a \
      --exclude node_modules --exclude .venv --exclude dist --exclude bin --exclude __pycache__ \
      "$WIN/$d/" "$DEST/$d/"
  fi
done
if [ -d "$WIN/infra" ]; then
  rsync -a --exclude data \
    "$WIN/infra/" "$DEST/infra/"
fi
for f in .env.example .gitattributes .gitignore Makefile README.md setup.sh setup.bat; do
  if [ -f "$WIN/$f" ]; then
    cp "$WIN/$f" "$DEST/$f"
  fi
done
find "$DEST" -type f \( -name '*.sh' -o -name '*.py' -o -name '*.go' -o -name '*.sql' \) -exec sed -i 's/\r$//' {} + 2>/dev/null || true
cd "$DEST"
git fetch origin
git fetch v2
git reset --hard origin/main
echo "[OK] WSL $DEST at $(git log -1 --oneline)"
