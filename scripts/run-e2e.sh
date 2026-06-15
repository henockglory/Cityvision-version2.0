#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT/frontend"

export PLAYWRIGHT_BASE_URL="${PLAYWRIGHT_BASE_URL:-http://localhost:5174}"
export DEMO_EMAIL="${DEMO_EMAIL:-glory.henock@hologram.cd}"
export DEMO_PASS="${DEMO_PASS:-Hologram2026!}"

npx playwright test e2e/demo-commercial.spec.ts --reporter=line
