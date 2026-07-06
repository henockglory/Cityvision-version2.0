#!/bin/bash
set -e
cd ~/citevision-v2
export PATH="$PATH:/usr/local/go/bin"

find scripts -name '*.sh' -exec sed -i 's/\r$//' {} + 2>/dev/null || true

if ! docker info >/dev/null 2>&1; then
  sudo nohup dockerd > /tmp/dockerd.log 2>&1 &
  sleep 4
fi

echo "=== Attente fin setup-wsl ==="
while pgrep -f 'scripts/setup-wsl.sh' >/dev/null 2>&1; do
  echo "$(date +%H:%M:%S) setup en cours (pip torch/modèles)..."
  sleep 60
done
echo "Setup terminé."

echo "=== Démarrage stack ==="
bash scripts/start-linux.sh 2>&1 | tee logs/start-linux.log

echo "=== Health ==="
curl -sf http://localhost:8081/health && echo " backend OK" || echo " backend FAIL"
curl -sf http://localhost:8001/health && echo " AI OK" || echo " AI FAIL"
curl -sf http://localhost:8010/health && echo " rules OK" || echo " rules FAIL"
curl -sf -o /dev/null -w "%{http_code}" http://localhost:5174/ && echo " frontend OK" || echo " frontend FAIL"
