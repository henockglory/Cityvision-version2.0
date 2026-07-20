#!/usr/bin/env bash
# Tail red_light abort / suppress signals while validate runs
ROOT=/home/gheno/citevision-v2
echo "=== OCR ==="
curl -sf http://127.0.0.1:8181/healthz; echo
echo "=== AI env OCR_URL ==="
tr '\0' '\n' < /proc/$(pgrep -f 'uvicorn citevision_ai.main' | head -1)/environ 2>/dev/null | grep -E 'OCR|FRIGATE' || true
grep -E 'OCR_URL|FRIGATE' "$ROOT/.env" | head -10
echo "=== recent aborts in ai log ==="
# ai-engine.log may be binary-ish; use strings
strings "$ROOT/logs/ai-engine.log" 2>/dev/null | grep -E 'abort|red_light|incomplete|IoU|no_correlation|missing_roles|plate|suppressed' | tail -40
echo "=== rules engine log ==="
strings "$ROOT/logs/rules-engine.log" 2>/dev/null | grep -E 'suppress|Feu|incomplete|evidence' | tail -20
