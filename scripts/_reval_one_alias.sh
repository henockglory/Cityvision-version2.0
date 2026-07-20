#!/usr/bin/env bash
# Run one validate_rule alias under disk budget; then demo OFF + retention purge + fstrim.
set -uo pipefail
ALIAS="${1:?alias required}"
ROOT=/home/gheno/citevision-v2
cd "$ROOT"
export SKIP_FRIGATE_REBUILD=1
export FRIGATE_DEMO_RETENTION_MIN=30
export HOME=/home/gheno
export PATH="/usr/local/go/bin:$PATH"

disk_check() {
  local label="$1"
  C_G=$(df -P /mnt/c | awk 'NR==2 {printf "%d", $4/1024/1024}')
  FRIG_G=$(sudo du -s -BG /var/lib/docker/volumes/infra_frigate_recordings/_data 2>/dev/null | awk '{gsub(/G/,"",$1); print $1+0}')
  echo "DISK[$label] C_free=${C_G}G frigate_rec=${FRIG_G}G"
  if (( C_G < 40 )); then
    echo "ABORT: C: free ${C_G}G < 40G"
    exit 99
  fi
}

disk_check "before_$ALIAS"
C_BEFORE=$C_G

curl -sf http://127.0.0.1:8010/health >/dev/null || {
  set -a; source .env; set +a
  setsid nohup ./rules-engine/bin/rules-engine >> logs/rules-engine.log 2>&1 &
  echo $! > logs/rules-engine.pid
  sleep 2
}

set +e
stdbuf -oL -eL bash scripts/validate_rule.sh "$ALIAS" 2>&1 | tee "/tmp/reval_${ALIAS}.log"
VAL_EXIT=${PIPESTATUS[0]}
set -e

disk_check "after_$ALIAS"
C_AFTER=$C_G
DROP=$((C_BEFORE - C_AFTER))
if (( DROP > 25 )); then
  echo "ABORT: C: dropped ${DROP}G during $ALIAS"
  exit 99
fi

echo "=== demo rules OFF ==="
docker exec citevision-v2-postgres psql -U citevision -d citevision -c \
  "UPDATE rules SET is_enabled=false, updated_at=NOW() WHERE name LIKE 'Démo%';" || true

echo "=== retention purge + fstrim ==="
bash scripts/demo-retention-purge.sh || true
sudo fstrim -v / || true

python3 - <<PY
import json, re, pathlib
log = pathlib.Path("/tmp/reval_${ALIAS}.log").read_text(errors="replace")
m = re.search(r"ARTEFACT:\s*(\S+)", log)
art = m.group(1) if m else ""
result = "UNKNOWN"
alert = None
if art:
    rj = pathlib.Path(art) / "report.json"
    if rj.exists():
        d = json.loads(rj.read_text())
        result = d.get("result")
        alert = d.get("alert_id")
        print("REPORT", json.dumps({"result": result, "alert_id": alert, "out_dir": art}, indent=2))
print(f"SUMMARY alias=${ALIAS} val_exit=${VAL_EXIT} result={result} alert={alert} art={art}")
PY

exit "$VAL_EXIT"
