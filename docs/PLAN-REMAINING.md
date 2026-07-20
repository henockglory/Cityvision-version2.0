# Plan complet — état final (2026-06-17)

## Statut : handoff prêt

`bash scripts/validate-final-premium.sh` → **VALIDATION PASSED** (~54 min WSL)

| Indicateur | Valeur |
|------------|--------|
| Disponibles / Bientôt | **77 / 10** |
| E2E couverts (matrice) | **87 / 87** (`e2e_missing: 0`) |
| Stubs honnêtes | 3 (ceinture, téléphone, feu rouge) |

## Livré

- Bootstrap `ensure-e2e-ready.sh` : Docker, migrations, venv ML **native WSL**, InsightFace preload, stack complète
- Lot E2E familles + fallbacks pytest `E2E_MODE=1` (line_cross, fighting, running, routier, SEQUENCE theft)
- `verify-e2e-pytest-catalog.sh` — couverture catalogue Disponibles
- Matrice : tout Disponible → script E2E (famille live ou pytest catalogue)
- `.gitattributes` + `fix-sh-lf.sh` — scripts LF sous WSL
- `docs/HANDOFF-TEST.md` — guide de test

## Commandes pour tester

```bash
cd ~/citevision-v2
bash scripts/ensure-e2e-ready.sh          # si stack arrêtée
bash scripts/validate-final-premium.sh    # batterie complète
make coverage-matrix                      # e2e_missing doit rester 0
```

UI : http://localhost:5174/demo — `glory.henock@hologram.cd` / `Hologram2026!`
