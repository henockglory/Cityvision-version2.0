#!/bin/bash
pkill -9 -f 'uvicorn citevision_ai' 2>/dev/null || true
sleep 3
cd ~/citevision-v2
PYTHON=ai-engine/.venv/bin/python3
nohup $PYTHON -m uvicorn citevision_ai.main:app --host 0.0.0.0 --port 8001 --workers 1 \
    >> logs/ai-engine.log 2>&1 &
PID=$!
echo $PID > logs/ai-engine.pid
echo "Started AI PID=$PID"
sleep 5
for i in $(seq 1 30); do
    if curl -sf http://127.0.0.1:8001/health >/dev/null 2>&1; then
        echo "[OK] AI healthy"
        break
    fi
    sleep 3
done
