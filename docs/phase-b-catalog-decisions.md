# Phase B — Décisions catalogue [I.76–I.82] [P.133]

_Date : 2026-07-04_

## Inventaire 34 templates fragiles

Classification documentée dans [`RULE-COVERAGE-MATRIX.md`](RULE-COVERAGE-MATRIX.md) et [`RULE-COVERAGE-MATRIX.json`](RULE-COVERAGE-MATRIX.json).

| Niveau | Count | Action |
|---|---|---|
| A — bbox/kinématique | 19 | Retirés de « Disponibles » → Bientôt/Laboratoire |
| B — scène/composite | 13 | Retirés ou badge `partial` |
| C — qualité image | 2 | Reclassés « qualité technique » (`tpl-video-blur`, `tpl-video-darkness`) |

## Fusion doublons [I.80]

- `tpl-fight` → `tpl-fighting`
- `tpl-speeding` / `tpl-speed-limit` → `tpl-speeding-premium`
- `tpl-accident` / `tpl-accident-composite` → `tpl-accident-composite`

## Décision [P.133] — `tpl-erratic-motion`

**Retrait** (recommandé et appliqué) : `ERRATIC` n'est jamais évalué dans `heuristics.py`. Le template est retiré du catalogue actif (`shared/rule-catalog/`) et reste uniquement dans la matrice de couverture avec statut `retired`.

Alternative non retenue : implémenter `erratic_turn_threshold` → reportée Phase F si demandée.

## Badges démo 5 règles [I.81]

| Template | Badge |
|---|---|
| `tpl-red-light` | `real` |
| `tpl-speeding-premium` | `real` (requires_calibration) |
| line_cross (spatial) | `real` |
| `tpl-phone-driving` | `real` (requires_model) |
| `tpl-seatbelt` | `real` (requires_model) |
