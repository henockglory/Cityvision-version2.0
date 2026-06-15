#!/usr/bin/env bash
# Valide fluidité RTSP : débit stable, timing 1:1, pas de B-frames.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RTSP="${RTSP_URL:-rtsp://127.0.0.1:8554/benedicte}"
DURATION="${SMOOTH_TEST_SEC:-30}"
OUT="$ROOT/logs/smooth-test-$$.ts"
MIN_FPS="${SMOOTH_MIN_FPS:-24}"

echo "==> Validation fluidité RTSP ($DURATION s) — $RTSP"

bash "$ROOT/scripts/validate-video-playback.sh" || exit 1

mkdir -p "$ROOT/logs"
rm -f "$OUT"

echo "==> Enregistrement $DURATION s…"
ffmpeg -y -hide_banner -loglevel error \
  -rtsp_transport tcp -i "$RTSP" -t "$DURATION" -c copy -an "$OUT"

if [[ ! -f "$OUT" || ! -s "$OUT" ]]; then
  echo "[FAIL] Enregistrement RTSP vide" >&2
  exit 1
fi

python3 - "$OUT" "$DURATION" "$MIN_FPS" <<'PY'
import subprocess, sys, json

out, duration_s, min_fps = sys.argv[1], float(sys.argv[2]), float(sys.argv[3])

info = subprocess.run(
    ["ffprobe", "-v", "error", "-select_streams", "v:0",
     "-count_frames", "-show_entries", "stream=nb_read_frames,duration,r_frame_rate",
     "-of", "json", out],
    capture_output=True, text=True, check=True,
)
stream = json.loads(info.stdout)["streams"][0]
frames = int(stream.get("nb_read_frames", 0))
span = float(stream.get("duration", 0))
rf = stream.get("r_frame_rate", "25/1")
num, den = rf.split("/")
nominal = float(num) / float(den) if float(den) else 25.0
fps = frames / span if span > 0 else 0

proc = subprocess.run(
    ["ffprobe", "-v", "error", "-select_streams", "v:0",
     "-show_frames", "-show_entries", "frame=pict_type",
     "-of", "csv=p=0", out],
    capture_output=True, text=True, check=True,
)
b_count = sum(1 for line in proc.stdout.splitlines() if line.strip() == "B")

print(f"  frames={frames} span={span:.2f}s fps={fps:.1f} nominal={nominal:.1f} B-frames={b_count}")

if frames < 10:
    print("[FAIL] Trop peu de frames")
    sys.exit(1)
if b_count > 0:
    print(f"[FAIL] {b_count} B-frames dans flux RTSP")
    sys.exit(1)
if fps < min_fps:
    print(f"[FAIL] FPS effectif {fps:.1f} < {min_fps}")
    sys.exit(1)
ratio = span / duration_s
if ratio < 0.92 or ratio > 1.08:
    print(f"[FAIL] Timing drift: {span:.1f}s vs {duration_s}s attendu (ratio={ratio:.2f})")
    sys.exit(1)
expected = duration_s * nominal
if abs(frames - expected) / expected > 0.08:
    print(f"[FAIL] Frame count {frames} vs ~{expected:.0f} attendu")
    sys.exit(1)

print("[OK] Flux RTSP fluide — débit et timing stables (type VLC)")
PY

rm -f "$OUT"
echo "[OK] validate-video-smooth passed"
