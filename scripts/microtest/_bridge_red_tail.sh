#!/usr/bin/env bash
grep -E 'SHADOW|GEMINI_SHADOW|RED_LIGHT_VOTE' /home/gheno/citevision-v2/.env || true
echo '--- recent bridge red ---'
grep 'frigate_bridge red_light' /home/gheno/citevision-v2/logs/ai-engine.log | tail -20
