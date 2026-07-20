#!/bin/bash
set -e
cd ~/citevision-v2
echo "=== Restarting AI engine with CUDA ==="
bash scripts/restart-ai-engine.sh
echo "EXIT: $?"
