#!/usr/bin/env bash
set -euo pipefail
cd ~/citevision-v2
export PATH="/usr/local/go/bin:/home/gheno/go/bin:${PATH:-}"

echo "=== sync rules-engine main.go + env.example ==="
cp /mnt/c/Users/gheno/citevision/rules-engine/cmd/rules-engine/main.go \
  rules-engine/cmd/rules-engine/main.go
sed -i 's/\r$//' rules-engine/cmd/rules-engine/main.go
cp /mnt/c/Users/gheno/citevision/.env.example .env.example
sed -i 's/\r$//' .env.example

echo "=== normalize WSL .env key ==="
# Remove deprecated name; set verification value 45 (not default 120, not old doc 60)
sed -i '/^RULES_DEDUP_TTL_SECONDS=/d' .env
if grep -q '^RULES_DEDUP_TTL_SEC=' .env; then
  sed -i 's/^RULES_DEDUP_TTL_SEC=.*/RULES_DEDUP_TTL_SEC=45/' .env
else
  echo 'RULES_DEDUP_TTL_SEC=45' >> .env
fi
grep -E 'RULES_DEDUP' .env || true

echo "=== rebuild rules-engine ==="
(cd rules-engine && go build -o bin/rules-engine ./cmd/rules-engine/)

echo "=== restart ==="
bash scripts/_start-rules-engine.sh 2>&1 | tail -30

sleep 2
echo "=== /health ==="
curl -sf http://127.0.0.1:8010/health; echo
echo "=== startup log dedup ==="
grep -a 'dedup_ttl_sec' logs/rules-engine.log | tail -5
