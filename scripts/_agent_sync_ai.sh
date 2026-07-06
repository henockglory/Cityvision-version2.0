#!/usr/bin/env bash
set -uo pipefail
W=/mnt/c/Users/gheno/citevision
R="$HOME/citevision-v2"
for f in ai-engine/src/citevision_ai/utils/paddle_ocr_compat.py ai-engine/src/citevision_ai/identity/plate.py; do
  cp "$W/$f" "$R/$f"
  sed -i 's/\r$//' "$R/$f"
done
echo SYNCED
sed 's/\r$//' "$W/scripts/_agent_ops.sh" > /tmp/o.sh
bash /tmp/o.sh start-ai 2>&1 | tail -3
