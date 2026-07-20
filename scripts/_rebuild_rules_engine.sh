#!/bin/bash
set -e
export PATH=$PATH:/usr/local/go/bin:/home/gheno/go/bin
cd ~/citevision-v2/rules-engine
echo "Building rules-engine..."
go build -o bin/rules-engine ./cmd/rules-engine/
echo "Build OK"
# Restart the rules-engine process
cd ~/citevision-v2
if [ -f logs/rules-engine.pid ]; then
  pid=$(cat logs/rules-engine.pid)
  kill "$pid" 2>/dev/null && echo "Stopped old rules-engine (pid=$pid)" || true
  sleep 2
fi
nohup bin/rules-engine/rules-engine > logs/rules-engine.log 2>&1 &
echo $! > logs/rules-engine.pid
echo "Rules-engine restarted (pid=$!)"
sleep 3
curl -sf http://localhost:8010/health | python3 -c "import sys,json; d=json.load(sys.stdin); print('health:', d)" 2>/dev/null || echo "health check failed"
