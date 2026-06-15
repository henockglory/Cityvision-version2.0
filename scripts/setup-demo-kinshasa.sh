#!/usr/bin/env bash
# Démo complète CitéVision — Ministère Urbanisme & Transport, Kinshasa
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
# shellcheck source=scripts/lib/env-utils.sh
source "$ROOT/scripts/lib/env-utils.sh"

DEMO_EMAIL="${DEMO_EMAIL:-glory.henock@hologram.cd}"
DEMO_PASS="${DEMO_PASS:-Hologram2026!}"
API_URL="${API_URL:-http://localhost:8081}"
VIDEO_SRC="${BENEDICTE_SRC:-/mnt/c/Users/gheno/Videos/benedicte.mp4}"
VIDEO_DST="$ROOT/data/videos/benedicte.mp4"

echo "╔══════════════════════════════════════════════════════════╗"
echo "║  CitéVision 2.0 — Démo Kinshasa (vidéo modèle)           ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""

echo "==> 1/8 Vidéo locale (ext4 — performances WSL)"
mkdir -p "$ROOT/data/videos"
if [[ -f "$VIDEO_DST" ]]; then
  echo "[OK] $VIDEO_DST exists"
elif [[ -f "$VIDEO_SRC" ]]; then
  cp "$VIDEO_SRC" "$VIDEO_DST"
  echo "[OK] Copied $VIDEO_SRC → $VIDEO_DST"
else
  echo "[WARN] benedicte.mp4 not found — place file at $VIDEO_DST"
fi

ENV_FILE="$(ensure_env_file "$ROOT")"
if grep -q '^VIDEOS_PATH=' "$ENV_FILE" 2>/dev/null; then
  sed -i "s|^VIDEOS_PATH=.*|VIDEOS_PATH=$ROOT/data/videos|" "$ENV_FILE" 2>/dev/null || \
    perl -pi -e "s|^VIDEOS_PATH=.*|VIDEOS_PATH=$ROOT/data/videos|" "$ENV_FILE"
else
  echo "VIDEOS_PATH=$ROOT/data/videos" >> "$ENV_FILE"
fi
export VIDEOS_PATH="$ROOT/data/videos"

echo ""
echo "==> 2/8 Modèle YOLO ONNX"
bash "$ROOT/scripts/export-yolo-onnx.sh" cuda

echo ""
echo "==> 3/8 Infrastructure + services"
bash "$ROOT/scripts/start-linux.sh"

echo ""
echo "==> 4/8 Mot de passe administrateur démo"
bash "$ROOT/scripts/reset-admin-password.sh" "$DEMO_PASS" "$DEMO_EMAIL"

echo ""
echo "==> 5/8 Caméra virtuelle (idempotent)"
export ADMIN_EMAIL="$DEMO_EMAIL" ADMIN_PASSWORD="$DEMO_PASS"
bash "$ROOT/scripts/register-virtual-camera.sh"

echo ""
echo "==> 6/8 Zones, lignes et règles de test"
export ADMIN_EMAIL="$DEMO_EMAIL" ADMIN_PASSWORD="$DEMO_PASS"
bash "$ROOT/scripts/seed-test-spatial.sh" || echo "[WARN] Seed spatial partiel"

echo ""
echo "==> 7/8 Vérification pipeline"
sleep 20
bash "$ROOT/scripts/validate-video-playback.sh"
curl -sf http://localhost:8001/health | python3 -m json.tool || echo "[WARN] AI health"

echo ""
echo "==> 8/8 Prêt"
echo ""
echo "  URL:          http://localhost:5174/demo"
echo "  Email:        $DEMO_EMAIL"
echo "  Mot de passe: $DEMO_PASS"
echo ""
echo "  Gate qualité: bash scripts/validate-commercial-gate.sh"
echo "  Vidéo directe: http://localhost:1984/stream.html?src=benedicte"
echo ""
