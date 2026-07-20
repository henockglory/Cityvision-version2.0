#!/usr/bin/env bash
set -euo pipefail
export PATH="/usr/local/go/bin:${PATH:-}"
SRC=/mnt/c/Users/gheno/citevision
DST="${HOME}/citevision-v2"
mkdir -p "$DST/backend/internal/camera"
cp -f "$SRC/backend/internal/camera/"*.go "$DST/backend/internal/camera/"
# also sync related files needed for compile
cp -f "$SRC/backend/cmd/api/main.go" "$DST/backend/cmd/api/main.go" 2>/dev/null || true
cp -f "$SRC/backend/internal/handler/api.go" "$DST/backend/internal/handler/api.go" 2>/dev/null || true
cd "$DST/backend"
go test ./internal/camera/ -count=1 -timeout 90s
