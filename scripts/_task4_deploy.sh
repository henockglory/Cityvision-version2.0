#!/usr/bin/env bash
set -euo pipefail
cd ~/citevision-v2
export PATH="/usr/local/go/bin:/home/gheno/go/bin:${PATH:-}"

sync_file() {
  local f="$1"
  mkdir -p "$(dirname "$f")"
  cp "/mnt/c/Users/gheno/citevision/$f" "$f"
  sed -i 's/\r$//' "$f"
  echo "ok $f"
}

sync_file backend/internal/evidence/completeness.go
sync_file backend/internal/evidence/completeness_test.go
sync_file backend/internal/alerts/service.go
sync_file rules-engine/internal/actions/executor.go
sync_file rules-engine/internal/actions/executor_test.go
sync_file frontend/src/components/evidence/EvidenceViewer.tsx
sync_file frontend/src/i18n/fr.json
sync_file frontend/src/i18n/en.json

echo "=== go test evidence ==="
(cd backend && go test ./internal/evidence/ -count=1)
echo "=== go test rules-engine actions ==="
(cd rules-engine && go test ./internal/actions/ -count=1 -run 'Evidence|Plate')

echo "=== rebuild api + rules-engine ==="
(cd backend && go build -o bin/citevision-api ./cmd/api/)
(cd rules-engine && go build -o bin/rules-engine ./cmd/rules-engine/)

# Restart backend with .env
python3 scripts/_restart_backend.py 2>&1 | tail -20
bash scripts/_start-rules-engine.sh 2>&1 | tail -15

echo "=== health ==="
curl -sf http://127.0.0.1:8081/health; echo
curl -sf http://127.0.0.1:8010/health; echo
