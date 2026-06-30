#!/usr/bin/env bash
strings ~/citevision-v2/logs/rules-engine.log | grep '2026/06/30 05:43' | head -10
echo "--- feux spatial ---"
curl -sf http://127.0.0.1:8001/cameras/726ff8a1-8442-4bdb-96ad-ec40a2fbb424/spatial | python3 -m json.tool 2>/dev/null | head -15
