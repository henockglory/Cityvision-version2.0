#!/usr/bin/env bash
set -uo pipefail
OUT=/mnt/c/Users/gheno/citevision/scripts/_diag
mkdir -p "$OUT"
V=/mnt/c/Users/gheno/citevision/data/videos/demo/74d51ead-97a7-4e41-a488-503a9b90c466/aaea7c30-1c4c-4ce5-9cd6-4b1f8ded4118_stream.mp4
echo "dims: $(ffprobe -v error -select_streams v:0 -show_entries stream=width,height,duration -of csv=p=0 "$V")"
for t in 3 15 30 45 60; do
  ffmpeg -y -ss "$t" -i "$V" -frames:v 1 -vf "crop=in_w*0.235:in_h*0.205:in_w*0.679:in_h*0.079" "$OUT/light_${t}.png" >/dev/null 2>&1 && echo "light_${t}.png ok"
  ffmpeg -y -ss "$t" -i "$V" -frames:v 1 -vf "scale=960:-1" "$OUT/full_${t}.png" >/dev/null 2>&1 && echo "full_${t}.png ok"
done
