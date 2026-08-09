#!/usr/bin/env bash
# Purge Frigate recordings / MinIO evidence older than FRIGATE_DEMO_RETENTION_MIN (default 30).
# Intended cron: */30 * * * *
set -euo pipefail

ROOT="${CITEVISION_ROOT:-$HOME/citevision-v2}"
RETAIN_MIN="${FRIGATE_DEMO_RETENTION_MIN:-30}"
LOGDIR="$ROOT/logs"
LOG="$LOGDIR/demo-retention-purge.log"
mkdir -p "$LOGDIR"

log() { echo "[$(date -Iseconds)] $*" | tee -a "$LOG"; }

freed_before=0
freed_after=0
du_bytes() {
  local p="$1"
  if [[ -d "$p" ]]; then
    sudo du -sb "$p" 2>/dev/null | awk '{print $1}' || echo 0
  else
    echo 0
  fi
}

RECORDINGS="/var/lib/docker/volumes/infra_frigate_recordings/_data"
CLIPS="/var/lib/docker/volumes/infra_frigate_clips/_data"
MINIO_EVIDENCE="/var/lib/docker/volumes/infra_minio_data/_data/citevision-evidence"

log "=== demo retention purge (keep ${RETAIN_MIN}m) ==="
freed_before=$(du_bytes "$RECORDINGS")

# Frigate continuous segments + event clips on disk
for dir in "$RECORDINGS" "$CLIPS"; do
  if [[ -d "$dir" ]]; then
    n=$(sudo find "$dir" -type f -mmin "+${RETAIN_MIN}" -print -delete 2>/dev/null | wc -l || echo 0)
    sudo find "$dir" -type d -empty -delete 2>/dev/null || true
    log "  $(basename "$(dirname "$dir")")/$(basename "$dir"): deleted ${n} file(s) older than ${RETAIN_MIN}m"
  fi
done

# MinIO evidence objects (JPEG/MP4 per alert)
if [[ -d "$MINIO_EVIDENCE" ]]; then
  n=$(sudo find "$MINIO_EVIDENCE" -type f -mmin "+${RETAIN_MIN}" -print -delete 2>/dev/null | wc -l || echo 0)
  sudo find "$MINIO_EVIDENCE" -type d -empty -delete 2>/dev/null || true
  log "  minio citevision-evidence: deleted ${n} file(s) older than ${RETAIN_MIN}m"
fi

freed_after=$(du_bytes "$RECORDINGS")
freed_mb=$(( (freed_before - freed_after) / 1024 / 1024 ))
log "  recordings size delta: ~${freed_mb} MB"

# Rotate bulky app logs so Cursor/WSL stay light (tests keep recent tails).
rotate_log() {
  local f="$1"
  local max_mb="${2:-80}"
  [[ -f "$f" ]] || return 0
  local sz_mb
  sz_mb=$(du -m "$f" 2>/dev/null | awk '{print $1}')
  [[ "${sz_mb:-0}" -ge "$max_mb" ]] || return 0
  local bak="${f}.$(date -u +%Y%m%dT%H%M%SZ).bak"
  mv -f "$f" "$bak" 2>/dev/null || return 0
  : >"$f"
  # keep last 3 rotated copies of this basename
  local dir base
  dir="$(dirname "$f")"
  base="$(basename "$f")"
  ls -1t "$dir"/"${base}".*.bak 2>/dev/null | tail -n +4 | xargs -r rm -f --
  log "  rotated $(basename "$f") (~${sz_mb}MB) -> $(basename "$bak")"
}

rotate_log "$LOGDIR/ai-engine.log" 64
rotate_log "$LOGDIR/backend.log" 32
rotate_log "$LOGDIR/rules-engine.log" 32
# Drop stale chain-smoke nohup / campaign logs older than 3 days
if [[ -d "$LOGDIR" ]]; then
  n=$(find "$LOGDIR" -maxdepth 1 -type f \( -name 'chain-smoke-*.log' -o -name 'chain-smoke-*.md' \) -mtime +3 -print -delete 2>/dev/null | wc -l || echo 0)
  log "  chain-smoke logs deleted (age>3d): ${n}"
fi
# Cap validation-evidence chain-smoke dirs (keep 8 newest)
if [[ -d "$ROOT/validation-evidence" ]]; then
  mapfile -t _cs < <(ls -1dt "$ROOT"/validation-evidence/chain-smoke-* 2>/dev/null || true)
  if [[ ${#_cs[@]} -gt 8 ]]; then
    for d in "${_cs[@]:8}"; do
      rm -rf "$d" 2>/dev/null || true
      log "  pruned old evidence $(basename "$d")"
    done
  fi
fi

if command -v fstrim >/dev/null 2>&1; then
  sudo fstrim -av >>"$LOG" 2>&1 || true
fi

log "=== done ==="
