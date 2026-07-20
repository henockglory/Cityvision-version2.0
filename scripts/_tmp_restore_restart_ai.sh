#!/usr/bin/env bash
set -uo pipefail
ROOT=/home/gheno/citevision-v2
python3 /mnt/c/Users/gheno/citevision/scripts/_tmp_restore_ai_files.py || exit 1
bash "$ROOT/scripts/restart-ai-engine.sh"
for i in $(seq 1 90); do
  if curl -sf --max-time 3 http://127.0.0.1:8001/health >/dev/null; then
    echo AI_UP
    break
  fi
  sleep 2
done
curl -sf --max-time 5 http://127.0.0.1:8001/health | head -c 200; echo
curl -sf --max-time 3 -o /dev/null -w "UI %{http_code}\n" http://127.0.0.1:5174/ || echo UI_DOWN
curl -sf --max-time 3 http://127.0.0.1:8081/health >/dev/null && echo BE_OK || {
  echo BE_DOWN
  source "$ROOT/scripts/lib/env-utils.sh"
  ENV_FILE="$(ensure_env_file "$ROOT")"
  load_dotenv "$ENV_FILE"
  free_port 8081 || true
  start_bg backend "$ROOT/backend" "$ROOT/backend/bin/citevision-api" "$ROOT/logs" "$ENV_FILE"
  wait_http_ok http://127.0.0.1:8081/health 60 || true
}
curl -sf --max-time 3 http://127.0.0.1:8081/health >/dev/null && echo BE_OK || echo BE_STILL_DOWN
if ! curl -sf --max-time 3 http://127.0.0.1:8001/health >/dev/null; then
  echo AI_STILL_DOWN
  tail -25 "$ROOT/logs/ai-engine.log"
fi
