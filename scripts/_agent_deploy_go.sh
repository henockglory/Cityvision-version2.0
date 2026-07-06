#!/usr/bin/env bash
set -euo pipefail
export PATH="$PATH:/usr/local/go/bin"
W=/mnt/c/Users/gheno/citevision
R=~/citevision-v2
for f in backend/internal/demo/service.go backend/internal/demo/retention.go rules-engine/internal/actions/executor.go; do
  mkdir -p "$R/$(dirname "$f")"
  cp "$W/$f" "$R/$f"
  sed -i 's/\r$//' "$R/$f"
done
echo SYNCED
cd "$R/backend" && go build -o bin/citevision-api ./cmd/api && echo BACKEND_OK
cd "$R/rules-engine" && go build -o bin/rules-engine ./cmd/rules-engine && echo RULES_OK
