# Handoff — tester CitéVision v2 (WSL)

## 1. Bootstrap (une fois par session)

```bash
cd ~/citevision-v2
bash scripts/ensure-e2e-ready.sh
```

Démarre Docker, migrations, venv ML native WSL, backend :8081, IA :8001, rules-engine :8010.

## 2. Batterie validation complète

```bash
bash scripts/validate-final-premium.sh
```

## 3. Commandes utiles (rapides)

```bash
make coverage-matrix
bash scripts/verify-e2e-spatial-semantic.sh
bash scripts/verify-e2e-webhook-cloudevents.sh
bash scripts/verify-e2e-families-all.sh      # ~20–30 min
bash scripts/verify-e2e-event-matrix.sh        # ~3 min MQTT
```

## 4. UI démo

- Frontend : http://localhost:5174/demo
- Login : `glory.henock@hologram.cd` / `Hologram2026!`

## 5. Matrice honnête

- **Disponibles** : couverts par familles E2E live + `verify-e2e-pytest-catalog.sh`
- **Stubs** (ceinture, téléphone, feu rouge) : `supported: false` — pas de faux positifs
- `e2e_missing` dans `docs/RULE-COVERAGE-MATRIX.json` doit être **0** après `make coverage-matrix`
