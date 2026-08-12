#!/usr/bin/env bash
# One-shot: strip plate from active face/cabin rule evidence when the template
# contract does not want plate. Also seed face/reference roles for watchlist.
set -uo pipefail
ROOT="${CITEVISION_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
API="${BACKEND_API_URL:-http://127.0.0.1:8081}"
PG_CONTAINER="${POSTGRES_CONTAINER:-citevision-v2-postgres}"
PG_USER="${POSTGRES_USER:-citevision}"
PG_DB="${POSTGRES_DB:-citevision}"

# shellcheck source=scripts/lib/env-utils.sh
source "$ROOT/scripts/lib/env-utils.sh" 2>/dev/null || true
load_dotenv "${ENV_FILE:-$ROOT/.env}" 2>/dev/null || true

CONTRACT="$ROOT/shared/rule-orchestration-contract.json"
if [[ ! -f "$CONTRACT" ]]; then
  echo "[FAIL] missing $CONTRACT"
  exit 1
fi

python3 - <<'PY' "$CONTRACT" "$PG_CONTAINER" "$PG_USER" "$PG_DB"
import json, subprocess, sys

contract_path, pg_c, pg_user, pg_db = sys.argv[1:5]
with open(contract_path, encoding="utf-8") as f:
    contract = json.load(f)
tpl_map = {t["id"]: t for t in contract.get("templates") or [] if t.get("id")}

FACE_CABIN = {
    tid for tid, t in tpl_map.items()
    if str(t.get("archetype") or "").lower() in ("face", "cabin")
}

q = "SELECT id::text, definition::text FROM rules WHERE is_enabled = true;"
proc = subprocess.run(
    ["docker", "exec", "-i", pg_c, "psql", "-U", pg_user, "-d", pg_db, "-At", "-c", q],
    capture_output=True, text=True,
)
if proc.returncode != 0:
    print("[FAIL] psql:", proc.stderr.strip() or proc.stdout.strip())
    sys.exit(1)

updated = 0
for line in proc.stdout.splitlines():
    if "|" not in line:
        continue
    rid, raw = line.split("|", 1)
    try:
        definition = json.loads(raw)
    except Exception:
        continue
    bindings = definition.get("bindings") or {}
    tpl_id = str(bindings.get("template_id") or "")
    if tpl_id not in FACE_CABIN:
        continue
    tpl = tpl_map.get(tpl_id) or {}
    desired = (tpl.get("evidence_policy") or {})
    evidence = definition.get("evidence") or {}
    images = list(evidence.get("images") or [])
    roles = [str(i.get("role") or "").lower() for i in images if isinstance(i, dict)]
    changed = False
    # Strip plate from face/cabin
    if "plate" in roles:
        images = [i for i in images if str(i.get("role") or "").lower() != "plate"]
        changed = True
    # Seed contract images when empty or polluted
    want_images = desired.get("images") or []
    if want_images and (not images or set(roles) - {"scene", "subject", "face", "reference"}):
        images = list(want_images)
        changed = True
    if desired:
        for key in ("clip_seconds", "enabled", "fail_closed"):
            if key in desired and evidence.get(key) != desired.get(key):
                evidence[key] = desired[key]
                changed = True
    if not changed:
        continue
    evidence["images"] = images
    definition["evidence"] = evidence
    new_json = json.dumps(definition, ensure_ascii=False).replace("'", "''")
    upd = f"UPDATE rules SET definition = '{new_json}'::jsonb WHERE id = '{rid}'::uuid;"
    u = subprocess.run(
        ["docker", "exec", "-i", pg_c, "psql", "-U", pg_user, "-d", pg_db, "-c", upd],
        capture_output=True, text=True,
    )
    if u.returncode == 0:
        updated += 1
        print(f"[OK] repaired rule {rid} template={tpl_id}")
    else:
        print(f"[WARN] failed rule {rid}: {u.stderr.strip()}")

print(f"[DONE] repaired={updated}")
PY
