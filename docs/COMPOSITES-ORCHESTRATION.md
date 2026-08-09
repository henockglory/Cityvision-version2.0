# Composites orchestration (Phase 6)

Composites are **not** new detectors. They are rules-engine sequences / windows over atoms that already emit with evidence packages.

| Template | Atoms (examples) | Engine |
|---|---|---|
| `tpl-identity-correlation` | `face_watchlist_match` + `plate_detected` / `plate_blocked` | correlation + sequence |
| `tpl-traffic-pipeline` | `speeding` + `red_light_violation` + plate | pipeline bindings |
| `tpl-observation-rule-set-n/or` | counting / line_cross observations | observation_mode |
| Intrusion after-hours / industrial | `perimeter_breach` + schedule `window` | schedule binding |

## Evidence policy

- Evidence = **union** of atom packages.
- If any required atom is `evidence_status=missing`, suppress the composite alert (fail-closed).
- Do not mark composite `catalog_badge=real` until each atom has a recent `validate_rule` PASS.

## Honesty

Only four templates are currently `dod_verified`/`real` (speeding, red-light, seatbelt, phone). Composites stay `partial` until atoms are green.

`tpl-theft-composite` (Vol suspect) a été **retiré** du catalogue — préférer les atomes `zone_enter` / `loitering` / `abandoned_object` séparément.
