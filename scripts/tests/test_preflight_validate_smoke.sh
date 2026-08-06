#!/usr/bin/env bash
# Smoke: preflight-validate and env-utils source without syntax errors.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
bash -n "$ROOT/scripts/preflight-validate.sh"
bash -n "$ROOT/scripts/lib/service-heal.sh"
bash -n "$ROOT/scripts/ensure-demo-validation-env.sh"
bash -n "$ROOT/scripts/lib/env-utils.sh"
echo "[OK] preflight-validate smoke (syntax)"
