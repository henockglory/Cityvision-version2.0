# Plan complet — état d'avancement (2026-06-17)

## Livré (session en cours)

### Lot E2E par famille (Phase D)
- `scripts/e2e/lib/common.sh` — auth, zone/line, règle, attente événement, preuves
- `scripts/verify-e2e-family-spatial.sh` — zone_enter, zone_presence, perimeter_breach, line_cross, fighting
- `scripts/verify-e2e-family-identity.sh` — running, face_detected, plate_detected (skip si modules absents)
- `scripts/verify-e2e-family-road.sh` — sudden_stop (pytest), vehicle_stopped, vehicle_count_threshold
- `scripts/verify-e2e-sequence-theft.sh` — SEQUENCE zone_enter + loitering
- `scripts/verify-e2e-families-all.sh` — familles + webhook + `make coverage-matrix`
- `validate-final-premium.sh` — délègue au lot familles (sans doublon zone-alert)

### zone_kind API + wizard
- Migration `000016_zone_kind` (+ script `apply-zone-kind-migration.sh`)
- Backend spatial CRUD + orchestrateur IA
- `ZoneEditor.tsx` — sélecteur type de zone sur brouillons (perimeter, controlled_exit, …)

### Phase B lot 2 — événements IA
- `perimeter_breach`, `unauthorized_exit`, `sudden_stop` + tests unitaires
- `verify-e2e-spatial-semantic.sh` — PASS

### Phase E — routage
- `webhook.go` : retries, CloudEvents, DLQ — `go test ./internal/routing` PASS

### Capabilities (11 templates)
- Fiches ajoutées : multi-zone, industrial-intrusion, pedestrian-zone, wrong-lane, etc.
- Stubs honnêtes inchangés : ceinture, téléphone, feu rouge (`supported: false`)

## Matrice actuelle

```bash
make coverage-matrix
```

| Indicateur | Valeur |
|------------|--------|
| Disponibles / Bientôt | **77 / 10** |
| Implémenté (IA) | 56 |
| E2E script (famille ou dédié) | **24** |
| E2E manquant | **63** |
| Stubs honnêtes | 3 |

## Reste à faire (honest)

1. **pip identité / ANPR** : venv `ai-engine/.venv` + `pip install -e '.[identity,anpr,dev]'` — en cours
2. **Phase D** : 63 règles Disponibles sans `verify-e2e-*.sh` dédié (familles couvrent ~10 chemins critiques)
3. **E2E composites** : vandalisme, accident SEQUENCE sur flux Benedicte
4. **Critère 100 %** : `e2e_missing` doit atteindre 0 dans `RULE-COVERAGE-MATRIX.json`

## Commandes utiles

```bash
make coverage-matrix
bash scripts/verify-e2e-spatial-semantic.sh      # rapide
bash scripts/verify-e2e-webhook-cloudevents.sh   # go test routing
bash scripts/verify-e2e-families-all.sh          # long (~15–25 min)
bash scripts/verify-e2e-event-matrix.sh          # très long (~3 min MQTT)
bash scripts/validate-final-premium.sh           # batterie complète
bash scripts/apply-zone-kind-migration.sh        # Postgres zone_kind
```
