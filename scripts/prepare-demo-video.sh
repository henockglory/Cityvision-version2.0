#!/usr/bin/env bash
# Réencode benedicte.mp4 pour streaming temps réel : 25 fps CFR, 0 B-frames, NVENC si RTX disponible.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SOURCE="${BENEDICTE_SRC:-/mnt/c/Users/gheno/Videos/benedicte.mp4}"
RAW="$ROOT/data/videos/benedicte.mp4"
STREAM="$ROOT/data/videos/benedicte_stream.mp4"
TARGET_FPS="${STREAM_FPS:-25}"
FORCE="${FORCE_REENCODE:-0}"

mkdir -p "$ROOT/data/videos"

if [[ ! -f "$RAW" || ! -s "$RAW" ]]; then
  if [[ -f "$SOURCE" ]]; then
    cp "$SOURCE" "$RAW"
  else
    echo "[FAIL] Source introuvable: $SOURCE" >&2
    exit 1
  fi
fi

count_bframes() {
  ffprobe -v error -select_streams v:0 -show_frames -show_entries frame=pict_type \
    -of csv=p=0 "$1" 2>/dev/null | awk '$1=="B"{c++} END{print c+0}'
}

stream_fps() {
  ffprobe -v error -select_streams v:0 -show_entries stream=r_frame_rate -of csv=p=0 "$1" 2>/dev/null
}

NEED_ENCODE=1
if [[ "$FORCE" != "1" && -f "$STREAM" && -s "$STREAM" ]]; then
  B=$(count_bframes "$STREAM")
  FPS=$(stream_fps "$STREAM")
  if [[ "$B" -eq 0 && "$FPS" == "$TARGET_FPS/1" ]]; then
    echo "[OK] benedicte_stream.mp4 déjà prêt ($STREAM, ${TARGET_FPS}fps, 0 B-frames)"
    NEED_ENCODE=0
  fi
fi

pick_encoder() {
  if ffmpeg -hide_banner -encoders 2>&1 | grep -q h264_nvenc; then
    if nvidia-smi >/dev/null 2>&1; then
      echo "nvenc"
      return
    fi
  fi
  echo "x264"
}

if [[ "$NEED_ENCODE" -eq 1 ]]; then
  B_RAW=$(count_bframes "$RAW")
  ENC=$(pick_encoder)
  echo "==> Réencodage RTSP-friendly (B-frames source: $B_RAW → 0, ${TARGET_FPS} fps CFR, encoder=$ENC)"

  if [[ "$ENC" == "nvenc" ]]; then
    ffmpeg -y -hide_banner -loglevel warning \
      -hwaccel cuda -hwaccel_output_format cuda -i "$RAW" \
      -c:v h264_nvenc -preset p4 -tune ll -rc cbr -b:v 5M -maxrate 5M -bufsize 10M \
      -bf 0 -g "$TARGET_FPS" -keyint_min "$TARGET_FPS" -forced-idr 1 \
      -r "$TARGET_FPS" -fps_mode cfr -pix_fmt yuv420p \
      -movflags +faststart -an \
      "$STREAM"
  else
    ffmpeg -y -hide_banner -loglevel warning -i "$RAW" \
      -c:v libx264 -preset veryfast -tune zerolatency \
      -bf 0 -g "$TARGET_FPS" -keyint_min "$TARGET_FPS" -sc_threshold 0 \
      -r "$TARGET_FPS" -fps_mode cfr -pix_fmt yuv420p -movflags +faststart \
      -an \
      "$STREAM"
  fi

  B_OUT=$(count_bframes "$STREAM")
  FPS_OUT=$(stream_fps "$STREAM")
  if [[ "$B_OUT" -ne 0 ]]; then
    echo "[FAIL] Encodage a encore $B_OUT B-frames" >&2
    exit 1
  fi
  if [[ "$FPS_OUT" != "$TARGET_FPS/1" ]]; then
    echo "[FAIL] FPS attendu ${TARGET_FPS}/1, obtenu $FPS_OUT" >&2
    exit 1
  fi
  echo "[OK] benedicte_stream.mp4 créé ($(du -h "$STREAM" | cut -f1), ${TARGET_FPS}fps, encoder=$ENC)"
fi

DUR=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$STREAM")
FPS=$(stream_fps "$STREAM")
echo "[OK] duration=${DUR}s fps=$FPS path=$STREAM"
