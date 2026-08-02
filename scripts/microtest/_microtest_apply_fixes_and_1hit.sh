#!/usr/bin/env bash
# Post-diagnostic: apply Gemini fix, spatial diagnostic, optional spatial reload,
# HSV reprobe with warm-start, then 1-hit feu if green.
# Usage: cd ~/citevision-v2 && bash scripts/microtest/_microtest_apply_fixes_and_1hit.sh
set -uo pipefail

REPO_ROOT="${MICROTEST_ROOT:-$HOME/citevision-v2}"
cd "$REPO_ROOT" || { echo "[FATAL] repo introuvable: $REPO_ROOT"; exit 1; }

source "$REPO_ROOT/scripts/microtest/_microtest_common.sh"
PY="$(microtest_python)"

TS="$(date -u +%Y%m%dT%H%M%SZ)"
OUT_DIR="$REPO_ROOT/docs/microtest-fix-$TS"
WIN_OUT="/mnt/c/Users/gheno/citevision/docs/microtest-fix-$TS"
mkdir -p "$OUT_DIR"
mkdir -p "$WIN_OUT" 2>/dev/null || true
REPORT="$OUT_DIR/final-fix-report.md"
cp_target() { cp -f "$1" "$WIN_OUT/$(basename "$1")" 2>/dev/null || true; }

log() { echo "[$(date -u +%H:%M:%S)] $*" | tee -a "$OUT_DIR/final-fix.raw.log"; }

TARGET_GEMINI="${MICROTEST_GEMINI_MODEL:-gemini-3.1-flash-lite}"
PROCEED_E=0

echo "# Final fix report — $TS" > "$REPORT"
echo "" >> "$REPORT"

ensure_stack

if [ -f "$REPO_ROOT/scripts/lib/env-utils.sh" ]; then
  # shellcheck source=scripts/lib/env-utils.sh
  source "$REPO_ROOT/scripts/lib/env-utils.sh"
  load_dotenv "$(ensure_env_file "$REPO_ROOT")"
fi

# ===========================================================================
# ÉTAPE A — Gemini (auto)
# ===========================================================================
log "== ÉTAPE A : fix modèle Gemini =="
echo "## A. Fix modèle Gemini" >> "$REPORT"

CURRENT_MODEL="$(resolve_gemini_model)"
HEALTH_MODEL="$("$PY" -c "
import json, urllib.request
try:
    h=json.load(urllib.request.urlopen('http://127.0.0.1:8001/health', timeout=8))
    print(h.get('gemini_model') or '')
except Exception:
    print('')
")"
[ -n "$HEALTH_MODEL" ] && CURRENT_MODEL="$HEALTH_MODEL"
log "Modèle actuel : $CURRENT_MODEL"

if [ "$CURRENT_MODEL" = "$TARGET_GEMINI" ]; then
  echo "- **Statut** : déjà \`$TARGET_GEMINI\`" >> "$REPORT"
  GEMINI_OK=1
else
  GEMINI_FIX_JSON="$OUT_DIR/gemini-fix-result.json"
  "$PY" - "$CURRENT_MODEL" "$GEMINI_FIX_JSON" "$TARGET_GEMINI" <<'PYEOF'
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

configured, out_path, target = sys.argv[1], Path(sys.argv[2]), sys.argv[3]
root = Path.home() / "citevision-v2"
env = {}
for line in (root / ".env").read_text(encoding="utf-8").splitlines() if (root / ".env").exists() else []:
    if not line.strip() or line.lstrip().startswith("#") or "=" not in line:
        continue
    k, v = line.split("=", 1)
    env[k.strip()] = v.strip().strip('"').strip("'")
key = (os.environ.get("GEMINI_API_KEY") or env.get("GEMINI_API_KEY") or "").strip()
result = {"configured": configured, "target": target, "status": "blocked"}

def smoke(api_key, model):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    body = json.dumps({"contents": [{"parts": [{"text": "ok"}]}]}).encode()
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            json.load(r)
        return True
    except Exception:
        return False

if not key:
    result["reason"] = "GEMINI_API_KEY missing"
else:
    ok_target = smoke(key, target)
    ok_current = smoke(key, configured) if configured else False
    if ok_target:
        result["chosen"] = target
        result["status"] = "fix_proposed"
    elif ok_current:
        result["chosen"] = configured
        result["status"] = "ok"
    else:
        result["status"] = "blocked"
        result["reason"] = f"neither {configured} nor {target} pass generateContent"

out_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
print(json.dumps(result))
PYEOF

  GEMINI_STATUS="$("$PY" -c "import json; print(json.load(open('$GEMINI_FIX_JSON'))['status'])")"
  GEMINI_CHOSEN="$("$PY" -c "import json; d=json.load(open('$GEMINI_FIX_JSON')); print(d.get('chosen') or '$TARGET_GEMINI')")"
  cp_target "$GEMINI_FIX_JSON"

  if [ "$GEMINI_STATUS" = "blocked" ]; then
    log "[BLOQUÉ] Gemini fix impossible"
    echo "- **Statut** : BLOQUÉ — voir \`gemini-fix-result.json\`" >> "$REPORT"
    GEMINI_OK=0
  elif [ "$GEMINI_CHOSEN" = "$CURRENT_MODEL" ]; then
    echo "- **Statut** : OK — \`$CURRENT_MODEL\` répond" >> "$REPORT"
    GEMINI_OK=1
  else
    cp "$REPO_ROOT/.env" "$OUT_DIR/.env.backup-$TS" 2>/dev/null || true
    set_gemini_model "$GEMINI_CHOSEN"
    restart_ai || log "[WARN] restart AI failed"
    PING="$("$PY" -c "
import sys
sys.path.insert(0, '$REPO_ROOT/ai-engine/src')
from citevision_ai.config import settings
from citevision_ai.vlm.gemini_client import GeminiClient
c = GeminiClient(settings.gemini_api_key, model=settings.gemini_model or '$GEMINI_CHOSEN')
print('yes' if c.ping() else 'no')
")"
    log "[APPLIQUÉ] GEMINI_MODEL=$GEMINI_CHOSEN ping=$PING"
    echo "- **Statut** : APPLIQUÉ \`GEMINI_MODEL=$GEMINI_CHOSEN\` ping=$PING" >> "$REPORT"
    GEMINI_OK=1
  fi
fi
echo "" >> "$REPORT"

# ===========================================================================
# ÉTAPE B — Diagnostic spatial (read-only)
# ===========================================================================
log "== ÉTAPE B : diagnostic spatial =="
echo "## B. Diagnostic spatial (API/DB)" >> "$REPORT"

SPATIAL_DIAG_JSON="$OUT_DIR/spatial-diagnostic.json"
"$PY" - "$SPATIAL_DIAG_JSON" <<'PYEOF' | tee -a "$OUT_DIR/spatial-diagnostic.log"
import json
import os
import sys
import urllib.request
from pathlib import Path

out_path = sys.argv[1]
API = os.environ.get("BACKEND_API_URL", "http://127.0.0.1:8081")
AI = os.environ.get("AI_ENGINE_URL", "http://127.0.0.1:8001")
EMAIL = os.environ.get("ADMIN_EMAIL", "glory.henock@hologram.cd")
PASS = os.environ.get("ADMIN_PASSWORD", "Hologram2026!")
ORG = os.environ.get("DEMO_ORG_ID", "74d51ead-97a7-4e41-a488-503a9b90c466")
RULE_NAME = "Démo · Feu rouge"
TL = frozenset({"traffic_light_color", "red_light_observation"})


def get_json(url, headers=None):
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode())


def req(method, url, token=None, body=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(r, timeout=60) as resp:
        raw = resp.read().decode()
        return json.loads(raw) if raw else {}


def rule_camera_id(rule):
    defn = rule.get("definition") or {}
    if isinstance(defn, str):
        defn = json.loads(defn)
    cam = defn.get("camera_id")
    if cam:
        return str(cam)
    return str((defn.get("bindings") or {}).get("camera_id") or "")


result = {}

try:
    blockers = get_json(f"{AI}/debug/rule-blockers")
except Exception as exc:
    blockers = {"error": str(exc)}

fb = blockers.get("frigate_bridge") or {}
result["mqtt_by_camera"] = fb.get("mqtt_by_camera") or {}
result["spatial_camera_count"] = blockers.get("spatial_camera_count", 0)
result["spatial_tl_summary"] = blockers.get("spatial_tl_summary") or {}
result["hsv_gate_debug_keys"] = list((blockers.get("hsv_gate_debug") or {}).keys())

try:
    cams_payload = get_json(f"{AI}/cameras")
    cams = cams_payload.get("cameras") or []
    result["ai_active_cameras"] = [
        {"camera_id": c.get("camera_id"), "frames": c.get("frames_processed"), "error": c.get("last_error")}
        for c in cams if isinstance(c, dict)
    ]
except Exception as exc:
    result["ai_active_cameras"] = {"error": str(exc)}

feu_cam = ""
tl_zones_db = []
try:
    login = req("POST", f"{API}/api/v1/auth/login", body={"email": EMAIL, "password": PASS})
    tok = login["access_token"]
    rules = req("GET", f"{API}/api/v1/orgs/{ORG}/rules", tok)
    feu = next((r for r in rules if r.get("name") == RULE_NAME), None)
    feu_cam = rule_camera_id(feu) if feu else ""
    result["feu_camera_id"] = feu_cam
    zones = req("GET", f"{API}/api/v1/orgs/{ORG}/zones", tok)
    if isinstance(zones, dict):
        zones = zones.get("items", zones)
    for z in zones or []:
        if str(z.get("camera_id") or "") != feu_cam:
            continue
        bc = z.get("behavior_config") or {}
        if isinstance(bc, str):
            bc = json.loads(bc) if bc.startswith("{") else {}
        beh = str(bc.get("behavior") or z.get("zone_kind") or "")
        if beh in TL:
            tl_zones_db.append({"name": z.get("name"), "behavior": beh})
    result["feu_tl_zones_db"] = tl_zones_db
except Exception as exc:
    result["feu_rule_error"] = str(exc)

if feu_cam:
    try:
        sp = get_json(f"{AI}/cameras/{feu_cam}/spatial")
        behaviors = [str(z.get("behavior") or "") for z in (sp.get("zones") or []) if isinstance(z, dict)]
        result["feu_ai_spatial_behaviors"] = behaviors
        result["feu_ai_spatial_tl"] = [b for b in behaviors if b in TL]
    except Exception as exc:
        result["feu_ai_spatial_error"] = str(exc)

active_ids = {c.get("camera_id") for c in (result.get("ai_active_cameras") or []) if isinstance(c, dict)}
feu_running = feu_cam in active_ids and any(
    int(c.get("frames") or 0) >= 1 for c in (result.get("ai_active_cameras") or [])
    if isinstance(c, dict) and c.get("camera_id") == feu_cam
)

if not feu_cam:
    verdict = "missing_feu_rule"
elif not tl_zones_db:
    verdict = "missing_tl_zones"
elif not feu_running and result.get("spatial_camera_count", 0) == 0:
    verdict = "idle_no_worker"
elif feu_running and result.get("spatial_camera_count", 0) == 0:
    verdict = "spatial_not_loaded"
elif result.get("spatial_tl_summary"):
    verdict = "spatial_ok"
else:
    verdict = "hsv_timing_or_unknown"

result["verdict"] = verdict
result["feu_camera_running"] = feu_running
result["note"] = (
    "mqtt_by_camera lists all Frigate event cameras; feu rule camera may differ — expected."
)

Path(out_path).write_text(json.dumps(result, indent=2), encoding="utf-8")
print(json.dumps(result, indent=2))
print(f"VERDICT={verdict}")
PYEOF

SPATIAL_VERDICT="$(grep '^VERDICT=' "$OUT_DIR/spatial-diagnostic.log" 2>/dev/null | tail -1 | cut -d= -f2- || echo unknown)"
cp_target "$SPATIAL_DIAG_JSON"
echo '```json' >> "$REPORT"
"$PY" -c "import json; print(json.dumps(json.load(open('$SPATIAL_DIAG_JSON')), indent=2)[:4000])" >> "$REPORT" 2>/dev/null || true
echo '```' >> "$REPORT"
echo "- **Verdict** : \`$SPATIAL_VERDICT\`" >> "$REPORT"
echo "" >> "$REPORT"

# ===========================================================================
# ÉTAPE C — Fix spatial (confirmation obligatoire, skip si AUTO_YES)
# ===========================================================================
log "== ÉTAPE C : fix spatial (confirmation) =="
echo "## C. Fix spatial (optionnel)" >> "$REPORT"

if [ "${MICROTEST_AUTO_YES:-0}" = "1" ]; then
  log "[SKIP] Étape C — MICROTEST_AUTO_YES=1"
  echo "- **Statut** : SKIP — confirmation manuelle requise pour reload spatial" >> "$REPORT"
elif [ "$SPATIAL_VERDICT" = "idle_no_worker" ] || [ "$SPATIAL_VERDICT" = "spatial_ok" ]; then
  echo "- **Statut** : SKIP — verdict \`$SPATIAL_VERDICT\` (warm-start suffit pour probe)" >> "$REPORT"
else
  echo "Options :" >> "$REPORT"
  echo "1. \`bash scripts/force-spatial-reload.sh\` (recommandé)" >> "$REPORT"
  echo "2. resync-spatial seul" >> "$REPORT"
  echo "3. \`push_ai_spatial_from_api.py\`" >> "$REPORT"
  if microtest_confirm "Appliquer force-spatial-reload.sh ?"; then
    bash "$REPO_ROOT/scripts/force-spatial-reload.sh" 2>&1 | tee "$OUT_DIR/force-spatial-reload.log"
    echo "- **Statut** : force-spatial-reload exécuté" >> "$REPORT"
    cp_target "$OUT_DIR/force-spatial-reload.log"
  else
    echo "- **Statut** : non appliqué (refus ou non-TTY)" >> "$REPORT"
  fi
fi
echo "" >> "$REPORT"

# ===========================================================================
# ÉTAPE D — Reprobe (auto + warm-start)
# ===========================================================================
log "== ÉTAPE D : warm-start + reprobe HSV =="
echo "## D. Reprobe post-fix" >> "$REPORT"

BEFORE_ENQ="$(bridge_stat red_light_enqueued)"
WARM_OUT="$(microtest_warm_feu_camera 90 2>&1 || true)"
log "warm_feu: $WARM_OUT"
echo "- Warm-start feu : \`$WARM_OUT\`" >> "$REPORT"

if [ -f "$REPO_ROOT/scripts/microtest/_microtest_raw_hsv_probe.py" ]; then
  "$PY" "$REPO_ROOT/scripts/microtest/_microtest_raw_hsv_probe.py" \
    --duration 60 --out-dir "$OUT_DIR" 2>&1 | tee "$OUT_DIR/raw_hsv_probe.log"
  cp_target "$OUT_DIR/raw_hsv_probe.log"
  PROBE_SUMMARY="$(grep '^\[RESULT\]' "$OUT_DIR/raw_hsv_probe.log" | tr '\n' ' ' || true)"
  echo "- Probe : $PROBE_SUMMARY" >> "$REPORT"
else
  echo "- Probe script missing" >> "$REPORT"
fi

curl -sf -m 12 "$AI/debug/rule-blockers" > "$OUT_DIR/rule-blockers-after.json" 2>/dev/null || echo '{}' > "$OUT_DIR/rule-blockers-after.json"
cp_target "$OUT_DIR/rule-blockers-after.json"

AFTER_STATS="$("$PY" - "$OUT_DIR/rule-blockers-after.json" "$OUT_DIR/raw_hsv_probe.log" <<'PY'
import json, sys
from pathlib import Path

blockers = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8") or "{}")
probe_log = Path(sys.argv[2])
n_red_raw = n_red_gate = 0
if probe_log.exists():
    for line in probe_log.read_text(encoding="utf-8").splitlines():
        if line.startswith("[RESULT]") and "n_red_raw=" in line:
            for part in line.split():
                if part.startswith("n_red_raw="):
                    n_red_raw = int(part.split("=", 1)[1])
                if part.startswith("n_red_gate="):
                    n_red_gate = int(part.split("=", 1)[1])

spatial_count = blockers.get("spatial_camera_count", 0)
tl_summary = blockers.get("spatial_tl_summary") or {}
hsv_keys = len(blockers.get("hsv_gate_debug") or {})
print(f"spatial_count={spatial_count} hsv_keys={hsv_keys} tl_cams={len(tl_summary)} n_red_raw={n_red_raw} n_red_gate={n_red_gate}")
green = (
    int(spatial_count or 0) > 0
    or len(tl_summary) > 0
    or n_red_raw > 0
    or n_red_gate > 0
)
print("PROCEED_E=" + ("1" if green else "0"))
PY
)"

echo "- After : $AFTER_STATS" >> "$REPORT"
PROCEED_E="$(echo "$AFTER_STATS" | grep '^PROCEED_E=' | cut -d= -f2)"
AFTER_ENQ="$(bridge_stat red_light_enqueued)"
DELTA_ENQ=$((AFTER_ENQ - BEFORE_ENQ))
if [ "$DELTA_ENQ" -gt 0 ]; then
  PROCEED_E=1
  echo "- Delta red_light_enqueued during warm+probe : $DELTA_ENQ → PROCEED_E=1" >> "$REPORT"
fi

if [ "$PROCEED_E" = "1" ]; then
  echo "✅ **D vert** — signal spatial/HSV ou bridge détecté" >> "$REPORT"
else
  echo "❌ **D rouge** — pas de signal ; 1-hit quand même possible via warm-start (étape E)" >> "$REPORT"
  # Allow 1-hit if warm-start succeeded (cam frames >= 3)
  if echo "$WARM_OUT" | grep -qE 'cam_id=.*frames=[0-9]+'; then
    WARM_FRAMES="$(echo "$WARM_OUT" | sed -n 's/.*frames=\([0-9][0-9]*\).*/\1/p' | head -1)"
    if [ "${WARM_FRAMES:-0}" -ge 3 ] 2>/dev/null; then
      PROCEED_E=1
      echo "- Override : warm-start OK (frames=$WARM_FRAMES) → PROCEED_E=1" >> "$REPORT"
    fi
  fi
fi
echo "" >> "$REPORT"

# ===========================================================================
# ÉTAPE E — 1-hit feu (auto si D vert ou warm OK)
# ===========================================================================
log "== ÉTAPE E : 1-hit feu =="
echo "## E. 1-hit feu final" >> "$REPORT"

if [ "$GEMINI_OK" != "1" ]; then
  log "[SKIP] 1-hit — Gemini non OK"
  echo "- **SKIP** : Gemini fix requis d'abord" >> "$REPORT"
elif [ "$PROCEED_E" != "1" ]; then
  log "[SKIP] 1-hit — reprobe non vert"
  echo "- **SKIP** : pas de signal spatial/HSV — corriger étape B/C puis relancer" >> "$REPORT"
else
  export MICROTEST_FORCE_1HIT=1
  export GATE_FEU=NO-GO
  export GATE_GEMINI_FEU=NO-GO
  export RULE_NAME='Démo · Feu rouge'
  export RULE_ALIAS=feu
  if [ -f "$REPO_ROOT/scripts/microtest/_microtest_1hit_feu.sh" ]; then
    log "Lancement 1-hit feu..."
    bash "$REPO_ROOT/scripts/microtest/_microtest_1hit_feu.sh" 2>&1 | tee "$OUT_DIR/1hit-feu.log"
    cp_target "$OUT_DIR/1hit-feu.log"
    T45="$(grep -o 'TEST45_RC=[0-9]*' "$OUT_DIR/1hit-feu.log" | tail -1 | cut -d= -f2 || echo 1)"
    echo "- **TEST45_RC** : $T45" >> "$REPORT"
    if [ "$T45" = "0" ]; then
      echo "- **PASS_1HIT** feu atteint (pas PASS_DoD)" >> "$REPORT"
    else
      echo "- **FAIL** — voir \`1hit-feu.log\`" >> "$REPORT"
    fi
  else
    echo "- Script _microtest_1hit_feu.sh introuvable" >> "$REPORT"
  fi
fi

echo "" >> "$REPORT"
echo "## Résumé" >> "$REPORT"
echo "| Étape | Résultat |" >> "$REPORT"
echo "|-------|----------|" >> "$REPORT"
echo "| A Gemini | GEMINI_OK=$GEMINI_OK |" >> "$REPORT"
echo "| B Spatial | $SPATIAL_VERDICT |" >> "$REPORT"
echo "| D Reprobe | PROCEED_E=$PROCEED_E |" >> "$REPORT"
echo "| E 1-hit | voir section E |" >> "$REPORT"
echo "" >> "$REPORT"
echo "Rapport : \`$REPORT\`" >> "$REPORT"

cp_target "$REPORT"
cp_target "$OUT_DIR/final-fix.raw.log"

log "Terminé. Rapport : $REPORT"
echo ""
echo "=================================================================="
echo " Rapport final : $REPORT"
echo " Windows : $WIN_OUT"
echo "=================================================================="
