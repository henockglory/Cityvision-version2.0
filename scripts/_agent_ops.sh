#!/usr/bin/env bash
# Temporary agent operations helper (Phase A boot). Safe: no DB geometry writes.
# Usage: bash _agent_ops.sh <task>
set -uo pipefail
export PATH="$PATH:/usr/local/go/bin"
WIN=/mnt/c/Users/gheno/citevision
RUNTIME=~/citevision-v2
cd "$RUNTIME" || exit 1

task="${1:-help}"

sync_file() {
  # sync_file <relpath>
  local rel="$1"
  mkdir -p "$(dirname "$RUNTIME/$rel")"
  cp "$WIN/$rel" "$RUNTIME/$rel"
  sed -i 's/\r$//' "$RUNTIME/$rel" 2>/dev/null || true
}

case "$task" in
  build-seed)
    sync_file backend/cmd/seed-demo-spatial/main.go
    (cd backend && go build -o bin/seed-demo-spatial ./cmd/seed-demo-spatial/ && echo BUILD_OK)
    ;;
  build-backend)
    (cd backend && go build -o bin/citevision-api ./cmd/api && echo BACKEND_BUILD_OK)
    ;;
  build-rules)
    (cd rules-engine && go build -o bin/rules-engine ./cmd/rules-engine && echo RULES_BUILD_OK)
    ;;
  health)
    echo "--- backend :8081 ---"; curl -sf http://localhost:8081/health && echo " OK" || echo " DOWN"
    echo "--- ai :8001 ---"; curl -sf http://localhost:8001/health || echo " DOWN"
    echo ""
    echo "--- rules :8010 ---"; curl -sf http://localhost:8010/health && echo " OK" || echo " DOWN"
    echo "--- frontend :5174 ---"; curl -s -o /dev/null -w "HTTP %{http_code}\n" http://localhost:5174/ || echo " DOWN"
    ;;
  ps)
    docker ps --format '{{.Names}}: {{.Status}}'
    ;;
  seed-spatial)
    PGPASS="$(docker inspect citevision-v2-postgres --format '{{range .Config.Env}}{{println .}}{{end}}' | sed -n 's/^POSTGRES_PASSWORD=//p')"
    export DATABASE_URL="postgres://citevision:${PGPASS}@localhost:5433/citevision?sslmode=disable"
    ./backend/bin/seed-demo-spatial
    ;;
  seed-rules)
    sync_file backend/cmd/seed-demo-rules/main.go
    (cd backend && go build -o bin/seed-demo-rules ./cmd/seed-demo-rules/) || exit 1
    PGPASS="$(docker inspect citevision-v2-postgres --format '{{range .Config.Env}}{{println .}}{{end}}' | sed -n 's/^POSTGRES_PASSWORD=//p')"
    export DATABASE_URL="postgres://citevision:${PGPASS}@localhost:5433/citevision?sslmode=disable"
    export DEMO_RULES_ENABLED="${DEMO_RULES_ENABLED:-0}"
    ./backend/bin/seed-demo-rules
    ;;
  db-probe)
    docker exec -i citevision-v2-postgres psql -U citevision -d citevision -f - < "$WIN/scripts/_agent_db_probe.sql"
    ;;
  sync-code)
    sync_file ai-engine/src/citevision_ai/face/insightface_module.py
    sync_file ai-engine/src/citevision_ai/identity/face.py
    sync_file scripts/validate_demo_five_rules.py
    echo SYNCED
    ;;
  start-ai)
    source scripts/lib/env-utils.sh
    source scripts/lib/cuda-utils.sh 2>/dev/null || true
    ENV_FILE="$(ensure_env_file "$PWD")"
    stop_from_pid logs/ai-engine.pid 2>/dev/null || true
    pkill -f 'uvicorn citevision_ai.main' 2>/dev/null || true
    sleep 2
    export AI_SKIP_VERIFY="${AI_SKIP_VERIFY:-1}"
    start_bg ai-engine "$PWD" "bash scripts/run-ai-engine.sh" logs "$ENV_FILE"
    echo "AI starting (log: logs/ai-engine.log)"
    ;;
  start-backend)
    source scripts/lib/env-utils.sh
    ENV_FILE="$(ensure_env_file "$PWD")"
    (cd backend && go build -o bin/citevision-api ./cmd/api) && echo BACKEND_BUILT
    stop_from_pid logs/backend.pid 2>/dev/null || true
    free_port 8081 2>/dev/null || true
    sleep 1
    start_bg backend "$PWD/backend" "$PWD/backend/bin/citevision-api" "$PWD/logs" "$ENV_FILE"
    ;;
  start-rules)
    source scripts/lib/env-utils.sh
    ENV_FILE="$(ensure_env_file "$PWD")"
    (cd rules-engine && go build -o bin/rules-engine ./cmd/rules-engine) && echo RULES_BUILT
    stop_from_pid logs/rules-engine.pid 2>/dev/null || true
    free_port 8010 2>/dev/null || true
    sleep 1
    start_bg rules-engine "$PWD/rules-engine" "$PWD/rules-engine/bin/rules-engine" "$PWD/logs" "$ENV_FILE"
    ;;
  start-frontend)
    source scripts/lib/env-utils.sh
    ensure_frontend_deps "$PWD" || true
    stop_from_pid logs/frontend.pid 2>/dev/null || true
    free_port 5174 2>/dev/null || true
    sleep 1
    start_bg frontend "$PWD/frontend" "npm run dev -- --host 0.0.0.0 --port 5174" "$PWD/logs" ""
    ;;
  verify-ai)
    source scripts/lib/cuda-utils.sh 2>/dev/null || true
    VENV_PY="$PWD/ai-engine/.venv/bin/python3"
    setup_cuda_library_path "$VENV_PY" 2>/dev/null || true
    "$VENV_PY" ai-engine/scripts/verify_ai_stack.py --device cuda 2>&1 | tail -30
    ;;
  ai-cameras)
    curl -sf http://localhost:8001/cameras 2>/dev/null | python3 -m json.tool 2>/dev/null | head -80 || echo 'no cameras endpoint'
    ;;
  psql)
    shift
    docker exec -i citevision-v2-postgres psql -U citevision -d citevision -c "$*"
    ;;
  demo-all)
    docker exec -i citevision-v2-postgres psql -U citevision -d citevision -c "UPDATE org_demo_settings SET active_video_id=NULL, active_camera_id=NULL, source_mode='video', updated_at=NOW();"
    ;;
  rules-enable)
    docker exec -i citevision-v2-postgres psql -U citevision -d citevision -c "UPDATE rules SET is_enabled=true, updated_at=NOW() WHERE name LIKE 'Démo%';"
    ;;
  rules-disable)
    docker exec -i citevision-v2-postgres psql -U citevision -d citevision -c "UPDATE rules SET is_enabled=false, updated_at=NOW() WHERE name LIKE 'Démo%';"
    ;;
  results)
    docker exec -i citevision-v2-postgres psql -U citevision -d citevision -f - < "$WIN/scripts/_agent_results.sql"
    ;;
  mailcount)
    curl -sf http://localhost:8025/api/v2/messages?limit=1 2>/dev/null | python3 -c "import sys,json;print('mails=',json.load(sys.stdin).get('total',0))" 2>/dev/null || echo 'mailhog?'
    ;;
  ailog)
    tail -n "${2:-40}" logs/ai-engine.log 2>/dev/null || echo 'no ai log'
    ;;
  log)
    tail -n "${3:-40}" "logs/${2:-backend}.log" 2>/dev/null || echo "no log ${2:-backend}"
    ;;
  *)
    echo "unknown task: $task"; exit 2;;
esac
