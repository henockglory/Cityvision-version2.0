#!/usr/bin/env bash
# WSL / drvfs helpers — source from other scripts (requires ROOT set)

is_drvfs_path() {
  local p="$1"
  [[ "$p" == /mnt/* ]]
}

is_drvfs_root() {
  is_drvfs_path "${ROOT:-}"
}

venv_on_drvfs() {
  local cfg="${ROOT}/ai-engine/.venv/pyvenv.cfg"
  [[ -f "$cfg" ]] && grep -q '/mnt/' "$cfg" 2>/dev/null
}

ensure_venv_not_on_drvfs() {
  if venv_on_drvfs; then
    echo "[FIX] Venv sur drvfs (/mnt/*) — recréation pour perf pip/IA…"
    rm -rf "${ROOT}/ai-engine/.venv"
    rm -f "${ROOT}/ai-engine/.venv/.installed_ok"
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
