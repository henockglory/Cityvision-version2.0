#!/bin/bash
echo "=== AI ENGINE STATUS ==="
pgrep -f 'uvicorn citevision_ai' | head -3 || echo "NOT RUNNING"
echo "=== LAST AI LOG ERRORS ==="
grep -E 'ERROR|CRITICAL|Traceback|exception|killed' ~/citevision-v2/logs/ai-engine.log 2>/dev/null | tail -20
echo "=== AI HEALTH ==="
curl -sf http://127.0.0.1:8001/health 2>/dev/null || echo "UNREACHABLE"
echo "=== RULES-ENGINE STATUS ==="
pgrep -f 'rules-engine' | head -3 || echo "NOT RUNNING"
curl -sf http://127.0.0.1:8010/health 2>/dev/null || echo "UNREACHABLE"
