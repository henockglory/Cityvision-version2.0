# Definition of Done — Produit commercial CitéVision

Checklist avant vente / démo client :

- [ ] `bash scripts/preflight_platform.sh` vert en < 60 s
- [ ] Demo switch vidéo → `pipeline_status=ready` en < 90 s (ingest + Frigate fresh)
- [ ] `python scripts/validate_demo_five_rules.py` → 5/5 events métier
- [ ] `bash scripts/_run_validate_now.sh` → 3 runs consécutifs PASS (Frigate 3 règles)
- [ ] `bash scripts/validate_disk_budget.sh 30` → PASS (idle ou actif selon `ACTIVE_DEMO`)
- [ ] Mailhog mail premium sur alerte test
- [ ] UI : aucun badge catalogue `real` sans preuve E2E
- [ ] `bash scripts/inject_faults_test.sh` → ≥ 9/10
- [ ] `GET /health/platform` → `status=ok` ou `degraded` documenté
- [ ] Runbook [QUICKSTART-DEMO.md](./QUICKSTART-DEMO.md) validé humainement

## Honnêteté catalogue

Voir [rule-honesty-matrix.md](./rule-honesty-matrix.md). Règles démo 5/5 :

| Règle | Badge autorisé si… |
|-------|-------------------|
| Feu rouge | Frigate PASS + evidence complete |
| Vitesse | idem |
| Téléphone | idem |
| Ceinture | idem |
| Comptage | event métier OK (observation, pas alerte) |
