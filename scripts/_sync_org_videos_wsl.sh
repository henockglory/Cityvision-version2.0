#!/usr/bin/env bash
set -euo pipefail
ORG="74d51ead-97a7-4e41-a488-503a9b90c466"
SRC="/mnt/c/Users/gheno/citevision/data/videos/demo/${ORG}"
DST="/home/gheno/citevision-v2/data/videos/demo/${ORG}"
mkdir -p "$DST"
if [[ ! -d "$SRC" ]]; then
  echo "[FAIL] Source missing: $SRC" >&2
  exit 1
fi
cp -av "$SRC"/*_stream.mp4 "$DST"/
echo "[OK] Copied to $DST"
ls -lah "$DST"
docker exec citevision-v2-go2rtc ls -lah "/videos/demo/${ORG}/"
