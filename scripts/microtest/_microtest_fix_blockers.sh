#!/usr/bin/env bash
# Diagnostique puis corrige (si possible) les 3 blocages micro-test.
# Usage: cd ~/citevision-v2 && bash scripts/microtest/_microtest_fix_blockers.sh
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
REPORT="$OUT_DIR/fix-report.md"
cp_target() { cp -f "$1" "$WIN_OUT/$(basename "$1")" 2>/dev/null || true; }

log() { echo "[$(date -u +%H:%M:%S)] $*" | tee -a "$OUT_DIR/fix-report.raw.log"; }

echo "# Fix-blockers report — $TS" > "$REPORT"
echo "" >> "$REPORT"

ensure_stack

# ---------------------------------------------------------------------------
# BLOQUANT 1 — Gemini HTTP 404
# ---------------------------------------------------------------------------
log "== BLOQUANT 1 : diagnostic modèle Gemini =="
echo "## 1. Gemini HTTP 404" >> "$REPORT"

if [ -f "$REPO_ROOT/scripts/lib/env-utils.sh" ]; then
  # shellcheck source=scripts/lib/env-utils.sh
  source "$REPO_ROOT/scripts/lib/env-utils.sh"
  load_dotenv "$(ensure_env_file "$REPO_ROOT")"
fi

CONFIGURED_MODEL="$(resolve_gemini_model)"
HEALTH_MODEL="$("$PY" - <<PY
import json, urllib.request
try:
    with urllib.request.urlopen("http://127.0.0.1:8001/health", timeout=8) as r:
        h = json.load(r)
    print(h.get("gemini_model") or "")
except Exception:
    print("")
PY
)"
[ -n "$HEALTH_MODEL" ] && CONFIGURED_MODEL="$HEALTH_MODEL"
log "Modèle configuré (détecté) : $CONFIGURED_MODEL"
echo "- Modèle configuré (détecté) : \`$CONFIGURED_MODEL\`" >> "$REPORT"

GEMINI_FIX_JSON="$OUT_DIR/gemini-fix-result.json"
"$PY" - "$CONFIGURED_MODEL" "$GEMINI_FIX_JSON" <<'PYEOF'
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

configured = sys.argv[1]
out_path = Path(sys.argv[2])
root = Path.home() / "citevision-v2"
env = {}
for line in (root / ".env").read_text(encoding="utf-8").splitlines() if (root / ".env").exists() else []:
    if not line.strip() or line.lstrip().startswith("#") or "=" not in line:
        continue
    k, v = line.split("=", 1)
    env[k.strip()] = v.strip().strip('"').strip("'")
key = (os.environ.get("GEMINI_API_KEY") or env.get("GEMINI_API_KEY") or "").strip()
result = {"configured": configured, "key_present": bool(key), "ok_models": [], "chosen": "", "status": "blocked"}

if not key:
    result["status"] = "blocked"
    result["reason"] = "GEMINI_API_KEY missing"
    out_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result))
    raise SystemExit(0)

def list_flash_models(api_key: str) -> list[str]:
    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
    with urllib.request.urlopen(url, timeout=30) as r:
        data = json.load(r)
    names = []
    for m in data.get("models") or []:
        name = str(m.get("name") or "").replace("models/", "")
        methods = m.get("supportedGenerationMethods") or []
        if "generateContent" in methods and "flash" in name.lower():
            names.append(name)
    return sorted(set(names))

def smoke_generate(api_key: str, model: str) -> tuple[bool, int, str]:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    body = json.dumps({"contents": [{"parts": [{"text": "Reply with exactly: ok"}]}]}).encode()
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            json.load(r)
        return True, 200, ""
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", "replace")
        msg = raw[:200]
        try:
            msg = json.loads(raw)["error"]["message"].split("\n")[0][:160]
        except Exception:
            pass
        return False, int(exc.code or 0), msg
    except Exception as exc:
        return False, 0, str(exc)[:160]

flash = list_flash_models(key)
result["flash_models"] = flash

# Test configured model first, then all flash models
candidates = [configured] + [m for m in flash if m != configured]
ok_models: list[str] = []
failures: dict[str, str] = {}
for model in candidates:
    if not model:
        continue
    ok, code, msg = smoke_generate(key, model)
    if ok:
        ok_models.append(model)
    else:
        failures[model] = f"HTTP {code}: {msg}"

result["ok_models"] = ok_models
result["failures"] = failures

if configured in ok_models and len(ok_models) >= 1:
    result["chosen"] = configured
    result["status"] = "ok"
elif len(ok_models) == 1:
    result["chosen"] = ok_models[0]
    result["status"] = "fix_proposed"
elif len(ok_models) > 1:
    preferred = [
        "gemini-3.1-flash-lite",
        *[m for m in ok_models if "flash-lite" in m.lower()],
        *[m for m in ok_models if "flash" in m.lower()],
    ]
    chosen = ""
    for p in preferred:
        if p in ok_models:
            chosen = p
            break
    if not chosen:
        chosen = ok_models[0]
    result["chosen"] = chosen
    result["status"] = "fix_proposed"
else:
    result["status"] = "blocked"
    result["reason"] = "no generateContent flash model succeeded"

out_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
print(json.dumps(result))
PYEOF

GEMINI_STATUS="$("$PY" -c "import json; print(json.load(open('$GEMINI_FIX_JSON'))['status'])")"
GEMINI_CHOSEN="$("$PY" -c "import json; d=json.load(open('$GEMINI_FIX_JSON')); print(d.get('chosen') or '')")"
OK_MODELS="$("$PY" -c "import json; print(','.join(json.load(open('$GEMINI_FIX_JSON')).get('ok_models') or []))")"

echo "- Modèles flash OK (generateContent) : \`${OK_MODELS:-none}\`" >> "$REPORT"
cp_target "$GEMINI_FIX_JSON"

if [ "$GEMINI_STATUS" = "blocked" ]; then
  REASON="$("$PY" -c "import json; print(json.load(open('$GEMINI_FIX_JSON')).get('reason',''))")"
  log "[BLOQUÉ] Gemini: $REASON"
  echo "- **Statut** : BLOQUÉ — $REASON" >> "$REPORT"
elif [ "$GEMINI_STATUS" = "ok" ]; then
  log "[OK] Modèle $GEMINI_CHOSEN répond generateContent"
  echo "- **Statut** : OK — \`$GEMINI_CHOSEN\` répond generateContent." >> "$REPORT"
else
  log "[FIX] Application GEMINI_MODEL=$GEMINI_CHOSEN"
  set_gemini_model "$GEMINI_CHOSEN"
  echo "- **Statut** : FIX APPLIQUÉ — \`GEMINI_MODEL=$GEMINI_CHOSEN\`" >> "$REPORT"
  restart_ai || log "[WARN] restart AI failed after Gemini fix"
  PING_OK="$("$PY" - <<PY
import sys
sys.path.insert(0, "$REPO_ROOT/ai-engine/src")
from citevision_ai.config import settings
from citevision_ai.vlm.gemini_client import GeminiClient
c = GeminiClient(settings.gemini_api_key, model=settings.gemini_model or "$GEMINI_CHOSEN")
print("yes" if c.ping() else "no")
PY
)"
  echo "- Post-fix ping : \`$PING_OK\`" >> "$REPORT"
fi
echo "" >> "$REPORT"

# ---------------------------------------------------------------------------
# BLOQUANT 2 — hsv_gate_debug vide
# ---------------------------------------------------------------------------
log "== BLOQUANT 2 : diagnostic hsv_gate_debug =="
echo "## 2. hsv_gate_debug vide (test A)" >> "$REPORT"

DEBUG_URL="${AI_URL:-http://127.0.0.1:8001}/debug/rule-blockers"
DEBUG_BEFORE="$OUT_DIR/rule-blockers-before.json"
curl -sf -m 12 "$DEBUG_URL" > "$DEBUG_BEFORE" 2>>"$OUT_DIR/fix-report.raw.log" || echo '{}' > "$DEBUG_BEFORE"
cp_target "$DEBUG_BEFORE"

HSV_DIAG="$("$PY" - "$DEBUG_BEFORE" "$AI" <<'PYEOF'
import json
import sys
import urllib.request

blockers_path, ai_base = sys.argv[1], sys.argv[2].rstrip("/")
data = json.loads(open(blockers_path, encoding="utf-8").read() or "{}")
hsv = data.get("hsv_gate_debug") or {}
tl_summary = data.get("spatial_tl_summary") or {}
spatial_count = data.get("spatial_camera_count", 0)

lines = []
lines.append(f"hsv_gate_debug_keys={list(hsv.keys())}")
lines.append(f"spatial_camera_count={spatial_count}")
lines.append(f"spatial_tl_summary={json.dumps(tl_summary)}")

# Level C: active cameras + spatial zones
try:
    with urllib.request.urlopen(f"{ai_base}/cameras", timeout=8) as r:
        cams_payload = json.load(r)
    cams = cams_payload.get("cameras") or []
    if isinstance(cams, dict):
        cams = list(cams.values())
    active = []
    for c in cams:
        if not isinstance(c, dict):
            continue
        cid = c.get("camera_id") or c.get("id") or ""
        if cid:
            active.append(str(cid))
    lines.append(f"active_cameras={active}")
    for cid in active[:8]:
        try:
            with urllib.request.urlopen(f"{ai_base}/cameras/{cid}/spatial", timeout=8) as r:
                sp = json.load(r)
            zones = sp.get("zones") or []
            behaviors = [str(z.get("behavior") or "") for z in zones if isinstance(z, dict)]
            tl = [b for b in behaviors if b in ("traffic_light_color", "red_light_observation")]
            lines.append(f"spatial_{cid}={behaviors} tl={tl}")
        except Exception as exc:
            lines.append(f"spatial_{cid}=ERR:{exc}")
except Exception as exc:
    lines.append(f"cameras_err={exc}")

# Verdict
if not tl_summary and spatial_count == 0:
    verdict = "config_routing"
    detail = "spatial configs vides — caméra feu probablement non démarrée"
elif not tl_summary:
    verdict = "config_routing"
    detail = "spatial chargé mais aucune zone traffic_light_color/red_light_observation"
else:
    unknown_all = all(
        (v.get("raw") or "unknown") == "unknown" and (v.get("stable") or "unknown") == "unknown"
        for v in hsv.values()
    ) if hsv else True
    if unknown_all:
        verdict = "hsv_pipeline"
        detail = "zones TL résolues mais raw/stable unknown — pipeline HSV ou timing vidéo"
    else:
        verdict = "ok_or_timing"
        detail = "hsv_gate_debug peuplé — gate A NO-GO = fenêtre poll ou compteurs bridge"

lines.append(f"verdict={verdict}")
lines.append(f"detail={detail}")
print("\n".join(lines))
PYEOF
)"

echo '```' >> "$REPORT"
echo "$HSV_DIAG" >> "$REPORT"
echo '```' >> "$REPORT"
VERDICT2="$(echo "$HSV_DIAG" | grep '^verdict=' | cut -d= -f2-)"
DETAIL2="$(echo "$HSV_DIAG" | grep '^detail=' | cut -d= -f2-)"
echo "- **Verdict** : \`$VERDICT2\` — $DETAIL2" >> "$REPORT"
echo "" >> "$REPORT"
echo "  Probe recommandé :" >> "$REPORT"
echo '  ```bash' >> "$REPORT"
echo "  $PY scripts/microtest/_microtest_raw_hsv_probe.py --duration 60 --out-dir $OUT_DIR" >> "$REPORT"
echo '  ```' >> "$REPORT"
echo "" >> "$REPORT"

# ---------------------------------------------------------------------------
# BLOQUANT 3 — Test 45 timing
# ---------------------------------------------------------------------------
log "== BLOQUANT 3 : diagnostic timing test 45 =="
echo "## 3. Test 45 — enqueue hors fenêtre" >> "$REPORT"

FRIGATE_VER="$(curl -sf -m 5 http://127.0.0.1:5000/api/version || echo FAIL)"
BEFORE_ENQ="$(bridge_stat red_light_enqueued)"
sleep 60
AFTER_ENQ="$(bridge_stat red_light_enqueued)"
DELTA_ENQ=$((AFTER_ENQ - BEFORE_ENQ))

echo "- Frigate version : \`$FRIGATE_VER\`" >> "$REPORT"
echo "- Delta red_light_enqueued (60s) : \`$DELTA_ENQ\` (before=$BEFORE_ENQ after=$AFTER_ENQ)" >> "$REPORT"
echo "- **Recommandation** : traiter comme symptôme des points 1+2. Relancer test 45 seulement après fix Gemini + spatial TL résolu :" >> "$REPORT"
echo '  ```bash' >> "$REPORT"
echo "  ensure_stack && bash scripts/microtest/_microtest_1hit_feu.sh" >> "$REPORT"
echo '  ```' >> "$REPORT"
echo "" >> "$REPORT"

# ---------------------------------------------------------------------------
# Résumé
# ---------------------------------------------------------------------------
echo "## Résumé" >> "$REPORT"
echo "" >> "$REPORT"
echo "| # | Bloquant | Statut |" >> "$REPORT"
echo "|---|---|---|" >> "$REPORT"
echo "| 1 | Gemini 404 | $GEMINI_STATUS ($GEMINI_CHOSEN) |" >> "$REPORT"
echo "| 2 | hsv_gate_debug | $VERDICT2 |" >> "$REPORT"
echo "| 3 | Test 45 timing | delta_enq_60s=$DELTA_ENQ |" >> "$REPORT"
echo "" >> "$REPORT"
echo "Rapport : \`$REPORT\`" >> "$REPORT"

cp_target "$REPORT"
cp_target "$OUT_DIR/fix-report.raw.log"

log "Terminé. Rapport : $REPORT"
echo ""
echo "=================================================================="
echo " Rapport généré : $REPORT"
echo " Windows mirror : $WIN_OUT"
echo "=================================================================="
