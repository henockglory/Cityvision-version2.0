# CitéVision v2 — Règle de travail source unique

## Source de vérité : WSL uniquement

| Répertoire | Rôle | Écriture autorisée |
|---|---|---|
| `~/citevision-v2/` (WSL) | **Source canonique** | ✅ Oui |
| `C:\Users\gheno\citevision-v2\` (Windows) | Mirror Cursor IDE | ❌ Non (lecture seule) |

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
