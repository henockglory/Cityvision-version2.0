# Validation DoD — Frigate-primary + Gemini (1a / 2b)

Pas de claim « 5/5 validé » sans artefacts `validate_rule` (R.3).

## Kill-switches (WSL `~/citevision-v2/.env`)

```
GEMINI_ENABLED=1
GEMINI_API_KEY=...          # never commit
FRIGATE_VLM_BRIDGE=1        # cabin/face/plate via Frigate→Gemini
FRIGATE_SPEED_BRIDGE=1      # speeding via Frigate estimate vs speed_limit_kmh
```

## Per-rule validation

```bash
bash scripts/validate_rule.sh seatbelt
bash scripts/validate_rule.sh phone
bash scripts/validate_rule.sh face
bash scripts/validate_rule.sh speed
bash scripts/validate_rule.sh plate
# red light stays local HSV — regression
bash scripts/validate_rule.sh redlight
```

Each PASS requires DoD points 1–6 + UI capture `:5174` under `validation-evidence/`.

## Honesty

- Catalog badges stay `partial` / `requires_external` until those artefacts exist.
- Feu rouge remains CiteVision HSV (not Gemini/Frigate judgment).
- Frigate `speed_threshold` ≠ legal limit; CiteVision `speed_limit_kmh` decides `speeding`.
