#!/usr/bin/env bash
# Rebuild backend/bin/citevision-api when Frigate Go sources are newer than the binary.
# Used by start-full-stack [4/10] and watch-backend (even when API /health is up).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BIN="$ROOT/backend/bin/citevision-api"
SRCS=(
  "$ROOT/backend/internal/frigate/compiler.go"
  "$ROOT/backend/internal/frigate/detect_gate.go"
  "$ROOT/backend/internal/frigate/sync.go"
  "$ROOT/backend/internal/health/platform.go"
  "$ROOT/backend/cmd/api/main.go"
)

need=0
if [[ ! -x "$BIN" ]]; then
  need=1
else
  bin_m=$(stat -c %Y "$BIN" 2>/dev/null || echo 0)
  for s in "${SRCS[@]}"; do
    [[ -f "$s" ]] || continue
    src_m=$(stat -c %Y "$s" 2>/dev/null || echo 0)
    if [[ "$src_m" -gt "$bin_m" ]]; then
      need=1
      break
    fi
  done
fi

if [[ "$need" -eq 0 ]]; then
  echo "[OK] backend binary current"
  exit 0
fi

export PATH="${PATH:-}:/usr/local/go/bin:/home/gheno/go/bin"
GO_BIN="$(command -v go || true)"
if [[ -z "$GO_BIN" && -x /usr/local/go/bin/go ]]; then
  GO_BIN=/usr/local/go/bin/go
fi
if [[ -z "$GO_BIN" ]]; then
  echo "[WARN] go not found — cannot rebuild citevision-api" >&2
  exit 1
fi

echo "[INFO] rebuilding backend/bin/citevision-api (Frigate Go sources newer)"
mkdir -p "$ROOT/backend/bin"
if (cd "$ROOT/backend" && "$GO_BIN" build -o "$BIN" ./cmd/api); then
  echo "[OK] backend rebuilt"
  exit 0
fi
echo "[FAIL] go build citevision-api" >&2
exit 1
