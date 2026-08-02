# CitéVision — Architecture fonctionnelle complète, campagne micro-tests, et feuille de route synergie 3 acteurs

> **Statut** : handoff pour assistant IA — environnement, campagne testée, blocages, synergie Frigate / IA locale / Gemini.
> **Complément opérationnel** : [HANDOFF-ARCHITECTURE-COMPLETE-1HIT-GEMINI.md](HANDOFF-ARCHITECTURE-COMPLETE-1HIT-GEMINI.md) §18–21 (fixes 20260802, stabilité 3/3).
> **Runtime vérité** : WSL `~/citevision-v2` uniquement.
>
> **Convention** :
> - `# CONFIRMÉ (chat)` — noms, flags, décisions, résultats validés en échange.
> - `# ILLUSTRATIF — signature non vérifiée` — pseudo-code probable ; vérifier le repo avant implémentation.

---

## Table des matières

1. [Vue d'ensemble](#1-vue-densemble-de-larchitecture)
2. [Flux RTSP → Frigate](#2-le-flux-rtsp--frigate--détection-brute)
3. [Les 3 acteurs](#3-les-3-acteurs-et-leurs-rôles-respectifs)
4. [Rules-engine](#4-le-moteur-de-règles-rules-engine)
5. [Règle par règle](#5-règle-par-règle--fonctionnement-détaillé)
6. [Pont Gemini](#6-le-pont-gemini-frigate_vlm_bridge)
7. [Evidence → notification](#7-le-pipeline-evidence--notification)
8. [Journal campagne 1-45](#8-journal-de-la-campagne-micro-tests-1-45)
9. [Post-mortem 3 blocages](#9-post-mortem-détaillé-des-3-blocages)
10. [Feu rouge vs moteur local](#10-pourquoi-le-feu-rouge-échoue-alors-que-le-moteur-local-y-arrivait)
11. [Synergie 3 acteurs](#11-proposition--synergie-maximale-des-3-acteurs-règle-par-règle)
12. [Questions Q46–Q60](#12-questions-ouvertes--priorisées)
13. [Batterie 46–90+](#13-nouvelle-batterie-de-micro-tests-46-90)
14. [Glossaire](#14-glossaire)
15. [Mises à jour post-campagne 20260802](#15-mises-à-jour-post-campagne-20260802)

---

## 1. Vue d'ensemble de l'architecture

CitéVision répartit la décision entre **trois acteurs** :

```text
RTSP → Frigate (objets, zones, MQTT)
     → Moteur IA locale (HSV, vitesse, gates, state machines)
     → Gemini VLM (jugement visuel sémantique)
     → Rules-engine (should_emit, evidence, notifications)
```

Principe validé : **Gemini remplace le classifieur visuel (SecondaryInferenceEngine)**, pas le contrat métier (rules-engine, evidence, event_type, MQTT). En cas d'échec, identifier **l'étage exact** qui bloque.

### 1.1 Quatre phases d'une détection

1. **Détection brute** (Frigate) — objet tracké dans une zone.
2. **Gate déterministe** (IA locale) — conditions a priori (HSV rouge, vitesse, etc.).
3. **Confirmation sémantique** (Gemini) — si la règle l'exige.
4. **Émission** (rules-engine) — should_emit, evidence, alerte.

---

## 2. Le flux RTSP → Frigate → détection brute

Frigate : tracking, zones, MQTT `entered_zones` / `left_zones`, clips evidence.

```text
# CONFIRMÉ (chat)
bbox_source = "frigate_mqtt"   # PASS_1HIT feu/vitesse (Q26)
```

Frigate **ne juge pas** la couleur du feu — délégué au moteur HSV local.

---

## 3. Les 3 acteurs et leurs rôles respectifs

| Acteur | Fait | Ne fait pas |
|---|---|---|
| **Frigate** | Objets, zones, tracking, clips | Sémantique (feu, ceinture, téléphone) |
| **IA locale** | HSV, vitesse, gates, dedupe | Jugement visuel ambigu |
| **Gemini** | Jugement visuel | Rien sans image pertinente ; coût + latence |

### 3.1 Friction actuelle

Chaîne **séquentielle stricte** : si le gate local ne s'active pas, Gemini n'est jamais interrogé.

### 3.2 Direction proposée (§11)

**Vote multi-signal** configurable par règle — ex. `LF_OR_G` : (local + Frigate) OU Gemini confirmé.

---

## 4. Le moteur de règles (rules-engine)

Orchestre candidats, politique evidence, `should_emit`, publication MQTT/UI.

Comportement confirmé campagne : rejets ceinture/téléphone sur `visible=false` **avant** le seuil de confiance (Q13 : ne pas baisser `min_confidence`).

### 4.1 PASS_1HIT vs PASS_DoD (Q25)

- **PASS_1HIT** : ≥1 event + ≥1 alert + preuve source OK → `_validate_rule_frigate_1hit.py`
- **PASS_DoD** : PASS_1HIT + evidence complete + mail + capture UI `validate_rule.sh`

---

## 5. Règle par règle — fonctionnement détaillé

### 5.1 Comptage (line_cross)

Frigate seul ; pas de Gemini. **PASS** campagne : `counter_delta=16` (test 31).

### 5.2 Feu rouge (red_light_violation)

- Frigate : véhicule dans `red_light_observation`
- Local : HSV `raw_state`, `stable_state`, `gate_mode` (and|or|raw), grâce post-rouge

```bash
# CONFIRMÉ (chat)
RED_LIGHT_GATE_MODE=or
RED_LIGHT_POST_RED_GRACE_SEC=2.5
RED_LIGHT_VOTE_MODE=strict_and|lf_or_g   # lf_or_g implémenté 20260802
RED_LIGHT_VOTE_SHADOW=1                  # shadow local path
RED_LIGHT_DEBUG_FORCE_ENQUEUE
```

Avant Q9 : `skipped_not_red=45`, `enqueued=6` (gate AND trop strict).

### 5.3 Excès de vitesse (speeding)

Frigate tracking + calcul local (`average_estimated_speed`, `speed_limit_kmh`, `edge_distances_m`). Campagne : `speed_emitted=0` (données test ou sync).

### 5.4 Téléphone (phone_use) / 5.5 Ceinture (seatbelt)

Gemini obligatoire. Crop campagne : `FRIGATE_VLM_BRIDGE_CROP_MODE=vehicle_bbox` → **driver_roi** disponible (Q19).

Audit Q18 : 50/50 `visible=false` ; dump 20 JPEG ge50 → problème crop/prompt, pas caméra.

```bash
FRIGATE_CABIN_DEDUPE_SEC=25
FRIGATE_VLM_BRIDGE_CROP_MODE=driver_roi   # alias cabin_driver, driver, torso
```

---

## 6. Le pont Gemini (FRIGATE_VLM_BRIDGE)

```bash
FRIGATE_VLM_BRIDGE=1
GEMINI_QUEUE_SIZE=12   # Q17, monté depuis 3
GEMINI_MODEL=gemini-3.1-flash-lite   # post-fix 20260802
```

Sous ce flag, HSV local = gate uniquement ; émission feu via Gemini (mode `strict_and`) ou vote `lf_or_g`.

---

## 7. Le pipeline evidence → notification

`evidence_status`, `capture_source`, `bbox_source`. Q27 : plaque manquante OK pour PASS_1HIT Phase A.

Tests 33–44 : Mailhog OK, recovery Frigate 11s.

---

## 8. Journal de la campagne micro-tests 1-45

| Bloc | Tests | Verdict initial (20260801) |
|---|---|---|
| A — feu | 1-10 | **NO-GO** — `delta_enqueued=0`, HSV debug vide au repos |
| B — Q18 | — | **ge50** — 20 JPEG `validation-evidence/cabin-dump-20260801T220229Z/` |
| C — Gemini | 11-18 | **NO-GO** — HTTP 404 `gemini-2.5-flash` |
| C2 — cabin | 19-25 | `cabin_enqueued_delta=0`, `emitted=0` |
| D — vitesse | 26-30 | `speed_emitted=0` |
| 31 — comptage | — | **PASS** — `counter_delta=16` |
| 33-44 | — | Mailhog OK, Frigate recovery 11s |
| 45 — 1-hit feu | — | **FAIL** — 0 alerte (historique) |

> **Post-fix 20260802** : test 45 **PASS_1HIT**, stabilité **3/3** — voir §15.

Livrables code : `traffic_light.py`, `config.py`, `pipeline.py`, `/debug/rule-blockers`, scripts `scripts/microtest/*`.

---

## 9. Post-mortem détaillé des 3 blocages

### 9.1 Gemini HTTP 404

Symptôme : 0/10 violation — échec API, pas jugement Gemini. **Résolu** : `gemini-3.1-flash-lite`.

### 9.2 hsv_gate_debug vide

Symptôme post Q9/Q8 : debug vide au repos. **Clarifié** : `spatial_camera_count=0` sans worker ; OK après warm-start cam feu.

### 9.3 Test 45 enqueue hors fenêtre

Symptôme conséquence 9.1 + 9.2. **Résolu** — ne pas réinvestiguer isolément.

---

## 10. Pourquoi le feu rouge échoue alors que le moteur local y arrivait

1. Bridge rend Gemini **obligatoire** pour émettre (`strict_and`).
2. Gate upstream trop strict (AND raw+stable) avant Q9.
3. Pas de filet si Gemini 404 / `unclear`.

Direction : vote `LF_OR_G` — local+Frigate peuvent émettre seuls ; Gemini en renfort.

---

## 11. Proposition : synergie maximale des 3 acteurs

```text
Frigate ── signal_frigate
Local   ── signal_local (HSV, vitesse)
Gemini  ── signal_gemini (multi-mode, rafale)
          ↓
Vote engine (strict_and | lf_or_g | weighted …)
```

| Règle | Vote proposé | Gemini |
|---|---|---|
| Comptage | inchangé | 0 |
| Feu | `LF_OR_G` + vérif continue 3s | élevée en fenêtre candidate |
| Vitesse | Frigate+local | optionnel |
| Tél./ceinture | Gemini + multi-crop | modérée–élevée |

Implémentation : [`red_light_vote.py`](../ai-engine/src/citevision_ai/road_enforcement/red_light_vote.py), flag `RED_LIGHT_VOTE_MODE`.

---

## 12. Questions ouvertes — priorisées

### Bloquantes — tranchées ou en cours

| Q | Statut |
|---|---|
| **Q46** Modèle Gemini | **RÉSOLU** : `gemini-3.1-flash-lite` |
| **Q47** spatial_configs cam feu | **RÉSOLU** : `spatial_ok`, cam `8ed20433-57d5-4999-a6ab-0bea028b23a3` |
| **Q48** Q9/Q8 actifs runtime | **OUI** — `skipped_not_red` mesuré 13–48 (stabilité) |
| **Q49** Vote feu | **IMPLÉMENTÉ** shadow — tester bloc F avant prod |
| **Q50** driver_roi vs vehicle_bbox | **driver_roi implémenté** — comparer via `_microtest_cabin_crop_compare.sh` |

### Importantes (campagnes suivantes)

- **Q51** Cadence Gemini feu : 3s vs 5s
- **Q52** Gemini pour vitesse ?
- **Q53** Coût multi-image
- **Q54** Cap budget quotidien
- **Q55** Rafale cabine systématique ou sur `unclear`
- **Q56** Gemini veto émission local+Frigate (`RED_LIGHT_GEMINI_VETO`)
- **Q57** Durée warm-up 1-hit

### Peuvent attendre

- Q58 centraliser VoteStrategy
- Q59 AGGRESSIVE_DEMO + LF_OR_G
- Q60 Priorité queue Gemini par règle

---

## 13. Nouvelle batterie de micro-tests (46-90+)

### Bloc E — Confirmation fixes (46-50) — COMPLÉTÉ 20260802

- [x] **46.** Modèle : `gemini-3.1-flash-lite`
- [x] **47.** HTTP 200 post-fix
- [x] **48.** Probe warm : `bridge_red_enqueued=7`
- [x] **49.** hsv_gate_debug peuplé en warm / vide au repos
- [x] **50.** Mapping spatial : cam feu + zones TL OK

### Bloc F — Vote feu (51-60)

Scripts : [`_microtest_synergy.sh`](../scripts/microtest/_microtest_synergy.sh) (LF_OR_G shadow).

- [ ] **51–54** LF_OR_G shadow vs strict_and
- [ ] **55–58** Cadence / multi-image / latence
- [ ] **59–60** 1-hit feu avec LF_OR_G + warm-up 60s

### Bloc G — Crop cabine (61-70)

Script : [`_microtest_cabin_crop_compare.sh`](../scripts/microtest/_microtest_cabin_crop_compare.sh).

- [x] **61.** `driver_roi` implémenté
- [ ] **62–70** compare crops, 1-hit ceinture/téléphone

### Blocs H–J (71–90+)

Vitesse, orchestration/coûts, validation multi-règles — après PASS_1HIT isolé par règle.

---

## 14. Glossaire

| Terme | Définition |
|---|---|
| PASS_1HIT | ≥1 event + alert + preuve source valide |
| PASS_DoD | PASS_1HIT + evidence complete + mail + UI |
| raw_state / stable_state | HSV instantané / lissé |
| gate_mode | and / or / raw |
| FRIGATE_VLM_BRIDGE | Gemini dans décision finale |
| LF_OR_G | (Local + Frigate) OU Gemini confirmé |
| driver_roi | Crop torse/conducteur vs vehicle_bbox |

---

## 15. Mises à jour post-campagne (20260802)

Append-only — historique §8–9 campagne 20260801 conservé.

### 15.1 Résultats post-fix

| Métrique | Valeur |
|---|---|
| Modèle Gemini | `gemini-3.1-flash-lite` |
| Test 45 | PASS_1HIT rc=0, `vlm_emitted=1` |
| Stabilité x3 | 3/3 PASS_1HIT |
| Cam feu | `8ed20433-57d5-4999-a6ab-0bea028b23a3` |
| Zones TL | `traffic_light_color`, `red_light_observation` |

Rapports :
- [`docs/microtest-fix-20260802T000652Z/fix-report.md`](microtest-fix-20260802T000652Z/fix-report.md)
- [`docs/microtest-fix-20260802T005519Z/final-fix-report.md`](microtest-fix-20260802T005519Z/final-fix-report.md)
- [`docs/microtest-stability-20260802T011746Z/stability-summary.md`](microtest-stability-20260802T011746Z/stability-summary.md)

### 15.2 Code ajouté (synergie phase 2)

| Fichier | Changement |
|---|---|
| `red_light_vote.py` | Vote `lf_or_g`, dedupe emit local/Gemini |
| `bridge.py` | `_maybe_emit_lf_or_g_local`, stats `lf_or_g_*` |
| `config.py` | `RED_LIGHT_VOTE_MODE` |
| `snapshot.py` | `FRIGATE_VLM_BRIDGE_CROP_MODE=driver_roi` |
| `vlm/queue.py` | Skip Gemini si local déjà émis (lf_or_g) |
| `_microtest_synergy.sh` | Tests 51–54 shadow |
| `_microtest_cabin_crop_compare.sh` | Tests 61–62 |

### 15.3 Commandes validation (WSL)

```bash
cd ~/citevision-v2
MICROTEST_AUTO_YES=1 bash scripts/microtest/_microtest_1hit_feu_stability_x3.sh
RED_LIGHT_VOTE_MODE=lf_or_g bash scripts/microtest/_microtest_synergy.sh
bash scripts/microtest/_microtest_cabin_crop_compare.sh
```

### 15.4 Prochaine cible

Bloc F shadow LF_OR_G → 1-hit feu vote actif → Bloc G 1-hit cabine.

*Toujours PASS_1HIT — pas claim PASS_DoD / 5/5.*

---

## §16 Append 2026-08-02 — vehicle_bbox verrouillé, fusion OCR/face

### Décision Q50 (finale)

| Option | Statut |
|---|---|
| `vehicle_bbox` | **Verrouillé** — crop cabine bridge exclusif |
| `driver_roi` | **Retiré** du runtime (`snapshot.py`, `bridge.py`) ; helper `bbox_cabin_driver_region` conservé pour tests unitaires seulement |

### Comportement fusion (post-implémentation)

- **Cabine** : prompts oui/non ; `should_emit` ignore `visible` / `unclear` pour `seatbelt_violation` et `phone_use_violation`.
- **Plaque** : `_maybe_plate` lance Paddle sync sur le jpeg Frigate ; queue fusionne avec Gemini (`plate_fusion.py`).
- **Visage** : InsightFace ne s'arrête plus sous bridge ; dedupe 30s dans `pipeline._identity_emit_dedupe`.

### Tests unitaires

```bash
python -m pytest ai-engine/tests/test_gemini_vlm.py ai-engine/tests/test_plate_fusion.py -q
```
