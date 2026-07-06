#!/bin/bash
# Surveille l'installation en cours — ne rien couper
echo "=== $(date +%H:%M:%S) État installation ==="
echo "GPU:"
nvidia-smi --query-gpu=name,memory.used,memory.total --format=csv,noheader 2>/dev/null || echo "  nvidia-smi indisponible"
echo ""
echo "Processus actifs:"
ps aux | grep -E 'pip install|restart-api|ensure-ai|setup-wsl' | grep -v grep | awk '{print "  "$11" "$12" "$13" "$14}'
echo ""
echo "Cache pip: $(du -sh ~/.cache/pip 2>/dev/null | cut -f1)"
echo ""
echo "Services:"
curl -sf http://localhost:8081/health >/dev/null && echo "  Backend  : OK" || echo "  Backend  : --"
curl -sf http://localhost:8001/health >/dev/null && echo "  AI       : OK" || echo "  AI       : en attente (install)"
curl -sf http://localhost:8010/health >/dev/null && echo "  Rules    : OK" || echo "  Rules    : --"
curl -sf -o /dev/null http://localhost:5174/ 2>/dev/null && echo "  Frontend : OK" || echo "  Frontend : --"
echo ""
if pgrep -f 'pip install.*torch' >/dev/null; then
  echo ">>> PyTorch CUDA en téléchargement — ne pas interrompre"
  echo ">>> Estimation: 15-45 min selon débit réseau, puis modèles YOLO/PaddleOCR/InsightFace"
elif pgrep -f 'restart-api-frontend' >/dev/null; then
  echo ">>> restart-api-frontend en cours (après PyTorch)"
else
  echo ">>> Installation terminée ou en pause — vérifier logs/"
fi
