#!/usr/bin/env bash
set -uo pipefail
export PATH="$PATH:/usr/local/go/bin"
W=/mnt/c/Users/gheno/citevision
R="$HOME/citevision-v2"

# Sync backend source (Go) + migrations, stripping CRLF from .go/.sql
rsync -a --delete \
  --exclude 'bin/' --exclude '*.exe' \
  "$W/backend/internal/" "$R/backend/internal/"
rsync -a "$W/backend/migrations/" "$R/backend/migrations/"
rsync -a "$W/backend/models/" "$R/backend/models/" 2>/dev/null || true
find "$R/backend/internal" -name '*.go' -exec sed -i 's/\r$//' {} +
find "$R/backend/migrations" -name '*.sql' -exec sed -i 's/\r$//' {} +
echo SYNCED

cd "$R/backend" && go build -o bin/citevision-api ./cmd/api 2>&1 && echo BACKEND_BUILD_OK
