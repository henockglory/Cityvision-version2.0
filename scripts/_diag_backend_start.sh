#!/usr/bin/env bash
set -uo pipefail
cd ~/citevision-v2
echo "=== backend log tail ==="
tail -100 logs/backend.log || echo "no log"
echo
echo "=== listening 8081 ==="
ss -lptn 'sport = :8081' || true
echo
echo "=== binary ==="
ls -la backend/bin/citevision-api
file backend/bin/citevision-api
echo
echo "=== try start foreground briefly ==="
export PATH="/usr/local/go/bin:/home/gheno/go/bin:${PATH:-}"
# Load .env like the normal start
if [[ -f scripts/lib/env-utils.sh ]]; then
  # shellcheck disable=SC1091
  source scripts/lib/env-utils.sh
  ENV_FILE="$(ensure_env_file "$PWD")"
  load_dotenv "$ENV_FILE"
fi
timeout 8 ./backend/bin/citevision-api 2>&1 | tail -50 || true
