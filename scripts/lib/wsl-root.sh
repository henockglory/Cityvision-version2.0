#!/usr/bin/env bash
# WSL / drvfs helpers — source from other scripts (requires ROOT set)

is_drvfs_path() {
  local p="$1"
  [[ "$p" == /mnt/* ]]
}

is_drvfs_root() {
  is_drvfs_path "${ROOT:-}"
}

# Chemin réel du venv : ext4 local si projet sur /mnt/c
resolve_venv_dir() {
  if is_drvfs_root; then
    echo "${HOME}/.citevision-v2/ai-engine-venv"
  else
    echo "${ROOT}/ai-engine/.venv"
  fi
}

_venv_link_path() {
  echo "${ROOT}/ai-engine/.venv"
}

venv_on_drvfs() {
  local venv
  venv="$(_venv_link_path)"
  if [[ -L "$venv" ]]; then
    local target
    target="$(readlink -f "$venv" 2>/dev/null || readlink "$venv" 2>/dev/null || true)"
    is_drvfs_path "$target"
    return $?
  fi
  local cfg="${venv}/pyvenv.cfg"
  [[ -f "$cfg" ]] && grep -q '/mnt/' "$cfg" 2>/dev/null
}

ensure_venv_not_on_drvfs() {
  local link ext4_venv
  link="$(_venv_link_path)"
  ext4_venv="$(resolve_venv_dir)"

  if [[ "$ext4_venv" == "$link" ]]; then
    if venv_on_drvfs; then
      echo "[FIX] Venv sur drvfs (/mnt/*) — recréation…"
      rm -rf "$link"
      rm -f "$link/.installed_ok"
    fi
    return 0
  fi

  # Projet sur drvfs : venv physique sur ext4, lien ai-engine/.venv
  if [[ -d "$link" ]] && ! [[ -L "$link" ]] && venv_on_drvfs; then
    echo "[FIX] Migration venv drvfs → ext4 ($ext4_venv)…"
    rm -rf "$link"
    rm -f "${ROOT}/ai-engine/.venv/.installed_ok"
  fi

  mkdir -p "$(dirname "$ext4_venv")"
  if [[ -L "$link" ]]; then
    local cur
    cur="$(readlink -f "$link" 2>/dev/null || true)"
    if [[ "$cur" == "$ext4_venv" ]]; then
      return 0
    fi
    rm -f "$link"
  elif [[ -e "$link" ]]; then
    rm -rf "$link"
  fi

  if ln -sfn "$ext4_venv" "$link" 2>/dev/null; then
    echo "[INFO] venv IA sur ext4 : $ext4_venv"
  else
    echo "[WARN] Lien symbolique venv impossible — utilisation directe $ext4_venv"
  fi
}

write_build_version() {
  local out="${ROOT}/installer/.build_version"
  mkdir -p "${ROOT}/installer"
  if command -v git >/dev/null 2>&1 && git -C "$ROOT" rev-parse --short HEAD >/dev/null 2>&1; then
    git -C "$ROOT" rev-parse --short HEAD >"$out"
    date -u +"%Y-%m-%dT%H:%MZ" >>"$out"
  else
    date -u +"%Y-%m-%dT%H:%MZ" >"$out"
  fi
}
