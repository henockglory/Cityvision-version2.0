#!/usr/bin/env bash
set -e
CVDIR=$(ls /mnt/c/ | python3 -c "import sys; lines=[l.rstrip() for l in sys.stdin]; r=[l for l in lines if 'Vision' in l and 'itch' not in l and len(l)<15]; print(r[0] if r else '')")
if [ -z "$CVDIR" ]; then echo "[ERR] not found"; exit 1; fi
CVPATH="/mnt/c/$CVDIR"
echo "[INFO] $CVPATH"
PIP="$CVPATH/ai-engine/.venv/bin/pip"
[ -x "$PIP" ] || { echo "[ERR] no pip"; exit 1; }
"$PIP" install --quiet requests boto3 minio
"$PIP" install --quiet -e "$CVPATH/ai-engine/.[identity,anpr,dev]"
echo "[OK] Done"