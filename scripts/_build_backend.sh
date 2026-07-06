#!/usr/bin/env bash
set -euo pipefail
export PATH=$PATH:/usr/local/go/bin:/home/gheno/go/bin:/usr/local/go/bin

echo "Go: $(go version)"
cd /home/gheno/citevision-v2/backend
go build -o bin/citevision-api ./cmd/api/...
echo "BUILD OK — bin/citevision-api rebuilt"
