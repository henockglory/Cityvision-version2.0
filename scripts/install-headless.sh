#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
# CitéVision v2 — Installation headless (sans navigateur)
#
# Enchaîne bootstrap, setup, démarrage et vérification des services
# (gate IA yolo_loaded + face_loaded + plate_loaded incluse). Aucune interaction requise.
#
# Usage recommandé :
#   sudo bash scripts/install-headless.sh
#
# Options :
#   --start-mode=auto|manual   Mode systemd (défaut: auto)
#   --skip-bootstrap           Ignorer installer/linux/bootstrap.sh
#   --skip-start               Installation uniquement, sans démarrage
#   --log-file=PATH            Fichier de log (défaut: logs/install-headless.log)
#   --help                     Afficher l'aide
# ─────────────────────────────────────────────────────────────
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

START_MODE="auto"
SKIP_BOOTSTRAP=false
SKIP_START=false
LOG_FILE="$ROOT/logs/install-headless.log"

for arg in "$@"; do
  case "$arg" in
    --start-mode=*) START_MODE="${arg#*=}" ;;
    --skip-bootstrap) SKIP_BOOTSTRAP=true ;;
    --skip-start) SKIP_START=true ;;
    --log-file=*) LOG_FILE="${arg#*=}" ;;
    --help)
      cat <<'EOF'
Usage: sudo bash scripts/install-headless.sh [OPTIONS]

Installation complète sans interaction (SSH, CI, serveur sans GUI).

Options:
  --start-mode=auto|manual   Mode de démarrage systemd (défaut: auto)
  --skip-bootstrap           Ignorer bootstrap.sh (deps déjà installées)
  --skip-start               Ne pas démarrer les services après l'installation
  --log-file=PATH            Fichier de log (défaut: logs/install-headless.log)
  --help                     Afficher cette aide

Exemple :
  sudo bash scripts/install-headless.sh
  sudo bash scripts/install-headless.sh --start-mode=manual --skip-bootstrap
EOF
      exit 0
      ;;
    *)
      echo "[WARN] Argument inconnu: $arg" >&2
      ;;
  esac
done

if [[ "$START_MODE" != "auto" && "$START_MODE" != "manual" ]]; then
  echo "[ERR]  --start-mode doit être 'auto' ou 'manual'" >&2
  exit 1
fi

INSTALL_USER="${SUDO_USER:-${USER:-$(whoami)}}"
mkdir -p "$(dirname "$LOG_FILE")"
echo "# CitéVision v2 Headless Install — $(date)" > "$LOG_FILE"

# shellcheck source=scripts/lib/env-utils.sh
source "$ROOT/scripts/lib/env-utils.sh"

_log() {
  echo "$1" | tee -a "$LOG_FILE"
}
_info()  { _log "[INFO] $1"; }
_ok()    { _log "[OK]   $1"; }
_warn()  { _log "[WARN] $1"; }
_err()   { _log "[ERR]  $1"; }
_step()  { _log ""; _log "=== $1 ==="; }

_run_as_user() {
  local cmd="$1"
  if [[ $EUID -eq 0 && -n "${SUDO_USER:-}" ]]; then
    sudo -u "$SUDO_USER" bash -lc "cd '$ROOT' && $cmd"
  else
    bash -lc "cd '$ROOT' && $cmd"
  fi
}

_wait_health_key() {
  local url="$1"
  local key="$2"
  local timeout="${3:-180}"
  local i=0
  while (( i < timeout )); do
    local status
    status="$(curl -sf "$url" 2>/dev/null \
      | grep -o "\"${key}\":\"[^\"]*\"" | cut -d'"' -f4 || echo "")"
    if [[ "$status" == "true" ]]; then
      return 0
    fi
    sleep 2
    ((i += 2))
  done
  return 1
}

_wait_all_ai_models() {
  local url="$1"
  local timeout="${2:-300}"
  _wait_health_key "$url" "yolo_loaded" "$timeout" || return 1
  _wait_health_key "$url" "face_loaded" "$timeout" || return 1
  _wait_health_key "$url" "plate_loaded" "$timeout" || return 1
  return 0
}

_step "Installation headless CitéVision v2"
_info "Racine: $ROOT"
_info "Utilisateur: $INSTALL_USER"
_info "Mode service: $START_MODE"
_info "Log: $LOG_FILE"

# ── 1. Bootstrap ─────────────────────────────────────────────
if [[ "$SKIP_BOOTSTRAP" == "false" ]]; then
  _step "Bootstrap système"
  if [[ -f "$ROOT/installer/linux/bootstrap.sh" ]]; then
    bash "$ROOT/installer/linux/bootstrap.sh" --silent --log-file="$LOG_FILE" \
      >>"$LOG_FILE" 2>&1 \
      && _ok "Bootstrap terminé" \
      || { _err "Bootstrap échoué — voir $LOG_FILE"; exit 1; }
  else
    _warn "installer/linux/bootstrap.sh introuvable — étape ignorée"
  fi
else
  _info "Bootstrap ignoré (--skip-bootstrap)"
fi

if ! command -v docker &>/dev/null; then
  _err "Docker absent. Relancez sans --skip-bootstrap ou installez Docker manuellement."
  exit 1
fi

# ── 2. Installation applicative ────────────────────────────
_step "Installation applicative (setup-wsl.sh)"
SETUP_ARGS=(--silent --log-file="$LOG_FILE" --start-mode="$START_MODE")
if _run_as_user "bash scripts/setup-wsl.sh ${SETUP_ARGS[*]}" >>"$LOG_FILE" 2>&1; then
  _ok "Installation terminée"
else
  _err "setup-wsl.sh a échoué — voir $LOG_FILE"
  exit 1
fi

if [[ "$SKIP_START" == "true" ]]; then
  _step "Terminé (--skip-start)"
  _info "Services non démarrés. Lancez: bash scripts/start-linux.sh"
  _info "Ou (systemd): sudo systemctl start citevision"
  exit 0
fi

# ── 3. Démarrage ─────────────────────────────────────────────
_step "Démarrage des services"
SERVICE_ACTIVE=false
if command -v systemctl &>/dev/null; then
  if systemctl is-active --quiet citevision.service 2>/dev/null; then
    SERVICE_ACTIVE=true
    _info "Service citevision.service déjà actif — start-linux.sh ignoré"
  fi
fi

if [[ "$SERVICE_ACTIVE" == "false" ]]; then
  if [[ "$START_MODE" == "manual" && "$SERVICE_ACTIVE" == "false" ]]; then
    _info "Mode manual — lancement via start-linux.sh"
  elif [[ "$START_MODE" == "auto" && "$SERVICE_ACTIVE" == "false" ]]; then
    _info "Service non actif — lancement via start-linux.sh"
  fi
  if _run_as_user "bash scripts/start-linux.sh" >>"$LOG_FILE" 2>&1; then
    _ok "start-linux.sh terminé"
  else
    _warn "start-linux.sh a signalé des erreurs — poursuite des vérifications santé"
  fi
fi

# Charger les ports depuis .env si présent
ENV_FILE="$(ensure_env_file "$ROOT" 2>/dev/null || echo "$ROOT/.env")"
load_dotenv "$ENV_FILE"
BACKEND_PORT="${API_PORT:-8081}"
AI_PORT="${AI_ENGINE_PORT:-8001}"
RULES_PORT="${RULES_ENGINE_PORT:-8010}"
FRONTEND_PORT="5174"

# ── 4. Gate santé ────────────────────────────────────────────
_step "Vérification santé des services"
HEALTH_OK=true

_info "Backend ($BACKEND_PORT)..."
if wait_http_ok "http://127.0.0.1:$BACKEND_PORT/health" 120; then
  _ok "Backend opérationnel"
else
  _err "Backend inaccessible — voir logs/backend.log"
  HEALTH_OK=false
fi

_info "AI Engine ($AI_PORT) — YOLO + InsightFace + PaddleOCR..."
if wait_http_ok "http://127.0.0.1:$AI_PORT/health" 120; then
  if _wait_all_ai_models "http://127.0.0.1:$AI_PORT/health" 300; then
    _ok "AI Engine opérationnel — yolo_loaded, face_loaded, plate_loaded"
  else
    _err "AI Engine up mais modèles IA incomplets — voir logs/ai-engine.log"
    _err "Relancez : bash scripts/download-models.sh"
    HEALTH_OK=false
  fi
else
  _err "AI Engine inaccessible — voir logs/ai-engine.log"
  HEALTH_OK=false
fi

_info "Rules Engine ($RULES_PORT)..."
if wait_http_ok "http://127.0.0.1:$RULES_PORT/health" 60; then
  _ok "Rules Engine opérationnel"
else
  _err "Rules Engine inaccessible — voir logs/rules-engine.log"
  HEALTH_OK=false
fi

_info "Frontend ($FRONTEND_PORT)..."
if wait_http_ok "http://127.0.0.1:$FRONTEND_PORT/" 120; then
  _ok "Frontend opérationnel"
else
  _err "Frontend inaccessible — voir logs/frontend.log"
  HEALTH_OK=false
fi

# ── 5. Résumé ────────────────────────────────────────────────
_step "Résumé"
_log ""
_log "=== CitéVision v2 — Installation headless terminée ==="
_log "  Frontend:     http://localhost:$FRONTEND_PORT"
_log "  Setup:        http://localhost:$FRONTEND_PORT/setup"
_log "  Backend:      http://localhost:$BACKEND_PORT/health"
_log "  AI Engine:    http://localhost:$AI_PORT/health"
_log "  Rules Engine: http://localhost:$RULES_PORT/health"
_log ""
_log "Diagnostic:  bash scripts/doctor-linux.sh"
_log "État service: systemctl status citevision"
_log "Arrêt:       bash scripts/stop-linux.sh"
_log "Log complet: $LOG_FILE"
_log ""

if [[ "$HEALTH_OK" == "false" ]]; then
  _err "Installation terminée avec des erreurs de santé"
  exit 1
fi

_ok "Tous les services sont opérationnels"
exit 0
