#!/usr/bin/env bash
# Phase F — IA incidents vidéo (flou / obscurité)
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
PY="$ROOT/ai-engine/.venv/bin/python3"
[[ -x "$PY" ]] || PY=python3

echo "=== verify-video-incidents ==="
"$PY" -m pytest -q ai-engine/tests/test_video_quality.py --tb=line
echo "=== verify-video-incidents OK ==="
