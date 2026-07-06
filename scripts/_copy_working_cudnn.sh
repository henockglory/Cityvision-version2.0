#!/usr/bin/env bash
set -euo pipefail
SRC=/home/gheno/.citevision-v2/ai-engine-venv/lib/python3.12/site-packages/nvidia/cudnn/lib
DST=/home/gheno/citevision-v2/ai-engine/.venv/lib/python3.12/site-packages/nvidia/cudnn/lib
ALT=/mnt/c/Users/gheno/citevision/ai-engine/.venv/lib/python3.12/site-packages/nvidia/cudnn/lib
if [[ ! -f "$SRC/libcudnn.so.9" ]]; then
  SRC="$ALT"
fi
echo "Copy from $SRC -> $DST"
cp -a "$SRC"/. "$DST"/
md5sum "$DST/libcudnn.so.9" "$SRC/libcudnn.so.9"
cd /home/gheno/citevision-v2
bash scripts/_test_cuda_cu12_only.sh
