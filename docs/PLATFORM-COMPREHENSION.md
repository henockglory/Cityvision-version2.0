# Compréhension plateforme — Pass 1–4 (réponses agent)

> Document de gate lecture. Référence : plan refonte produit CitéVision.

## Pass 1 — Carte des acteurs

| Question | Réponse |
|----------|---------|
| Q1.1 Source polygones | DB `zones` / `lines` uniquement — jamais scripts `_fix_*` |
| Q1.2 Filtre caméra | `buildSpatialConfig(org, cameraID)` dans orchestrator |
| Q1.3 Excès vitesse | IA `zone_speed.py` → event `speeding` — pas Frigate |
| Q1.4 Alerte | rules-engine sur MQTT `cv/events/#` → executor |
| Q1.5 Preuve | `evidence/service.py` (+ Frigate si `EVIDENCE_BACKEND=frigate`) |

## Pass 2 — Trace event bout-en-bout

| Maillon | Réponse |
|---------|---------|
| Ingest | IA et Frigate lisent le même flux go2rtc via restream `cv_{uuid}` |
| Spatial | Zones IA = Frigate `cv_zone_{uuid}` (compiler sync.go) |
| Event | `zone_id` doit matcher zone active sur caméra courante |
| Règle | `is_enabled` + camera binding + pas `observation_mode` pour alerte |
| Preuve | Inline dans pipeline si policy match ; retry rules-engine 5×5s |
| Alerte suppressed | `incomplete evidence` si package absent après retries |

**Point de rupture typique** : corrélation Frigate (offset horloge démo) ou evidence async.

## Pass 3 — 5 règles démo

| Règle | event_type | behavior | Alerte |
|-------|------------|----------|--------|
| Feu rouge | red_light_violation | traffic_light_color | oui |
| Comptage | line_cross | count_crossings | non (observation) |
| Vitesse | speeding | speed_measurement | oui |
| Téléphone | phone_use_violation | phone_use | oui |
| Ceinture | seatbelt_violation | seatbelt | oui |

Changement zone UI → orchestrator fingerprint → resync IA + Frigate rebuild.

## Pass 4 — Stockage

| Composant | Écriture | Rétention | Purge |
|-----------|----------|-----------|-------|
| Frigate recordings | continuous si record.enabled | days:0 = illimité | demo-retention-purge.sh |
| Frigate clips | events detect | 30j (base yaml) | purge shell |
| MinIO evidence | alertes | cron 30 min | retention governor |
| Postgres events | MQTT ingest | janitor 60 min | retention.go |

**Cause racine 100 Go/30 min** : `record.enabled: true` + `retain.mode: all` + boucles démo.
