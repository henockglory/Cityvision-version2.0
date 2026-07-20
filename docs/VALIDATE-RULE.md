# validate_rule — DoD infalsifiable (Sprint 2)

## Usage (WSL `~/citevision-v2`)

```bash
bash scripts/health_check_all.sh
bash scripts/validate_rule.sh speeding
bash scripts/validate_rule.sh red_light
bash scripts/validate_rule.sh phone
bash scripts/validate_rule.sh seatbelt
bash scripts/validate_rule.sh counting
```

Audit only (latest alert, no live wait):

```bash
VALIDATE_MODE=audit SKIP_1HIT=1 bash scripts/validate_rule.sh red_light
```

## Artefacts

`validation-evidence/<alias>/<UTC-timestamp>/`

| Fichier | Rôle |
|---------|------|
| `report.json` / `report.md` | DoD points 1–6 |
| `ui.png` | Point 7 — capture UI `:5174` (R.3) |

## Règles

- Un artefact **PASS** = **une** règle validée.
- Claim **5/5** uniquement si **cinq** artefacts PASS récents existent (un par alias).
- Jamais de PASS sans `ui.png` (sinon `PARTIAL` max).
- Pas de rewrite de zones (A.1 / P.135).
