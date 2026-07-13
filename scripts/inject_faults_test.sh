#!/usr/bin/env bash
# Inject known fault patterns and verify supervisor/health recovery (smoke test).
set -euo pipefail
BACKEND="${BACKEND_API_URL:-http://127.0.0.1:8081}"
KEY="${INTERNAL_API_KEY:-}"
HDR=()
[ -n "$KEY" ] && HDR=(-H "X-Internal-Key: $KEY")

PASS=0
TOTAL=10

check_health() {
  curl -sf "$BACKEND/health/platform" | python3 -c "import sys,json; s=json.load(sys.stdin).get('status'); sys.exit(0 if s in ('ok','degraded') else 1)"
}

# 1-3: rules sync repair
for i in 1 2 3; do
  curl -sf -X POST "${HDR[@]}" "$BACKEND/api/v1/internal/supervisor/repair?issue=rules_engine" >/dev/null && PASS=$((PASS+1)) || true
done

# 4-5: spatial resync
for i in 1 2; do
  curl -sf -X POST "${HDR[@]}" "$BACKEND/api/v1/internal/supervisor/repair?issue=ai_engine" >/dev/null && PASS=$((PASS+1)) || true
done

# 6-7: frigate rebuild
for i in 1 2; do
  curl -sf -X POST "${HDR[@]}" "$BACKEND/api/v1/internal/supervisor/repair?issue=frigate" >/dev/null && PASS=$((PASS+1)) || true
done

# 8-9: health still reachable
check_health && PASS=$((PASS+1)) || true
check_health && PASS=$((PASS+1)) || true

# 10: backend liveness
curl -sf "$BACKEND/health" >/dev/null && PASS=$((PASS+1)) || true

echo "Recovery smoke: $PASS/$TOTAL"
[ "$PASS" -ge 9 ] && exit 0
exit 1
