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
| Visages | 1× zone person (hors behaviors cabine/feu/plaque) | Frigate person∩zone | Vote identité **Frigate > InsightFace > Gemini** → `face_watchlist_match` / `face_unknown` (+ `face_detected` audit) |
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

Pas de prompt VLM « correlation ». Catalogue : `tpl-identity-correlation` = **RULE_SET** `face_watchlist_match` + `plate_detected` (fenêtre 120 s). L’event historique `correlation_match` n’est plus la promesse produit sous ce template.

Voir aussi [ENV-PLATFORM.md](./ENV-PLATFORM.md), [FRIGATE-SYNC-HONESTY.md](./FRIGATE-SYNC-HONESTY.md), [COMPOSITES-ORCHESTRATION.md](./COMPOSITES-ORCHESTRATION.md).

## Append 2026-08-02 — cabine vehicle_bbox, fusion OCR/face

| Décision | Valeur verrouillée |
|---|---|
| Crop cabine | **`vehicle_bbox` exclusivement** — `driver_roi` retiré du runtime bridge |
| Emit cabine | **Oui/non** sur `violation` + confiance — **plus de gate `visible=false`** |
| OCR plaque | **Gemini + PaddleOCR** en parallèle sur le même crop Frigate → `gemini_paddle_fusion` |
| Visage | **Fusion Frigate → InsightFace → Gemini** sur crop person Frigate (`identity_votes` + `winner`) ; XOR full-frame InsightFace/Gemini quand bridge ON |
| Modèle | **`gemini-3.1-flash-lite`** (défaut `config.py`) |

Sous `FRIGATE_VLM_BRIDGE=1` : ONNX cabine local reste coupé ; Paddle live + bridge fusion coexistent pour les plaques ; InsightFace tourne **uniquement** sur crops Frigate (pas RTSP full-frame).

## Append 2026-08-08 — face watchlist photo + vote triple

| Décision | Valeur verrouillée |
|---|---|
| Source de vérité | CiteVision UI `surveillance_lists` (photo + label) |
| Embedding | InsightFace via `POST /identity/face/embed` → `metadata.embedding` |
| Miroir Frigate | Face Library `create` + `register` à l’enrôlement ; `face_recognition.enabled` dans le compiler si watchlist/règle face |
| Vote live | Frigate (`sub_label` puis `/faces/recognize`) > InsightFace cosine > Gemini multimodal same-person |
| Badge catalogue | **`partial`** jusqu’à `validate_rule` face — pas de claim `real` / 5/5 |
| Fail-closed | Timeout/erreur Gemini ou Frigate = abstention, jamais fabrication de match |
