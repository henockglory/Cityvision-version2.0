#!/bin/bash
echo "=== VALIDATION RUNNING ==="
pgrep -f 'validate_demo|_run_five_rules' | head -5 || echo "none"
echo "=== AI ENGINE ==="
pgrep -fa 'uvicorn citevision_ai' | head -2 || echo "NOT RUNNING"
curl -sf --max-time 5 http://127.0.0.1:8001/health 2>/dev/null | python3 -c "
import sys,json
d=json.load(sys.stdin)
print('AI OK yolo='+str(d.get('yolo_loaded'))+ ' cuda='+str(d.get('yolo_cuda')))
" 2>/dev/null || echo "AI DOWN"
echo "=== RULES ENGINE ==="
curl -sf http://127.0.0.1:8010/health 2>/dev/null || echo "RULES DOWN"
echo "=== LATEST LOG ==="
ls -t ~/citevision-v2/logs/demo-five-rules-gated-*.log 2>/dev/null | head -1
echo "=== LAST 5 LINES ==="
tail -5 $(ls -t ~/citevision-v2/logs/demo-five-rules-gated-*.log 2>/dev/null | head -1) 2>/dev/null
echo "=== OOM SINCE BOOT ==="
dmesg 2>/dev/null | grep -c 'Out of memory' || echo 0
echo "=== RAM ==="
free -m | grep Mem
