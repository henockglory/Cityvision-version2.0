# Composites orchestration (Phase 6)

Composites are **not** new detectors. They are rules-engine sequences / windows over atoms that already emit with evidence packages.

| Template | Atoms (examples) | Engine |
|---|---|---|
| `tpl-identity-correlation` | `face_watchlist_match` + `plate_detected` (RULE_SET, fenêtre 120 s) | rules-engine RULE_SET |
| `tpl-traffic-pipeline` | **redirect** → `tpl-speeding-premium` (`vehicle_corridor` drop publish) | — |
| `tpl-observation-rule-set-n/or` | Compteur scénario (≥2 event chips) | observation_mode / RULE_SET(_OR) |
| Intrusion after-hours / industrial | `perimeter_breach` + schedule `window` | schedule binding |

## Evidence policy

- Evidence = **union** of atom packages.
- Observation mode : preuves off par défaut.
- If any required atom is `evidence_status=missing`, suppress the composite alert (fail-closed).
- Do not mark composite `catalog_badge=real` until each atom has a recent `validate_rule` PASS.

## Honesty

Only four templates are currently `dod_verified`/`real` (speeding, red-light, seatbelt, phone). Composites stay `partial` until atoms are green.

`tpl-theft-composite` (Vol suspect) a été **retiré** du catalogue — préférer les atomes `zone_enter` / `loitering` / `abandoned_object` séparément.

`tpl-traffic-pipeline` / `tpl-plate-pipeline` / `tpl-face-watchlist` / `tpl-plate-unknown` sont des **redirects** catalogue (plus de fiches live).
