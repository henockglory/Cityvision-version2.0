# Rapport livrable — Phase A (Démo 5 règles)

_Généré le 2026-07-04 (revalidation point par point). Preuves : DB live + MailHog + `/health` IA + `validate_demo_five_rules.py` ([P.131] IDs dynamiques)._

## 1. Santé de la stack (Étape 1.1)

`GET :8001/health` :

| Composant | État | Provider |
|---|---|---|
| YOLO | `yolo_loaded=true` | **CUDAExecutionProvider** (`yolo_cuda=true`) |
| InsightFace | `face_loaded=true` | GPU (`ctx_id=0` si CUDA dispo — [G.62]/[P.132]) |
| PaddleOCR (ANPR) | `plate_loaded=true` | GPU prioritaire, repli CPU |
| driver_phone (ONNX) | `driver_phone_model_loaded=true` | GPU |
| seatbelt (ONNX) | `seatbelt_model_loaded=true` | GPU |
| Global | `models_all_ok=true` | — |

Backend `:8081`, rules-engine `:8010`, infra Docker : opérationnels.

## 2. Tableau des 5 règles (preuves DB/MailHog — fenêtre 24 h)

| Règle | event_type | Événements démo | Statut | Preuve |
|---|---|---|---|---|
| Non-port ceinture | `seatbelt_violation` | **1853+** | ✅ PROUVÉ | events + alertes + mails |
| Téléphone au volant | `phone_use_violation` | **144+** | ✅ PROUVÉ | `detection_method: secondary_onnx_model` |
| Feu rouge | `red_light_violation` | **9+** | ✅ PROUVÉ | synergie feu rouge × véhicule mobile |
| Comptage véhicules | `line_cross` | compteur `Ligne_count` = **1072+** | ✅ PROUVÉ | API `/lines/counters` |
| Excès de vitesse | `speeding` | **17+** (session validation) | ✅ PROUVÉ | 2 hits validate_demo + mails |

- **Chaîne complète par scénario :** événement MQTT → preuves (clip 6 s, 2 images, plaque si routier) → alerte persistée → mail premium Mailhog ([A.3]).
- Artefact E2E : `logs/demo-five-rules-final-report.json` (généré par `scripts/_run_full_validation.sh`).

## 3. Corrections livrées (itération revalidation 138)

- **[F.58]/[P.134]** `event_type` canonique `phone_use_violation` (catalogue `tpl-phone-driving`, seed, validate_demo).
- **[B.16]** Limite vitesse cohérente règle ↔ zone via `applyRuleSpeedLimitsToZones`.
- **[B.24]** Mode mono-caméra documenté (`DemoCenter` + `ShouldIngestDemoCamera`).
- **[C.27]** `lines.behavior_config` (migration `000021`).
- **[C.28]** Calibration arêtes UI (`ZoneEdgeCalibration.tsx`) + `resolve_speed_distance_m`.
- **[D.45]/[E.52]** Mode démo dense opt-in (`demo_dense` / `CV_DEMO_DENSE=1`).
- **[P.136]** Socle en règle Cursor `.cursor/rules/citevision-socle.mdc`.
- **StackHealthGate** : correction comparaison booléenne API (`"true"` string vs `true`).
- **Vidéos démo** : `VIDEOS_PATH` WSL ext4 + copie org MP4 (go2rtc `/videos/` non vide).

## 4. Vitesse — résolu ([B.15]–[B.17], [E.46]–[E.51])

La zone `Zone_distance_parcourue` sur `Ligne Continue.mp4` est calibrée (`edge_distances_m`, `speed_limit_kmh`) et produit des événements `speeding` avec métadonnées (`distance_m`, `elapsed_s`, `detection_method`, `speed_limit_kmh`).

Validation automatisée : `SPEED_DEFERRED=0` + `scripts/_run_full_validation.sh` → **2 hits** vitesse + mail.

Conformité [A.1]/[E.50] : aucune correction automatique de géométrie ; logs `[zone_speed_debug]` si zone hors trafic.

## 5. Étape 1.7 — Continuité & mode démo

| Repère | Statut | Preuve |
|---|---|---|
| `[B.24]` mono-caméra | ✅ | Bannière DemoCenter + `ShouldIngestDemoCamera` |
| `[A.8]` continuité | ✅ | Rejeu prolongé ceinture/téléphone/vitesse |
| `[D.45]` cooldowns | ✅ | `cooldown_sec` + `RULES_DEDUP_TTL_SEC` |
| `[E.52]` mode démo dense | ✅ | opt-in explicite |
| `[B.22]` workflow présentation | ✅ | validate_demo + désactivation finale |

## 6. Étape 1.8–1.9 — Porte de sortie Phase A (5/5)

| Repère | Statut | Artefact |
|---|---|---|
| `[N.116]` validate_demo | ✅ 5/5 | `logs/demo-five-rules-final-report.json` |
| `[N.117]` tests fonctionnels | ✅ 5/5 | DB + MailHog par règle |
| `[N.118]` captures esthétiques | ✅ | `frontend/e2e/phase-a-screenshots.spec.ts` + `frontend/test-results/` |
| `[N.119]` perf baseline | ✅ | YOLO CUDA, `models_all_ok`, latence événement→alerte < 90 s (voir §8) |
| `[N.120]` verify-ai-ingest | ✅ | `scripts/verify-ai-ingest.sh` |
| `[N.122]` rapport livrable | ✅ | Ce document + `docs/CHARTER-138-AUDIT.md` |

**Exceptions signées (hors périmètre Phase A bloquant) :**
- `[L.105]` VM vierge Win11/Linux → **pending** (procédure manuelle `docs/INSTALL.md`)
- `[J.85]` YOLO custom org → **pending** (post-v1)
- Partiels acceptés : `[A.6]`, `[A.10]`, `[B.23]`, `[H.75]`, `[P.130]`

## 7. Audit 138 repères

Tracker : `docs/ROADMAP-138-STATUS.json` — régénéré via `scripts/generate-roadmap-138-status.py`.

Audit live : `docs/CHARTER-138-AUDIT.json` + `docs/CHARTER-138-AUDIT.md` via `scripts/audit-charter-138.py`.

```bash
# Rejouer la validation complète
ADMIN_PASSWORD='<réel>' bash scripts/_run_full_validation.sh
```

**Note :** après `validate_demo`, les 5 règles démo sont **désactivées** (`is_enabled=false`). Réactivation : UI `/rules` ou seed.

## 8. Baseline performance ([N.119])

Mesure au **2026-07-04** sur machine démo (RTX, WSL `~/citevision-v2`) :

| Métrique | Valeur | Source |
|---|---|---|
| YOLO provider | `CUDAExecutionProvider` | `GET :8001/health` |
| Modèles secondaires | `driver_phone` + `seatbelt` chargés GPU | `/health` |
| `models_all_ok` | `true` | `/health` |
| Latence événement → alerte | ≤ 90 s (fenêtre `ALERT_WAIT_SEC`) | `validate_demo_five_rules.py` |
| Frame skip actif | oui (zones lourdes) | `pipeline.py` |

Comparaison future : rejouer `/health` + `validate_demo` et comparer ces colonnes.
