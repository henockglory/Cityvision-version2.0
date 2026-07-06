#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
# CitéVision v2 — WSL/Linux Setup Script
# Usage: bash scripts/setup-wsl.sh [OPTIONS]
#
# Options:
#   --silent              Suppress non-essential output (still logs errors)
#   --log-file=<path>     Redirect all output to file in addition to stdout
#   --start-mode=auto|manual  Mode de démarrage du service systemd (défaut: auto)
#   --help                Show this help
# ─────────────────────────────────────────────────────────────
set -euo pipefail

# ── Argument parsing ──────────────────────────────────────────
SILENT=false
LOG_FILE=""
START_MODE="auto"

for arg in "$@"; do
  case "$arg" in
    --silent)          SILENT=true ;;
    --log-file=*)      LOG_FILE="${arg#*=}" ;;
    --start-mode=*)    START_MODE="${arg#*=}" ;;
    --help)
      echo "Usage: bash scripts/setup-wsl.sh [--silent] [--log-file=<path>] [--start-mode=auto|manual]"
      exit 0 ;;
    *)
      echo "[WARN] Unknown argument: $arg" ;;
  esac
done

# ── Logging helpers ───────────────────────────────────────────
_log() {
  local msg="$1"
  if [ -n "$LOG_FILE" ]; then
    echo "$msg" | tee -a "$LOG_FILE"
  else
    echo "$msg"
  fi
}
_info()  { $SILENT && [ -n "$LOG_FILE" ] && echo "$1" >>"$LOG_FILE" || _log "[INFO] $1"; }
_ok()    { _log "[OK]   $1"; }
_warn()  { _log "[WARN] $1"; }
_err()   { _log "[ERR]  $1"; }
_step()  { _log ""; _log "=== $1 ==="; }

# Initialize log file
if [ -n "$LOG_FILE" ]; then
  mkdir -p "$(dirname "$LOG_FILE")"
  echo "# CitéVision v2 Setup Log — $(date)" > "$LOG_FILE"
fi

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
# shellcheck source=scripts/lib/env-utils.sh
source "$ROOT/scripts/lib/env-utils.sh"

_log "=== CitéVision v2 WSL/Linux setup ==="
_log ""

if command -v apt-get &>/dev/null; then
  _step "System packages"
  _info "Updating package lists…"
  sudo apt-get update -qq 2>>"${LOG_FILE:-/dev/null}" || true

  _info "Installing system packages…"
  sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq \
    python3.12 python3.12-venv python3-pip \
    build-essential cmake pkg-config \
    curl jq git rsync ffmpeg unzip \
    ca-certificates gnupg lsb-release 2>>"${LOG_FILE:-/dev/null}" || true
  _ok "System packages installed"

  # ── Docker ──────────────────────────────────────────────────
  if ! command -v docker &>/dev/null; then
    _step "Docker Engine"
    _info "Installing Docker Engine…"
    sudo install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
      | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg 2>/dev/null || true
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
      | sudo tee /etc/apt/sources.list.d/docker.list >/dev/null
    sudo apt-get update -qq 2>>"${LOG_FILE:-/dev/null}"
    sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq \
      docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin \
      2>>"${LOG_FILE:-/dev/null}"
    _ok "Docker Engine installed"
  else
    _info "Docker Engine already present — $(docker --version)"
  fi

  # ── Go ───────────────────────────────────────────────────────
  if ! command -v go &>/dev/null; then
    _step "Go 1.22"
    _info "Downloading Go 1.22.5…"
    curl -fsSL https://go.dev/dl/go1.22.5.linux-amd64.tar.gz | sudo tar -C /usr/local -xz
    grep -q '/usr/local/go/bin' ~/.bashrc 2>/dev/null \
      || echo 'export PATH=$PATH:/usr/local/go/bin' >>~/.bashrc
    export PATH="$PATH:/usr/local/go/bin"
    _ok "Go $(go version) installed"
  else
    _info "Go already present — $(go version)"
  fi

  # ── Node.js ──────────────────────────────────────────────────
  if ! command -v node &>/dev/null || [[ "$(node -v 2>/dev/null || echo v0)" < "v20" ]]; then
    _step "Node.js 20 LTS"
    _info "Installing Node.js 20 LTS…"
    curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash - 2>>"${LOG_FILE:-/dev/null}"
    sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq nodejs \
      2>>"${LOG_FILE:-/dev/null}"
    _ok "Node.js $(node -v) installed"
  else
    _info "Node.js already present — $(node -v)"
  fi

  sudo usermod -aG docker "$USER" 2>/dev/null || true
  sudo service docker start 2>/dev/null || _warn "Docker daemon start skipped (may need manual start)"
fi

# ── .env file ────────────────────────────────────────────────
_step "Environment file"
ensure_env_file "$ROOT" >/dev/null
_ok ".env file ready"

# ── Frontend node_modules (avant profil matériel) ─────────────────
_step "Frontend dependencies"
if ! ensure_frontend_deps "$ROOT"; then
  _error "Frontend dependencies — npm install failed (see above)"
fi
_ok "Frontend node_modules ready for WSL/Linux"

# ── Hardware profile generation (avant YOLO pour connaître le bon modèle) ──
_step "Hardware profile"
_info "Génération du profil matériel et de generated.env..."

PYTHON_CMD=""
if [[ -f "ai-engine/.venv/bin/python" ]]; then
  PYTHON_CMD="ai-engine/.venv/bin/python"
elif command -v python3.12 &>/dev/null; then
  PYTHON_CMD="python3.12"
elif command -v python3 &>/dev/null; then
  PYTHON_CMD="python3"
elif command -v python &>/dev/null; then
  PYTHON_CMD="python"
fi

if [[ -n "$PYTHON_CMD" ]] && [[ -f "installer/apply-hardware-profile.py" ]]; then
  hw_ok=false
  for attempt in 1 2; do
    if "$PYTHON_CMD" installer/apply-hardware-profile.py 2>>"${LOG_FILE:-/dev/null}"; then
      hw_ok=true
      _ok "generated.env créé"
      break
    fi
    [[ $attempt -eq 1 ]] && _info "apply-hardware-profile retry…"
  done
  if [[ "$hw_ok" != "true" ]]; then
    if [[ ! -f generated.env ]]; then
      _warn "apply-hardware-profile échoué — fallback CPU-only (yolov8n)"
      cat >generated.env <<'FALLBACK'
# Fallback CPU-only (apply-hardware-profile failed)
CV_YOLO_MODEL=yolov8n.onnx
CV_YOLO_DEVICE=cpu
CV_FACE_DEVICE=cpu
CV_PLATE_DEVICE=cpu
FALLBACK
    else
      _err "apply-hardware-profile.py a échoué et generated.env existant est invalide"
      exit 1
    fi
  fi
else
  _err "Python ou apply-hardware-profile.py introuvable"
  exit 1
fi

# ── AI stack complet (venv + pip + modèles) — auto-fix obligatoire ──
_step "AI Engine stack (venv + modèles IA)"
mkdir -p ai-engine/models logs
if [[ -n "$LOG_FILE" ]]; then
  bash scripts/ensure-ai-stack.sh --fix --max-attempts=5 2>&1 | tee -a "$LOG_FILE"
  ai_rc=${PIPESTATUS[0]}
else
  bash scripts/ensure-ai-stack.sh --fix --max-attempts=5
  ai_rc=$?
fi
if [[ "$ai_rc" -eq 0 ]]; then
  _ok "AI stack prêt (YOLO + InsightFace + PaddleOCR)"
else
  _err "AI stack incomplet après remédiation automatique — voir logs/installer.log"
  exit 1
fi

# ── Mode de démarrage du service (enregistré au premier lancement) ──
_step "Mode de démarrage du service"
if [[ "$START_MODE" != "auto" && "$START_MODE" != "manual" ]]; then
  _warn "Mode de démarrage invalide ($START_MODE) — utilisation de 'auto'"
  START_MODE="auto"
fi
mkdir -p installer
echo "$START_MODE" > installer/.service_start_mode
_ok "Mode service enregistré pour le premier lancement ($START_MODE)"

_log ""
_ok "Setup complete"
_log ""
_log "Next steps:"
_log "  If docker group was just added: newgrp docker"
_log "  Start all services:             bash scripts/start-all.sh"
_log "  Open the app:                   http://localhost:5174"
_log ""

if [ -n "$LOG_FILE" ]; then
  _log "Full log saved to: $LOG_FILE"
fi
