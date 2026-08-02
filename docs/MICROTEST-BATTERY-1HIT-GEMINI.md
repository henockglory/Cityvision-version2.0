# Batterie micro-tests — CitéVision (campagne 1-45)

> Checklist de référence. Rapport auto : `docs/MICROTEST-REPORT-<TS>.md`  
> PASS campagne = **PASS_1HIT** uniquement (pas PASS_DoD).

## Décisions verrouillées (D1-D5)

- D1/Q9 : gate OR (`RED_LIGHT_GATE_MODE=or`)
- D2/Q8 : grâce 2,5 s (`RED_LIGHT_POST_RED_GRACE_SEC=2.5`)
- D3/Q18 : dump 20 JPEG cabine avant tests 19-25
- D4/Q25 : PASS_1HIT vs PASS_DoD séparés
- D5/Q13 : min_confidence 0,45 inchangé

## Exécution

```bash
cd ~/citevision-v2
bash scripts/microtest/_microtest_run_all.sh
```

Variables utiles :
- `MICROTEST_HSV_SEC=120` — durée poll feu (défaut campagne rapide)
- `MICROTEST_FAST=1` — alias raccourci
- `MICROTEST_FORCE_1HIT=1` — test 45 malgré gate NO-GO

## Tests 1-45

Voir plan `micro-tests_batterie_1-45` et rapport généré avec chiffres par test.

| # | Domaine | Script |
|---|---------|--------|
| 1-10 | Feu/HSV | `_microtest_feu_hsv.sh` |
| 11-18 | Gemini feu | `_microtest_gemini_feux.py` |
| 19-25 | Cabin | `_microtest_cabin.sh` (si Q18 OK) |
| 26-30 | Vitesse | `_microtest_vitesse.sh` |
| 31-32 | Régression | `_microtest_regression.sh` |
| 33-35 | Evidence | `_microtest_evidence.sh` |
| 36-40 | Orchestration | `_microtest_orchestration.sh` |
| 41-44 | Synergie shadow | `_microtest_synergy.sh` |
| 45 | 1-hit feu | `_microtest_1hit_feu.sh` |

## Résultats campagne 20260801T215936Z

Rapport : [`MICROTEST-REPORT-20260801T215936Z.md`](MICROTEST-REPORT-20260801T215936Z.md)

| Gate / test | Verdict | Détail |
|-------------|---------|--------|
| A feu 1-10 | **NO-GO** | `delta_enqueued=0`, `hsv_gate_debug keys []` |
| B Q18 cabin | **ge50** | 20 JPEG → `validation-evidence/cabin-dump-20260801T220229Z/` |
| C Gemini 11-18 | **NO-GO** | HTTP 404 modèle (`gemini-2.5-flash`) — 0/10 violation |
| C2 cabin 19-25 | exécuté | `cabin_enqueued_delta=0`, `emitted=0` |
| D vitesse 26-30 | exécuté | `speed_emitted=0`, shadow_max=0 |
| D2 comptage 31 | **PASS** | rc=0, counter_delta=16 |
| E evidence 33-35 | exécuté | mailhog OK, 8 alerts récentes |
| E2 orchestration 38 | OK | recovery Frigate 11s, disque C: 77% |
| E3 shadow 42-44 | exécuté | shadow_logged=0 |
| **45 1-hit feu** | **FAIL** | rc=1, 720s, 0 alert ; bridge `red_light_enqueued=8` hors fenêtre |

**PASS_1HIT feu : non atteint.** Prochaines actions : résoudre caméras TL dans `hsv_gate_debug`, corriger endpoint/modèle Gemini 404, relancer gate A avec poll 300s.

### Fix blocages (20260802)

Scripts [`scripts/microtest/_microtest_fix_blockers.sh`](scripts/microtest/_microtest_fix_blockers.sh) + [`_microtest_raw_hsv_probe.py`](scripts/microtest/_microtest_raw_hsv_probe.py). Rapport [`docs/microtest-fix-20260802T000652Z/fix-report.md`](docs/microtest-fix-20260802T000652Z/fix-report.md).

| Action | Résultat |
|--------|----------|
| Auto-fix `GEMINI_MODEL=gemini-3.1-flash-lite` | generateContent OK |
| Test 45 relance post-fix | **PASS_1HIT** rc=0, `vlm_emitted=1` |
| Stabilite x3 | [`_microtest_1hit_feu_stability_x3.sh`](scripts/microtest/_microtest_1hit_feu_stability_x3.sh) | **3/3 PASS_1HIT** ([rapport](docs/microtest-stability-20260802T011746Z/stability-summary.md)) |

**PASS_1HIT feu : atteint et stable (3/3).** Prochaine cible : bloc F (vote LF_OR_G shadow) — voir [`HANDOFF-SYNERGIE-3-ACTEURS.md`](HANDOFF-SYNERGIE-3-ACTEURS.md) §13–15.

## Batterie 46–90+ (en cours)

| Bloc | Script | Statut |
|------|--------|--------|
| E 46–50 | `_microtest_fix_blockers.sh` | complété 20260802 |
| F 51–60 | `_microtest_synergy.sh` | LF_OR_G shadow |
| G 61–70 | `_microtest_cabin_crop_compare.sh` | driver_roi compare |
