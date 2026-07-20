#!/usr/bin/env bash
set -euo pipefail
cp -f /mnt/c/Users/gheno/citevision/backend/internal/evidence/completeness.go \
  /home/gheno/citevision-v2/backend/internal/evidence/completeness.go
sed -i 's/\r$//' /home/gheno/citevision-v2/backend/internal/evidence/completeness.go
export PATH="/usr/local/go/bin:$PATH"
cd /home/gheno/citevision-v2/backend
go test ./internal/evidence/ -count=1 -v
