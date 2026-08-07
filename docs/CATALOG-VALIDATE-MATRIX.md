# Catalog × validate_rule matrix

Generated: `2026-08-07T07:02:04.846224+00:00`

- Total templates: **53**
- DoD verified (`real`): **4** → `tpl-seatbelt, tpl-speeding-premium, tpl-red-light, tpl-phone-driving`

| Template | dod_alias | signal_owner | judgment | badge | verified |
|---|---|---|---|---|---|
| `tpl-abandoned-object` | `abandoned` | `hybrid` | `geometry` | `partial` | `False` |
| `tpl-blocked-plate` | `plate-blocked` | `frigate` | `rules_composite` | `partial` | `False` |
| `tpl-congestion` | `congestion` | `frigate` | `geometry` | `partial` | `False` |
| `tpl-crowd-count` | `crowd-count` | `frigate` | `geometry` | `partial` | `False` |
| `tpl-crowd-density` | `crowd-density` | `frigate` | `geometry` | `partial` | `False` |
| `tpl-dwell-exceeded` | `dwell` | `frigate` | `geometry` | `partial` | `False` |
| `tpl-face-detected` | `face-detected` | `frigate` | `insightface` | `partial` | `False` |
| `tpl-face-watchlist` | `face-watchlist` | `frigate` | `insightface` | `partial` | `False` |
| `tpl-identity-correlation` | `identity-correlation` | `frigate` | `rules_composite` | `partial` | `False` |
| `tpl-illegal-parking` | `illegal-parking` | `frigate` | `geometry` | `partial` | `False` |
| `tpl-industrial-intrusion` | `industrial-intrusion` | `frigate` | `rules_composite` | `partial` | `False` |
| `tpl-intrusion` | `intrusion` | `frigate` | `geometry` | `partial` | `False` |
| `tpl-intrusion-after-hours` | `intrusion-after-hours` | `frigate` | `rules_composite` | `partial` | `False` |
| `tpl-line-cross` | `line-cross` | `frigate` | `geometry` | `partial` | `False` |
| `tpl-line-cross-bidir` | `line-cross-bidir` | `frigate` | `geometry` | `partial` | `False` |
| `tpl-line-cross-forbidden` | `line-cross-forbidden` | `frigate` | `geometry` | `partial` | `False` |
| `tpl-loitering` | `loitering` | `frigate` | `geometry` | `partial` | `False` |
| `tpl-loitering-entrance` | `loitering-entrance` | `frigate` | `geometry` | `partial` | `False` |
| `tpl-multi-person-vehicle` | `multi-person-vehicle` | `frigate` | `geometry` | `partial` | `False` |
| `tpl-multi-zone` | `multi-zone` | `frigate` | `geometry` | `partial` | `False` |
| `tpl-object-disappeared` | `object-disappeared` | `hybrid` | `geometry` | `partial` | `False` |
| `tpl-object-removed` | `object-removed` | `hybrid` | `geometry` | `partial` | `False` |
| `tpl-observation-rule-set-n` | `obs-n` | `frigate` | `rules_composite` | `partial` | `False` |
| `tpl-observation-rule-set-or` | `obs-or` | `frigate` | `rules_composite` | `partial` | `False` |
| `tpl-pedestrian-zone` | `pedestrian-zone` | `frigate` | `geometry` | `partial` | `False` |
| `tpl-perimeter-breach` | `perimeter` | `frigate` | `geometry` | `partial` | `False` |
| `tpl-person-stopped` | `person-stopped` | `frigate` | `geometry` | `partial` | `False` |
| `tpl-phone-driving` | `telephone` | `frigate` | `gemini` | `real` | `True` |
| `tpl-plate-detected` | `plate-detected` | `frigate` | `ocr_fusion` | `partial` | `False` |
| `tpl-plate-pipeline` | `plate-pipeline` | `frigate` | `ocr_fusion` | `partial` | `False` |
| `tpl-plate-repeat` | `plate-repeat` | `frigate` | `rules_composite` | `partial` | `False` |
| `tpl-plate-unknown` | `plate-unknown` | `frigate` | `rules_composite` | `partial` | `False` |
| `tpl-plate-whitelist` | `plate-whitelist` | `frigate` | `rules_composite` | `partial` | `False` |
| `tpl-proximity-alert` | `proximity` | `frigate` | `geometry` | `partial` | `False` |
| `tpl-red-light` | `feu` | `hybrid` | `geometry` | `real` | `True` |
| `tpl-seatbelt` | `ceinture` | `frigate` | `gemini` | `real` | `True` |
| `tpl-slow-vehicle` | `slow-vehicle` | `frigate` | `frigate_speed` | `partial` | `False` |
| `tpl-speeding-premium` | `vitesse` | `frigate` | `frigate_speed` | `real` | `True` |
| `tpl-sudden-stop` | `sudden-stop` | `frigate` | `frigate_speed` | `partial` | `False` |
| `tpl-theft-composite` | `theft-composite` | `frigate` | `rules_composite` | `partial` | `False` |
| `tpl-traffic-pipeline` | `traffic-pipeline` | `frigate` | `rules_composite` | `partial` | `False` |
| `tpl-unauthorized-exit` | `unauthorized-exit` | `frigate` | `geometry` | `partial` | `False` |
| `tpl-unknown-face` | `face-unknown` | `frigate` | `insightface` | `partial` | `False` |
| `tpl-unknown-plate` | `plate-unknown` | `frigate` | `rules_composite` | `partial` | `False` |
| `tpl-vehicle-count` | `vehicle-count` | `frigate` | `geometry` | `partial` | `False` |
| `tpl-vehicle-stopped` | `vehicle-stopped` | `frigate` | `geometry` | `partial` | `False` |
| `tpl-video-blur` | `video-blur` | `citevision_local` | `geometry` | `partial` | `False` |
| `tpl-video-darkness` | `video-darkness` | `citevision_local` | `geometry` | `partial` | `False` |
| `tpl-watchlist-match` | `face-watchlist` | `frigate` | `insightface` | `partial` | `False` |
| `tpl-zone-absence` | `zone-absence` | `frigate` | `geometry` | `partial` | `False` |
| `tpl-zone-enter` | `zone-enter` | `frigate` | `geometry` | `partial` | `False` |
| `tpl-zone-exit` | `zone-exit` | `frigate` | `geometry` | `partial` | `False` |
| `tpl-zone-presence` | `zone-presence` | `frigate` | `geometry` | `partial` | `False` |

## Reminder

Passage `partial` → `real` requires recent `validation-evidence/<alias>/…/report.json` with `result=PASS` + gallery + UI (R.3).
