#!/usr/bin/env bash
# Phase A Tâche 10 — fstrim explicite + rappel ZoneEditor humain
set -euo pipefail
echo "=== fstrim (explicit — systemd timer inactive under this WSL) ==="
if command -v fstrim >/dev/null 2>&1; then
  # may need sudo
  if sudo -n fstrim -v / 2>/tmp/fstrim.out; then
    cat /tmp/fstrim.out
    echo "FSTRIM_OK"
  else
    echo "sudo fstrim requires password — attempting without -n"
    sudo fstrim -v / 2>&1 | tee /tmp/fstrim.out || {
      echo "FSTRIM_BLOCKED: run manually: sudo fstrim -v /"
      exit 0
    }
  fi
else
  echo "fstrim binary missing"
fi

echo "=== ZoneEditor human confirmation (REQUIRED — no auto geometry) ==="
cat <<'EOF'
ACTION HUMAINE REQUISE (P.135 / A.1):
1. Ouvrir UI → Éditeur de zones sur chaque caméra démo (Feux, Vitesse, Cabine, Comptage).
2. Vérifier polygones/lignes/distances = intention utilisateur (pas de seed _fix_zone_*).
3. Confirmer oralement ou noter dans le journal: "zones confirmées ZoneEditor YYYY-MM-DD".

Agent: ne pas écrire la géométrie en DB automatiquement.
EOF
echo "T10_FSTRIM_DONE_ZONEEDITOR_PENDING_HUMAN"
