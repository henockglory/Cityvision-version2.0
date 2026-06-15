#!/usr/bin/env bash
set -euo pipefail
PASS="${1:-Hologram2026!}"
EMAIL="${2:-glory.henock@hologram.cd}"
HASH=$(cd ~/citevision-v2/backend && /usr/local/go/bin/go run ./cmd/hashpw "$PASS")
docker exec citevision-v2-postgres psql -U citevision -d citevision -c "UPDATE users SET password_hash='$HASH' WHERE email='$EMAIL';"
echo "Password for $EMAIL reset to: $PASS"
