# Catalogue honnête Frigate + Gemini

Architecture : **zone → Frigate (où/quand/objet) → Gemini (oui/non sémantique) → moteur règles → preuves**.

Pas de claim « 5/5 validé » ici — intégration catalogue/runtime uniquement.

## Mapping zone → event → décideur

| Famille | Zones (ZoneEditor) | Init (géométrie) | Décision |
|---------|--------------------|------------------|----------|
| Ceinture | 1× `seatbelt` | Frigate véhicule∩zone | Gemini → `seatbelt_violation` |
| Téléphone | 1× `phone_use` | Frigate véhicule∩zone | Gemini → `phone_use_violation` |
| Feu rouge | 2× `traffic_light_color` + `red_light_observation` | Frigate véhicule∩observation | Gemini → `red_light_violation` |
| Vitesse | 1× `speed_measurement` + distances m | Frigate speed estimate | Moteur (`speed_limit_kmh`) — **pas** Gemini |
| Plaques | 1× `plate_ocr` | Frigate véhicule∩zone | Gemini OCR → `plate_detected` ; listes moteur → `plate_blocked` / `plate_allowed` / `plate_unknown` |
| Visages | 1× zone person (hors behaviors cabine/feu/plaque) | Frigate person∩zone | Gemini → `face_detected` (+ `face_unknown` / `face_watchlist_match` si watchlist) |
| Spatial / temps | zones / lignes | Frigate ou générateur spatial | Moteur (`zone_enter`, `line_cross`, `loitering`, …) |

## Kill-switches

| Variable | Rôle |
|----------|------|
| `FRIGATE_VLM_BRIDGE=1` | Frigate MQTT → crop → Gemini ; coupe YOLO cabine, Paddle local, HSV feu |
| `FRIGATE_SPEED_BRIDGE=1` | Vitesse via Frigate ; désactive `zone_speed` local |
| `GEMINI_ENABLED=1` + `GEMINI_API_KEY` | Juge VLM / OCR |
| `GEMINI_MODEL=gemini-3.1-flash-lite` | Modèle runtime recommandé |
| `FRIGATE_VLM_BRIDGE_CROP_MODE=vehicle_bbox` | Crop cabine recommandé (leçons Port de Ceinture) |

## Purge (18 event_types)

Absents du catalogue et bloqués fail-closed à la publication :

`phone_driving`, `fighting`, `falling`, `fight_detected`, `traffic_light_state`, `behavior_anomaly`, `running`, `crowd_panic`, `crowd_gathering`, `queue_forming`, `erratic_motion`, `wandering`, `rapid_activity`, `tailgating`, `carry_detected`, `climb_detected`, `crouch_detected`, `object_appeared`.

Remplacements : `phone_driving` → `phone_use_violation` ; présence → `zone_enter` ; abandon → `object_abandoned` ; feu → `red_light_violation` uniquement.

## Badges [A.4]

Règles Gemini (ceinture, téléphone, feu, plaque, faces) = **`partial`** jusqu’à `validate_rule` (étape tests ultérieure). Jamais `supported: true` sur heuristique morte.

## Corrélation identité

Pas de prompt VLM « correlation ». Le moteur peut lier des events déjà émis (`face_*`, `plate_*`) → `correlation_match` si encore au catalogue.

Voir aussi [ENV-PLATFORM.md](./ENV-PLATFORM.md), [FRIGATE-SYNC-HONESTY.md](./FRIGATE-SYNC-HONESTY.md).
