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

if command -v fstrim >/dev/null 2>&1; then
  sudo fstrim -av >>"$LOG" 2>&1 || true
fi

log "=== done ==="
