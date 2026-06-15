#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export PATH="$PATH:/usr/local/go/bin"
# shellcheck source=scripts/lib/env-utils.sh
source "$ROOT/scripts/lib/env-utils.sh"

FAIL=0
pass() { echo "[PASS] $1"; }
fail() { echo "[FAIL] $1"; FAIL=$((FAIL + 1)); }

echo "=== Citevision v2 Doctor (Linux/WSL) ==="
echo ""

if grep -qi microsoft /proc/version 2>/dev/null; then
  pass "Running under WSL"
else
  echo "[INFO] Native Linux (not WSL)"
fi

command -v docker >/dev/null && pass "docker CLI" || fail "docker CLI missing"
if command -v docker >/dev/null; then
  docker info >/dev/null 2>&1 && pass "docker daemon" || fail "docker daemon not running (sudo service docker start)"
fi

command -v go >/dev/null && pass "go" || fail "go missing"
command -v node >/dev/null && pass "node" || fail "node missing"
command -v python3 >/dev/null && pass "python3" || fail "python3 missing"
if command -v nvidia-smi >/dev/null 2>&1; then
  pass "nvidia-smi (GPU)"
  nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null | head -1 || true
else
  echo "[WARN] nvidia-smi missing — CUDA unavailable for AI"
fi
command -v ffmpeg >/dev/null && pass "ffmpeg" || echo "[WARN] ffmpeg missing (camera RTSP test)"

for port in 5433 6380 1884 8554 9003 1984 8081 8001 8010 5174; do
  if ss -tln 2>/dev/null | grep -q ":$port " || netstat -tln 2>/dev/null | grep -q ":$port "; then
    echo "[WARN] Port $port in use"
  else
    pass "Port $port free"
  fi
done

vite_count=0
for port in 5174 5175 5176 5177; do
  if ss -tln 2>/dev/null | grep -q ":$port " || netstat -tln 2>/dev/null | grep -q ":$port "; then
    vite_count=$((vite_count + 1))
  fi
done
if (( vite_count > 1 )); then
  fail "Multiple Vite ports in use (5174-5177) — run bash scripts/stop-linux.sh"
elif (( vite_count == 1 )); then
  pass "Single Vite dev server on 517x"
fi

if [[ -f .env ]]; then
  load_dotenv .env
  [[ -n "${JWT_SECRET:-}" && ${#JWT_SECRET} -ge 16 ]] && pass "JWT_SECRET" || fail "JWT_SECRET"
  [[ -n "${CAMERA_CREDENTIAL_KEY:-}" && ${#CAMERA_CREDENTIAL_KEY} -ge 32 ]] && pass "CAMERA_CREDENTIAL_KEY" || fail "CAMERA_CREDENTIAL_KEY"
else
  fail ".env missing (run start-linux.sh)"
fi

CAM_IP="${CAMERA_TEST_IP:-${TEST_CAMERA_IP:-}}"
if [[ -n "$CAM_IP" ]]; then
  ping -c 1 -W 2 "$CAM_IP" >/dev/null 2>&1 && pass "Camera ping $CAM_IP" || fail "Camera ping $CAM_IP"
else
  echo "[INFO] CAMERA_TEST_IP not set"
fi

for f in backend/go.mod frontend/package.json infra/docker-compose.yml; do
  [[ -f "$f" ]] && pass "$f" || fail "$f"
done

echo ""
echo "FAIL=$FAIL"
exit "$FAIL"
