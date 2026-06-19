#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
git commit -F - <<'EOF'
Améliorer l'UX règles, preuves et mur vidéo pour des tests premium.

Catalogue règles avec hiérarchie visuelle groupe/sous-listes (dark et light), espacements unifiés et groupes fermés par défaut. Aperçu des preuves en modal centré, mur vidéo plein viewport, défilement indépendant Alertes/Événements restauré, et script de purge alertes/événements/MinIO.
EOF
