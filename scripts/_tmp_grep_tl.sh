#!/usr/bin/env bash
set -uo pipefail
ROOT=/home/gheno/citevision-v2
grep -E 'traffic_light|red_light_violation|abort red_light|scene lamp' "$ROOT/logs/ai-engine.log" | tail -30 || true
echo "violation_count=$(grep -c red_light_violation "$ROOT/logs/ai-engine.log" 2>/dev/null || echo 0)"
echo "abort_count=$(grep -c 'abort red_light' "$ROOT/logs/ai-engine.log" 2>/dev/null || echo 0)"
