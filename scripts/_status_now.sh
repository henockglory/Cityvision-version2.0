#!/bin/bash
echo "=== $(date +%H:%M) ==="
echo "Processus:"
ps aux | grep -E 'pip install|restart-api|uvicorn|rules-engine|vite|ensure-ai' | grep -v grep | awk '{print " ",$9,$11,$12,$13,$14}' || echo "  (aucun install en cours)"
echo "Cache pip: $(du -sh ~/.cache/pip 2>/dev/null | cut -f1)"
echo ""
echo "Services:"
curl -sf http://localhost:8081/health >/dev/null && echo "  Backend  : OK" || echo "  Backend  : DOWN"
if curl -sf http://localhost:8001/health -o /tmp/ai_h.json 2>/dev/null; then
  python3 -c "import json; d=json.load(open('/tmp/ai_h.json')); print('  AI       : OK | yolo_cuda='+str(d.get('yolo_cuda'))+' plate='+str(d.get('plate_loaded'))+' face='+str(d.get('face_loaded')))"
else
  echo "  AI       : DOWN"
fi
curl -sf http://localhost:8010/health >/dev/null && echo "  Rules    : OK" || echo "  Rules    : DOWN"
code=$(curl -sf -o /dev/null -w '%{http_code}' http://localhost:5174/ 2>/dev/null); echo "  Frontend : HTTP $code"
echo ""
echo "Docker:"
docker ps --format '  {{.Names}}: {{.Status}}' 2>/dev/null | head -6
