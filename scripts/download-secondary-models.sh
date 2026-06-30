#!/usr/bin/env bash
# Download + verify the secondary AI models (driver phone, seatbelt) declared in
# shared/ai-models.json. Verifies sha256 when pinned; warns (and records) when
# unpinned. Honest degradation: a failed/missing model is reported, never faked.
#
# Usage: bash scripts/download-secondary-models.sh [--fix]
#   --fix : re-download even if a file exists but fails its sha256.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REGISTRY="$ROOT/shared/ai-models.json"
DEST="$ROOT/ai-engine/models/secondary"
FIX=false
for arg in "$@"; do
  case "$arg" in
    --fix) FIX=true ;;
    --help) echo "Usage: bash scripts/download-secondary-models.sh [--fix]"; exit 0 ;;
  esac
done

PYTHON="$(command -v python3 || command -v python || echo python3)"
mkdir -p "$DEST"

if [[ ! -f "$REGISTRY" ]]; then
  echo "[ERR] Registry not found: $REGISTRY"
  exit 1
fi

# Emit "id|file|url|sha256" lines from the registry.
mapfile -t MODELS < <("$PYTHON" - "$REGISTRY" <<'PY'
import json, sys
data = json.load(open(sys.argv[1], encoding="utf-8"))
for m in data.get("models", []):
    print(f"{m.get('id','')}|{m.get('file','')}|{m.get('url','')}|{m.get('sha256','')}")
PY
)

sha256_of() {
  if command -v sha256sum >/dev/null 2>&1; then sha256sum "$1" | awk '{print $1}';
  else shasum -a 256 "$1" | awk '{print $1}'; fi
}

OK=0; FAIL=0
for line in "${MODELS[@]}"; do
  IFS='|' read -r id file url sha <<< "$line"
  [[ -z "$file" ]] && continue
  out="$DEST/$file"

  if [[ -f "$out" && "$FIX" == "false" ]]; then
    if [[ -n "$sha" ]]; then
      got="$(sha256_of "$out")"
      if [[ "$got" == "$sha" ]]; then echo "[OK] $id present + sha256 verified"; OK=$((OK+1)); continue;
      else echo "[WARN] $id sha256 mismatch (have $got) — re-downloading"; fi
    else
      echo "[OK] $id present (sha256 unpinned)"; OK=$((OK+1)); continue
    fi
  fi

  if [[ -z "$url" ]]; then
    if [[ -f "$out" ]]; then
      echo "[OK] $id present (built locally, no URL)"; OK=$((OK+1)); continue
    fi
    echo "[SKIP] $id has no URL — place $file manually in $DEST"; FAIL=$((FAIL+1)); continue
  fi

  echo "==> Downloading $id from $url"
  if curl -fSL --retry 3 -o "$out.tmp" "$url" 2>/dev/null; then
    mv "$out.tmp" "$out"
    got="$(sha256_of "$out")"
    if [[ -n "$sha" && "$got" != "$sha" ]]; then
      echo "[ERR] $id sha256 mismatch after download (have $got, want $sha) — removing"
      rm -f "$out"; FAIL=$((FAIL+1)); continue
    fi
    if [[ -z "$sha" ]]; then
      echo "[WARN] $id downloaded but sha256 UNPINNED. To freeze integrity, set sha256=$got in shared/ai-models.json"
    fi
    echo "[OK] $id ready ($got)"; OK=$((OK+1))
  else
    rm -f "$out.tmp"
    echo "[ERR] $id download failed — behavior will degrade honestly (emits nothing)"; FAIL=$((FAIL+1))
  fi
done

echo "==> Secondary models: $OK ok, $FAIL missing/failed"
# Non-fatal: the AI engine degrades honestly when a model is absent.
exit 0
