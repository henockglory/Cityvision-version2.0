#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
# CitéVision v2 — WSL/Linux Setup Script
# Usage: bash scripts/setup-wsl.sh [OPTIONS]
#
# Options:
#   --silent              Suppress non-essential output (still logs errors)
#   --log-file=<path>     Redirect all output to file in addition to stdout
#   --help                Show this help
# ─────────────────────────────────────────────────────────────
set -euo pipefail

# ── Argument parsing ──────────────────────────────────────────
SILENT=false
LOG_FILE=""

for arg in "$@"; do
  case "$arg" in
    --silent)          SILENT=true ;;
    --log-file=*)      LOG_FILE="${arg#*=}" ;;
    --help)
      echo "Usage: bash scripts/setup-wsl.sh [--silent] [--log-file=<path>]"
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
_error() { _log "[ERR]  $1"; }
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
    curl jq git rsync ffmpeg \
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

# ── Python virtualenv ────────────────────────────────────────
_step "Python virtualenv (AI Engine)"
VENV_SENTINEL="ai-engine/.venv/.installed_ok"
if [[ ! -d ai-engine/.venv ]]; then
  _info "Creating Python 3.12 virtualenv…"
  python3.12 -m venv ai-engine/.venv
fi
# shellcheck disable=SC1091
source ai-engine/.venv/bin/activate
if [[ -f "$VENV_SENTINEL" ]]; then
  _info "Python packages already installed — skipping pip install"
else
  _info "Installing AI engine requirements (première fois, peut prendre quelques minutes)…"
  pip install --upgrade pip -q 2>>"${LOG_FILE:-/dev/null}"
  ( cd ai-engine && pip install -r requirements.txt -q 2>>"${LOG_FILE:-/dev/null}" )
  touch "$VENV_SENTINEL"
fi
_ok "Python virtualenv ready"

# ── Frontend node_modules ────────────────────────────────────
_step "Frontend dependencies"
if [[ ! -d frontend/node_modules ]] || [[ ! -f frontend/node_modules/.package-lock.json && ! -f frontend/node_modules/.modules.yaml ]]; then
  _info "Running npm install…"
  (cd frontend && npm install --silent 2>>"${LOG_FILE:-/dev/null}")
  _ok "Frontend node_modules installed"
else
  _info "Frontend node_modules already present — skipping"
fi

# ── Hardware profile generation (avant YOLO pour connaître le bon modèle) ──
_step "Hardware profile"
_info "Génération du profil matériel et de generated.env..."

# Chercher Python dans le venv, puis Python 3.12, puis python3
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
  "$PYTHON_CMD" installer/apply-hardware-profile.py 2>>"${LOG_FILE:-/dev/null}" \
    && _ok "generated.env créé" \
    || _warn "apply-hardware-profile.py a échoué — generated.env absent (mode CPU-only par défaut)"
else
  _warn "Python ou apply-hardware-profile.py introuvable — generated.env non créé"
fi

# ── YOLO model download (selon le tier GPU détecté) ──────────
_step "YOLO model"
mkdir -p ai-engine/models logs

# Lire le modèle recommandé par le profil GPU, sinon yolov8n par défaut
CV_YOLO_MODEL="$(grep '^CV_YOLO_MODEL=' generated.env 2>/dev/null | cut -d= -f2 | tr -d ' \r' || true)"
CV_YOLO_MODEL="${CV_YOLO_MODEL:-yolov8n.onnx}"
_info "Modèle YOLO requis selon profil GPU : $CV_YOLO_MODEL"

if [[ -f "ai-engine/models/$CV_YOLO_MODEL" ]]; then
  _ok "Modèle $CV_YOLO_MODEL déjà présent"
else
  _info "Téléchargement de $CV_YOLO_MODEL…"
  if [[ -f "scripts/download-yolo-model.sh" ]]; then
    YOLO_MODEL="$CV_YOLO_MODEL" bash scripts/download-yolo-model.sh 2>>"${LOG_FILE:-/dev/null}" \
      && _ok "$CV_YOLO_MODEL téléchargé" \
      || _warn "Téléchargement de $CV_YOLO_MODEL échoué"
  else
    _warn "scripts/download-yolo-model.sh introuvable"
  fi
fi

# Toujours s'assurer que yolov8n.onnx est présent (fallback universel)
if [[ "$CV_YOLO_MODEL" != "yolov8n.onnx" ]] && [[ ! -f "ai-engine/models/yolov8n.onnx" ]]; then
  _info "Téléchargement du modèle de secours yolov8n.onnx…"
  YOLO_MODEL="yolov8n.onnx" bash scripts/download-yolo-model.sh 2>>"${LOG_FILE:-/dev/null}" \
    && _ok "yolov8n.onnx (fallback) téléchargé" \
    || _warn "Téléchargement yolov8n.onnx échoué — download-yolo-model.sh requis manuellement"
fi

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
