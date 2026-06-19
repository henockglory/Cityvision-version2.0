#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# CitéVision v2 — Linux Native Bootstrap
# Installe toutes les dépendances sur une machine Linux vierge.
#
# Usage: bash installer/linux/bootstrap.sh [--silent] [--log-file=<path>]
# Supporte: Ubuntu/Debian, Fedora/RHEL/CentOS, Arch Linux
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

SILENT=false
LOG_FILE=""

for arg in "$@"; do
  case "$arg" in
    --silent)       SILENT=true ;;
    --log-file=*)   LOG_FILE="${arg#*=}" ;;
    --help)
      echo "Usage: bash installer/linux/bootstrap.sh [--silent] [--log-file=<path>]"
      exit 0 ;;
  esac
done

# ── Logging ──────────────────────────────────────────────────────────────────
_log()   {
  if [ -n "$LOG_FILE" ]; then echo "$1" | tee -a "$LOG_FILE"
  else echo "$1"; fi
}
_info()  { $SILENT || _log "[INFO] $1"; [ -n "$LOG_FILE" ] && echo "[INFO] $1" >>"$LOG_FILE" 2>/dev/null || true; }
_ok()    { _log "[OK]   $1"; }
_warn()  { _log "[WARN] $1"; }
_error() { _log "[ERR]  $1"; }
_step()  { _log ""; _log "=== $1 ==="; }

if [ -n "$LOG_FILE" ]; then
  mkdir -p "$(dirname "$LOG_FILE")"
  echo "# CitéVision v2 Linux Bootstrap — $(date)" > "$LOG_FILE"
fi

# ── Détecter la distribution ─────────────────────────────────────────────────
DISTRO="unknown"
PKG_MANAGER="unknown"

if command -v apt-get &>/dev/null; then
  DISTRO="debian"
  PKG_MANAGER="apt"
elif command -v dnf &>/dev/null; then
  DISTRO="fedora"
  PKG_MANAGER="dnf"
elif command -v yum &>/dev/null; then
  DISTRO="rhel"
  PKG_MANAGER="yum"
elif command -v pacman &>/dev/null; then
  DISTRO="arch"
  PKG_MANAGER="pacman"
fi

_log "=== CitéVision v2 Linux Bootstrap ==="
_log "Distribution détectée: $DISTRO (gestionnaire: $PKG_MANAGER)"
_log ""

CURRENT_USER="${SUDO_USER:-$USER}"

# ── Helpers install ───────────────────────────────────────────────────────────
pkg_install() {
  case "$PKG_MANAGER" in
    apt)    sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq "$@" 2>>"${LOG_FILE:-/dev/null}" ;;
    dnf)    sudo dnf install -y -q "$@" 2>>"${LOG_FILE:-/dev/null}" ;;
    yum)    sudo yum install -y -q "$@" 2>>"${LOG_FILE:-/dev/null}" ;;
    pacman) sudo pacman -S --noconfirm --needed "$@" 2>>"${LOG_FILE:-/dev/null}" ;;
    *)      _error "Gestionnaire de paquets non supporté: $PKG_MANAGER"; return 1 ;;
  esac
}

pkg_update() {
  case "$PKG_MANAGER" in
    apt)    sudo apt-get update -qq 2>>"${LOG_FILE:-/dev/null}" ;;
    dnf)    sudo dnf check-update -q 2>>"${LOG_FILE:-/dev/null}" || true ;;
    yum)    sudo yum check-update -q 2>>"${LOG_FILE:-/dev/null}" || true ;;
    pacman) sudo pacman -Sy --noconfirm 2>>"${LOG_FILE:-/dev/null}" ;;
  esac
}

# ══════════════════════════════════════════════════════════════════════════════
# 1. Paquets de base (curl, git, build tools)
# ══════════════════════════════════════════════════════════════════════════════
_step "Paquets système de base"
_info "Mise à jour des dépôts..."
pkg_update || true

case "$PKG_MANAGER" in
  apt)
    pkg_install curl wget git ca-certificates gnupg lsb-release \
      build-essential pkg-config software-properties-common apt-transport-https
    ;;
  dnf|yum)
    pkg_install curl wget git ca-certificates gnupg \
      gcc gcc-c++ make cmake pkgconfig
    ;;
  pacman)
    pkg_install curl wget git base-devel cmake pkg-config
    ;;
esac
_ok "Paquets de base installés"

# ══════════════════════════════════════════════════════════════════════════════
# 2. Docker
# ══════════════════════════════════════════════════════════════════════════════
_step "Docker Engine"
if command -v docker &>/dev/null; then
  _info "Docker déjà présent — $(docker --version)"
else
  _info "Installation de Docker Engine..."
  case "$PKG_MANAGER" in
    apt)
      # Docker officiel via get.docker.com
      curl -fsSL https://get.docker.com | sudo sh 2>>"${LOG_FILE:-/dev/null}"
      ;;
    dnf)
      sudo dnf config-manager --add-repo https://download.docker.com/linux/fedora/docker-ce.repo 2>>"${LOG_FILE:-/dev/null}" || true
      pkg_install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
      ;;
    yum)
      sudo yum-config-manager --add-repo https://download.docker.com/linux/centos/docker-ce.repo 2>>"${LOG_FILE:-/dev/null}" || true
      pkg_install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
      ;;
    pacman)
      pkg_install docker docker-compose
      ;;
  esac
  _ok "Docker Engine installé"
fi

# Docker Compose v2 (plugin)
if ! docker compose version &>/dev/null 2>&1; then
  _info "Installation docker-compose-plugin..."
  case "$PKG_MANAGER" in
    apt)    pkg_install docker-compose-plugin ;;
    dnf|yum) pkg_install docker-compose-plugin ;;
    pacman) pkg_install docker-compose ;;
  esac
fi
_ok "Docker Compose v2 disponible"

# Groupe docker
_info "Ajout de $CURRENT_USER au groupe docker..."
sudo usermod -aG docker "$CURRENT_USER" 2>/dev/null || true

# Démarrer et activer Docker
if command -v systemctl &>/dev/null; then
  sudo systemctl enable docker 2>/dev/null || true
  sudo systemctl start docker 2>/dev/null || \
    _warn "Docker daemon start échoué — lancez: sudo systemctl start docker"
elif command -v service &>/dev/null; then
  sudo service docker start 2>/dev/null || \
    _warn "Docker daemon start échoué (service) — essayez: sudo service docker start"
fi
_ok "Docker daemon démarré"

# nvidia-docker2 si GPU NVIDIA présent
if command -v nvidia-smi &>/dev/null 2>&1; then
  _step "NVIDIA Container Toolkit"
  if ! dpkg -l nvidia-container-toolkit &>/dev/null 2>&1 && \
     ! rpm -q nvidia-container-toolkit &>/dev/null 2>&1; then
    _info "GPU NVIDIA détecté — installation du NVIDIA Container Toolkit..."
    case "$PKG_MANAGER" in
      apt)
        distribution="$(. /etc/os-release; echo "$ID$VERSION_ID")"
        curl -fsSL "https://nvidia.github.io/libnvidia-container/gpgkey" \
          | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg 2>/dev/null || true
        curl -fsSL "https://nvidia.github.io/libnvidia-container/$distribution/libnvidia-container.list" \
          | sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' \
          | sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list >/dev/null
        sudo apt-get update -qq 2>>"${LOG_FILE:-/dev/null}" || true
        pkg_install nvidia-container-toolkit
        sudo nvidia-ctk runtime configure --runtime=docker 2>/dev/null || true
        sudo systemctl restart docker 2>/dev/null || true
        _ok "nvidia-container-toolkit installé"
        ;;
      dnf|yum)
        distribution="$(. /etc/os-release; echo "$ID$VERSION_ID")"
        curl -fsSL "https://nvidia.github.io/libnvidia-container/$distribution/libnvidia-container.repo" \
          | sudo tee /etc/yum.repos.d/nvidia-container-toolkit.repo >/dev/null
        pkg_install nvidia-container-toolkit
        sudo nvidia-ctk runtime configure --runtime=docker 2>/dev/null || true
        sudo systemctl restart docker 2>/dev/null || true
        _ok "nvidia-container-toolkit installé"
        ;;
      *)
        _warn "Installation automatique nvidia-container-toolkit non supportée sur $DISTRO — installez manuellement"
        ;;
    esac
  else
    _info "nvidia-container-toolkit déjà présent"
  fi
fi

# ══════════════════════════════════════════════════════════════════════════════
# 3. Go 1.22+
# ══════════════════════════════════════════════════════════════════════════════
_step "Go 1.22+"
if command -v go &>/dev/null; then
  GO_VER="$(go version | grep -oP 'go\K[\d.]+')"
  MAJOR="$(echo "$GO_VER" | cut -d. -f1)"
  MINOR="$(echo "$GO_VER" | cut -d. -f2)"
  if [ "${MAJOR:-0}" -gt 1 ] || { [ "${MAJOR:-0}" -eq 1 ] && [ "${MINOR:-0}" -ge 22 ]; }; then
    _info "Go $GO_VER déjà présent et suffisant"
  else
    _warn "Go $GO_VER trop ancien — mise à jour..."
    sudo rm -rf /usr/local/go
    curl -fsSL https://go.dev/dl/go1.22.5.linux-amd64.tar.gz | sudo tar -C /usr/local -xz
    _ok "Go 1.22.5 installé"
  fi
else
  _info "Installation de Go 1.22.5..."
  curl -fsSL https://go.dev/dl/go1.22.5.linux-amd64.tar.gz | sudo tar -C /usr/local -xz
  _ok "Go 1.22.5 installé"
fi

# Ajouter Go au PATH si nécessaire
for RC in "$HOME/.bashrc" "$HOME/.profile" "$HOME/.zshrc"; do
  if [ -f "$RC" ] && ! grep -q '/usr/local/go/bin' "$RC"; then
    echo 'export PATH=$PATH:/usr/local/go/bin' >>"$RC"
  fi
done
export PATH="$PATH:/usr/local/go/bin"

# ══════════════════════════════════════════════════════════════════════════════
# 4. Node.js 20+
# ══════════════════════════════════════════════════════════════════════════════
_step "Node.js 20+"
NODE_OK=false
if command -v node &>/dev/null; then
  NODE_MAJ="$(node -e 'process.stdout.write(process.versions.node.split(".")[0])' 2>/dev/null || echo 0)"
  if [ "${NODE_MAJ:-0}" -ge 20 ]; then
    _info "Node.js $(node -v) déjà présent"
    NODE_OK=true
  else
    _warn "Node.js $(node -v) trop ancien — mise à jour..."
  fi
fi

if ! $NODE_OK; then
  _info "Installation de Node.js 20 LTS..."
  case "$PKG_MANAGER" in
    apt)
      curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash - 2>>"${LOG_FILE:-/dev/null}"
      pkg_install nodejs
      ;;
    dnf|yum)
      curl -fsSL https://rpm.nodesource.com/setup_20.x | sudo bash - 2>>"${LOG_FILE:-/dev/null}"
      pkg_install nodejs
      ;;
    pacman)
      pkg_install nodejs npm
      ;;
  esac
  _ok "Node.js $(node -v) installé"
fi

# ══════════════════════════════════════════════════════════════════════════════
# 5. Python 3.12+
# ══════════════════════════════════════════════════════════════════════════════
_step "Python 3.12+"
PYTHON_OK=false
for PY_CMD in python3.12 python3 python; do
  if command -v "$PY_CMD" &>/dev/null; then
    PY_VER="$($PY_CMD --version 2>&1 | grep -oP '[\d]+\.[\d]+' | head -1)"
    PY_MAJ="$(echo "$PY_VER" | cut -d. -f1)"
    PY_MIN="$(echo "$PY_VER" | cut -d. -f2)"
    if [ "${PY_MAJ:-0}" -ge 3 ] && [ "${PY_MIN:-0}" -ge 12 ]; then
      _info "Python $PY_VER présent ($PY_CMD)"
      PYTHON_OK=true
      break
    fi
  fi
done

if ! $PYTHON_OK; then
  _info "Installation de Python 3.12..."
  case "$PKG_MANAGER" in
    apt)
      sudo add-apt-repository -y ppa:deadsnakes/ppa 2>>"${LOG_FILE:-/dev/null}" || true
      sudo apt-get update -qq 2>>"${LOG_FILE:-/dev/null}" || true
      pkg_install python3.12 python3.12-venv python3.12-dev python3-pip
      ;;
    dnf)
      pkg_install python3.12 python3.12-devel python3-pip
      ;;
    yum)
      # EPEL + IUS repository
      pkg_install epel-release 2>/dev/null || true
      pkg_install python312 python312-devel
      ;;
    pacman)
      pkg_install python python-pip
      ;;
  esac
  _ok "Python 3.12 installé"
fi

# ══════════════════════════════════════════════════════════════════════════════
# 6. FFmpeg
# ══════════════════════════════════════════════════════════════════════════════
_step "FFmpeg"
if command -v ffmpeg &>/dev/null; then
  _info "FFmpeg déjà présent — $(ffmpeg -version 2>&1 | head -1)"
else
  _info "Installation de FFmpeg..."
  case "$PKG_MANAGER" in
    apt)    pkg_install ffmpeg ;;
    dnf)    sudo dnf install -y ffmpeg --allowerasing 2>>"${LOG_FILE:-/dev/null}" || pkg_install ffmpeg ;;
    yum)    pkg_install ffmpeg ;;
    pacman) pkg_install ffmpeg ;;
  esac
  _ok "FFmpeg installé"
fi

# ══════════════════════════════════════════════════════════════════════════════
# 7. cmake, build-essential
# ══════════════════════════════════════════════════════════════════════════════
_step "cmake & outils de compilation"
if command -v cmake &>/dev/null; then
  _info "cmake déjà présent — $(cmake --version | head -1)"
else
  case "$PKG_MANAGER" in
    apt)    pkg_install cmake build-essential ;;
    dnf|yum) pkg_install cmake gcc-c++ make ;;
    pacman) pkg_install cmake base-devel ;;
  esac
  _ok "cmake installé"
fi

# ══════════════════════════════════════════════════════════════════════════════
# Résumé
# ══════════════════════════════════════════════════════════════════════════════
_log ""
_ok "Bootstrap Linux terminé"
_log ""
_warn "IMPORTANT: Pour que Docker soit utilisable sans sudo, déconnectez-vous et reconnectez-vous"
_warn "  ou lancez: newgrp docker"
_log ""
_log "Prochaines étapes:"
_log "  1. newgrp docker    (ou se déconnecter/reconnecter)"
_log "  2. bash scripts/setup-wsl.sh"
_log "  3. bash scripts/start-all.sh"
_log ""

exit 0
