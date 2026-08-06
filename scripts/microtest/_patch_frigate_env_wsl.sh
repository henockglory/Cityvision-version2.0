#!/usr/bin/env bash
set -euo pipefail
ROOT="${MICROTEST_ROOT:-$HOME/citevision-v2}"
cd "$ROOT"
cp /mnt/c/Users/gheno/citevision/scripts/microtest/_microtest_common.sh scripts/microtest/
export DEMO_ORG_ID="${DEMO_ORG_ID:-74d51ead-97a7-4e41-a488-503a9b90c466}"
source scripts/microtest/_microtest_common.sh
patch_env_kv
grep -E '^(FRIGATE_ENABLED|FRIGATE_CONFIG_SYNC|DEFAULT_ORG_ID)=' .env
