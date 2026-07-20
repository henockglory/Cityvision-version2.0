#!/usr/bin/env python3
"""
R7 - Setup WSL canonical workflow:
  1. Create a Cursor rule that enforces WSL-only edits
  2. Create a sync script sync-from-wsl.sh for Windows users who need to pull
  3. Update .cursor/rules/ with a reminder
  4. Update Makefile with wsl-sync target
  5. Document in WORKSPACE.md
"""
from pathlib import Path
import json

# ──────────────────────────────────────────────────────────────────────────────
# 1. Create .cursor/rules/wsl-canonical.mdc
# ──────────────────────────────────────────────────────────────────────────────
cursor_rules_dir = Path(".cursor/rules")
cursor_rules_dir.mkdir(parents=True, exist_ok=True)

wsl_rule = """---
description: WSL canonical workspace — edit files only in WSL ~/citevision-v2/
globs:
alwaysApply: true
---
# Source de vérité : WSL uniquement

Toutes les modifications de fichiers **doivent** se faire dans le répertoire WSL `~/citevision-v2/`.

## Règles strictes

1. **Ne jamais écrire directement** dans `C:\\Users\\gheno\\citevision-v2\\` (Windows mirror).
2. **Utiliser des scripts Python/bash** exécutés dans WSL pour toutes les modifications de code.
3. Après chaque batch de modifications WSL, exécuter `make sync-to-windows` pour mettre à jour le mirror Windows.
4. Le mirror Windows sert uniquement à Cursor IDE — **jamais** pour éditer directement.

## Commandes rapides

```bash
# Synchroniser WSL → Windows
make sync-to-windows

# Synchroniser Windows → WSL (urgence seulement)
make sync-from-windows

# Valider JSON avant de committer
python3 scripts/validate_json.py frontend/src/i18n/fr.json
```

## Conséquence d'une violation
Une désynchronisation entre Windows et WSL a causé une panne de login (fr.json invalide) en juin 2026.
Respecter cette règle élimine ce risque de manière permanente.
"""

wsl_rule_file = cursor_rules_dir / "wsl-canonical.mdc"
wsl_rule_file.write_text(wsl_rule, encoding="utf-8")
print(f"Created {wsl_rule_file}")

# ──────────────────────────────────────────────────────────────────────────────
# 2. Create scripts/sync-to-windows.sh
# ──────────────────────────────────────────────────────────────────────────────
sync_to_windows = """#!/usr/bin/env bash
# Synchronise WSL ~/citevision-v2/ → Windows C:/Users/gheno/citevision-v2/
# Exclut les artefacts volumineux (node_modules, .venv, *.pyc, build)
set -euo pipefail
SRC="$HOME/citevision-v2/"
DST="/mnt/c/Users/gheno/citevision-v2/"

if [ ! -d "$DST" ]; then
    echo "[WARN] Dossier Windows introuvable: $DST"
    exit 1
fi

echo "=== Sync WSL → Windows ==="
rsync -av --checksum --delete \\
    --exclude='.git/' \\
    --exclude='node_modules/' \\
    --exclude='.venv/' \\
    --exclude='__pycache__/' \\
    --exclude='*.pyc' \\
    --exclude='*.pyo' \\
    --exclude='.mypy_cache/' \\
    --exclude='dist/' \\
    --exclude='build/' \\
    --exclude='*.egg-info/' \\
    --exclude='models/*.onnx' \\
    "$SRC" "$DST"
echo "=== Sync terminé ==="
"""
sync_to_win_path = Path("scripts/sync-to-windows.sh")
sync_to_win_path.write_text(sync_to_windows, encoding="utf-8")
print(f"Created {sync_to_win_path}")

# ──────────────────────────────────────────────────────────────────────────────
# 3. Create scripts/sync-from-windows.sh (emergency pull)
# ──────────────────────────────────────────────────────────────────────────────
sync_from_windows = """#!/usr/bin/env bash
# URGENCE : Synchronise Windows → WSL (seulement si WSL est en retard)
# Utiliser uniquement quand nécessaire — WSL est la source de vérité !
set -euo pipefail
SRC="/mnt/c/Users/gheno/citevision-v2/"
DST="$HOME/citevision-v2/"

echo "[WARN] Vous êtes sur le point de remplacer des fichiers WSL par des fichiers Windows."
echo "[WARN] Cela devrait être TRÈS rare. WSL est la source de vérité."
read -r -p "Continuer? (oui/non): " yn
if [ "$yn" != "oui" ]; then
    echo "Annulé."
    exit 0
fi

echo "=== Sync Windows → WSL (urgence) ==="
rsync -av --checksum \\
    --exclude='.git/' \\
    --exclude='node_modules/' \\
    --exclude='.venv/' \\
    --exclude='__pycache__/' \\
    --exclude='*.pyc' \\
    --exclude='dist/' \\
    --exclude='build/' \\
    --exclude='models/*.onnx' \\
    "$SRC" "$DST"
echo "=== Sync terminé — valider les fichiers critiques ==="
python3 scripts/validate_json.py frontend/src/i18n/fr.json
"""
sync_from_win_path = Path("scripts/sync-from-windows.sh")
sync_from_win_path.write_text(sync_from_windows, encoding="utf-8")
print(f"Created {sync_from_win_path}")

# ──────────────────────────────────────────────────────────────────────────────
# 4. Update Makefile with sync targets
# ──────────────────────────────────────────────────────────────────────────────
makefile = Path("Makefile")
content = makefile.read_text(encoding="utf-8")

SYNC_TARGETS = """
# ── WSL ↔ Windows sync ────────────────────────────────────────────────────────
.PHONY: sync-to-windows sync-from-windows

sync-to-windows: ## Synchronise WSL → Windows mirror (post-édition WSL)
\tbash scripts/sync-to-windows.sh

sync-from-windows: ## Synchronise Windows → WSL (urgence seulement)
\tbash scripts/sync-from-windows.sh

"""

if "sync-to-windows" not in content:
    # Add before the last section or at end
    if ".PHONY: help" in content:
        content = content.replace(".PHONY: help", SYNC_TARGETS + ".PHONY: help")
    else:
        content += SYNC_TARGETS
    makefile.write_text(content, encoding="utf-8")
    print("Added sync targets to Makefile")
else:
    print("Makefile already has sync targets")

# ──────────────────────────────────────────────────────────────────────────────
# 5. Create WORKSPACE.md
# ──────────────────────────────────────────────────────────────────────────────
workspace_md = """# CitéVision v2 — Règle de travail source unique

## Source de vérité : WSL uniquement

| Répertoire | Rôle | Écriture autorisée |
|---|---|---|
| `~/citevision-v2/` (WSL) | **Source canonique** | ✅ Oui |
| `C:\\Users\\gheno\\citevision-v2\\` (Windows) | Mirror Cursor IDE | ❌ Non (lecture seule) |

## Workflow recommandé

```bash
# 1. Travailler dans WSL
cd ~/citevision-v2

# 2. Modifier les fichiers via scripts Python/bash
python3 scripts/mon_script_patch.py

# 3. Synchroniser vers Windows (pour Cursor IDE)
make sync-to-windows

# 4. Valider JSON si modifié
python3 scripts/validate_json.py frontend/src/i18n/fr.json
```

## Pourquoi cette règle ?

En juin 2026, des modifications faites directement dans Windows sans sync vers WSL ont corrompu
`fr.json` (accolade supplémentaire), causant un crash de login pour tous les utilisateurs.

Cette architecture un seule copie élimine définitivement ce risque.

## Commandes

```bash
make sync-to-windows   # WSL → Windows (utiliser après chaque session WSL)
make sync-from-windows # Windows → WSL (urgence seulement, confirmation requise)
```
"""

workspace_file = Path("WORKSPACE.md")
workspace_file.write_text(workspace_md, encoding="utf-8")
print(f"Created {workspace_file}")
