#!/bin/bash
for i in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20 21 22 23 24 25; do
    if curl -sf --max-time 5 http://127.0.0.1:8001/health >/dev/null 2>&1; then
        echo "[OK] AI UP"
        curl -sf http://127.0.0.1:8001/health 2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin); print('yolo='+d.get('yolo_loaded','?')+' cuda='+d.get('yolo_cuda','?')+' evidence_backend='+str(d.get('evidence_backend','?')))"
        exit 0
    fi
    echo "  wait $i/25..."
    sleep 4
done
echo "TIMEOUT: AI not healthy"
exit 1
