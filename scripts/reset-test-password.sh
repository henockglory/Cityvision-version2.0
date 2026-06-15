#!/usr/bin/env bash
set -euo pipefail
PASS="${1:-CitevisionTest2026!}"
HASH=$(cd ~/citevision-v2/backend && /usr/local/go/bin/go run ./cmd/hashpw "$PASS")
docker exec citevision-v2-postgres psql -U citevision -d citevision -c "UPDATE users SET password_hash='$HASH' WHERE email='heegyboanerges@gmail.com';"
echo "Password reset to: $PASS"
