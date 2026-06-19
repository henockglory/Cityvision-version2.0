# Matrice de couverture des règles Citévision v2

Généré le 2026-06-18T10:30:52.275620+00:00 par `scripts/generate-rule-coverage-matrix.py`.

## Synthèse

- Cartes catalogue uniques : **87** (occurrences totales dans les JSON : 96)
- Fiches `ai-capabilities.json` : **90** (90 `supported: true`)
- UI **Disponibles** : **87** | UI **Bientôt** : **0**
- Implémentation : implémenté=70, partiel=17, absent=0, stub=0, nom_incoherent=0
- E2E : **87** testés / **0** sans test  
  - dont **31** live (chemin vidéo→MQTT→alerte) / **56** pytest-fallback

- Fiches capabilities sans carte catalogue : tpl-dwell-time, tpl-object-abandoned, tpl-plate-blocked

## Légende statuts

| Statut | Signification |
|--------|---------------|
| implémenté | Événement IA émis (éventuellement prérequis InsightFace/PaddleOCR/calibration) |
| partiel | Capabilities manquantes, composite incomplet, ou supported:false |
| absent | Événement non émis par le pipeline |
| stub | Stub catalogue explicite (pas de simulation) |
| nom_incoherent | Décalage catalogue vs IA (ex. wrong_direction vs wrong_way) |

## Matrice complète

| ID | Nom | Catégorie | event_type | UI | Statut IA | E2E | Notes |
|----|-----|-----------|------------|-----|-----------|-----|-------|
| `tpl-abandoned-object` | Objet abandonné | objects | `object_appeared` | Disponibles | implémenté | verify-e2e-family-identity.sh | Chaîne IA branchée (YOLO/heuristiques) |
| `tpl-accident` | Accident routier probable | composite | `sudden_stop` | Disponibles | implémenté | verify-e2e-bientot-templates.sh | Émis si calibration caméra configurée |
| `tpl-accident-composite` | Accident (arrêt brutal) | road-enforcement | `sudden_stop` | Disponibles | implémenté | verify-e2e-family-road.sh | Émis si calibration caméra configurée |
| `tpl-behavior-anomaly` | Anomalie comportementale | behavior | `behavior_anomaly` | Disponibles | implémenté | verify-e2e-pytest-catalog.sh | Chaîne IA branchée (YOLO/heuristiques) |
| `tpl-blocked-plate` | Plaque bloquée | identity | `plate_blocked` | Disponibles | implémenté | verify-e2e-pytest-catalog.sh | Émis si PaddleOCR installé |
| `tpl-bottleneck` | Goulot d'étranglement | behavior | `—` | Disponibles | partiel | verify-e2e-pytest-catalog.sh | event_type non extrait de la définition |
| `tpl-carry-object` | Transport d'objet | behavior | `carry_detected` | Disponibles | implémenté | verify-e2e-pytest-catalog.sh | Chaîne IA branchée (YOLO/heuristiques) |
| `tpl-climb-detected` | Escalade détectée | behavior | `climb_detected` | Disponibles | implémenté | verify-e2e-pytest-catalog.sh | Chaîne IA branchée (YOLO/heuristiques) |
| `tpl-congestion` | Embouteillage | road-enforcement | `vehicle_count_threshold` | Disponibles | implémenté | verify-e2e-family-road.sh | Chaîne IA branchée (YOLO/heuristiques) |
| `tpl-crouch-detected` | Position accroupie | behavior | `crouch_detected` | Disponibles | implémenté | verify-e2e-pytest-catalog.sh | Chaîne IA branchée (YOLO/heuristiques) |
| `tpl-crowd-count` | Seuil foule atteint | behavior | `crowd_count_threshold` | Disponibles | implémenté | verify-e2e-pytest-catalog.sh | Chaîne IA branchée (YOLO/heuristiques) |
| `tpl-crowd-density` | Densité foule élevée | behavior | `scene_density_high` | Disponibles | implémenté | verify-e2e-pytest-catalog.sh | Chaîne IA branchée (YOLO/heuristiques) |
| `tpl-crowd-gathering` | Rassemblement foule | behavior | `crowd_gathering` | Disponibles | implémenté | verify-e2e-family-spatial.sh | Chaîne IA branchée (YOLO/heuristiques) |
| `tpl-crowd-panic` | Panique de foule | crowd | `crowd_panic` | Disponibles | implémenté | verify-e2e-bientot-templates.sh | Chaîne IA branchée (YOLO/heuristiques) |
| `tpl-dwell-exceeded` | Dépassement temps de présence | time | `dwell_time_exceeded` | Disponibles | implémenté | verify-e2e-pytest-catalog.sh | Chaîne IA branchée (YOLO/heuristiques) |
| `tpl-erratic-motion` | Mouvement erratique | presence | `—` | Disponibles | partiel | verify-e2e-pytest-catalog.sh | event_type non extrait de la définition |
| `tpl-face-count` | Comptage visages | identity | `—` | Disponibles | partiel | verify-e2e-pytest-catalog.sh | event_type non extrait de la définition |
| `tpl-face-detected` | Visage détecté | identity | `face_detected` | Disponibles | implémenté | verify-e2e-family-identity.sh | Émis si InsightFace installé |
| `tpl-face-repeat` | Visage récurrent | identity | `—` | Disponibles | partiel | verify-e2e-pytest-catalog.sh | event_type non extrait de la définition |
| `tpl-face-watchlist` | Personne liste noire | identity | `face_watchlist_match` | Disponibles | implémenté | verify-e2e-pytest-catalog.sh | Émis si InsightFace installé |
| `tpl-falling` | Chute détectée | behavior | `falling` | Disponibles | implémenté | verify-e2e-pytest-catalog.sh | Chaîne IA branchée (YOLO/heuristiques) |
| `tpl-fight` | Bagarre probable | incident | `fight_detected` | Disponibles | implémenté | verify-e2e-bientot-templates.sh | Chaîne IA branchée (YOLO/heuristiques) |
| `tpl-fighting` | Bagarre détectée | behavior | `fighting` | Disponibles | implémenté | verify-e2e-family-spatial.sh | Chaîne IA branchée (YOLO/heuristiques) |
| `tpl-flow-rate` | Débit piétons élevé | behavior | `—` | Disponibles | partiel | verify-e2e-pytest-catalog.sh | event_type non extrait de la définition |
| `tpl-group-formation` | Attroupement suspect | crowd | `crowd_gathering` | Disponibles | implémenté | verify-e2e-pytest-catalog.sh | Chaîne IA branchée (YOLO/heuristiques) |
| `tpl-identity-correlation` | Corrélation identité | identity | `correlation_match` | Disponibles | implémenté | verify-e2e-pytest-catalog.sh | Chaîne IA branchée (YOLO/heuristiques) |
| `tpl-illegal-parking` | Stationnement illégal | traffic | `vehicle_stopped` | Disponibles | implémenté | verify-e2e-bientot-templates.sh | Chaîne IA branchée (YOLO/heuristiques) |
| `tpl-immobility` | Immobilité prolongée | presence | `stationary` | Disponibles | partiel | verify-e2e-pytest-catalog.sh | métadonnée behavior, pas event_type |
| `tpl-industrial-intrusion` | Intrusion site industriel | industrial | `—` | Disponibles | partiel | verify-e2e-family-spatial.sh | event_type non extrait de la définition |
| `tpl-intrusion` | Intrusion zone interdite | security | `—` | Disponibles | partiel | verify-e2e-family-spatial.sh | event_type non extrait de la définition |
| `tpl-intrusion-after-hours` | Intrusion hors horaires | security | `zone_enter` | Disponibles | implémenté | verify-e2e-family-spatial.sh | Chaîne IA branchée (YOLO/heuristiques) |
| `tpl-intrusion-zone` | Intrusion zone interdite | security | `zone_enter` | Disponibles | implémenté | verify-e2e-family-spatial.sh | Chaîne IA branchée (YOLO/heuristiques) |
| `tpl-line-cross` | Franchissement de ligne | spatial | `—` | Disponibles | partiel | verify-e2e-pytest-catalog.sh | event_type non extrait de la définition |
| `tpl-line-cross-bidir` | Franchissement bidirectionnel | spatial | `line_cross` | Disponibles | implémenté | verify-e2e-family-spatial.sh | Chaîne IA branchée (YOLO/heuristiques) |
| `tpl-line-cross-forbidden` | Franchissement ligne continue | road-enforcement | `line_cross` | Disponibles | implémenté | verify-e2e-family-spatial.sh | Chaîne IA branchée (YOLO/heuristiques) |
| `tpl-loitering` | Présence prolongée (loitering) | time | `loitering` | Disponibles | implémenté | verify-e2e-family-spatial.sh | Chaîne IA branchée (YOLO/heuristiques) |
| `tpl-loitering-entrance` | Flânerie près entrée | security | `loitering_near_entrance` | Disponibles | implémenté | verify-e2e-pytest-catalog.sh | Chaîne IA branchée (YOLO/heuristiques) |
| `tpl-multi-person-vehicle` | Plusieurs personnes, un véhicule | security | `multiple_persons_one_vehicle` | Disponibles | implémenté | verify-e2e-pytest-catalog.sh | Chaîne IA branchée (YOLO/heuristiques) |
| `tpl-multi-zone` | Présence multi-zones | spatial | `zone_enter` | Disponibles | implémenté | verify-e2e-bientot-templates.sh | Chaîne IA branchée (YOLO/heuristiques) |
| `tpl-object-appeared` | Apparition d'objet | presence | `object_appeared` | Disponibles | implémenté | verify-e2e-pytest-catalog.sh | Chaîne IA branchée (YOLO/heuristiques) |
| `tpl-object-disappeared` | Disparition d'objet | presence | `object_disappeared` | Disponibles | implémenté | verify-e2e-pytest-catalog.sh | Chaîne IA branchée (YOLO/heuristiques) |
| `tpl-object-removed` | Objet retiré | objects | `object_removed` | Disponibles | implémenté | verify-e2e-pytest-catalog.sh | Chaîne IA branchée (YOLO/heuristiques) |
| `tpl-pedestrian-zone` | Piéton en zone véhicules | traffic | `—` | Disponibles | partiel | verify-e2e-pytest-catalog.sh | event_type non extrait de la définition |
| `tpl-perimeter-breach` | Intrusion périmétrique | spatial | `perimeter_breach` | Disponibles | implémenté | verify-e2e-family-spatial.sh | Chaîne IA branchée (YOLO/heuristiques) |
| `tpl-person-stopped` | Personne immobile prolongée | behavior | `person_stopped` | Disponibles | implémenté | verify-e2e-pytest-catalog.sh | Chaîne IA branchée (YOLO/heuristiques) |
| `tpl-phone-driving` | Téléphone au volant | road-enforcement | `phone_driving` | Disponibles | implémenté | verify-e2e-bientot-templates.sh | Chaîne IA branchée (YOLO/heuristiques) |
| `tpl-plate-detected` | Plaque détectée | identity | `plate_detected` | Disponibles | implémenté | verify-e2e-family-identity.sh | Émis si PaddleOCR installé |
| `tpl-plate-pipeline` | Plaque détectée (OCR) | road-enforcement | `plate_detected` | Disponibles | implémenté | verify-e2e-family-identity.sh | Émis si PaddleOCR installé |
| `tpl-plate-repeat` | Plaque récurrente | identity | `plate_detected` | Disponibles | implémenté | verify-e2e-family-identity.sh | Émis si PaddleOCR installé |
| `tpl-plate-unknown` | Plaque non enregistrée | identity | `plate_unknown` | Disponibles | implémenté | verify-e2e-pytest-catalog.sh | Émis si PaddleOCR installé |
| `tpl-plate-whitelist` | Plaque autorisée | identity | `plate_allowed` | Disponibles | implémenté | verify-e2e-pytest-catalog.sh | Émis si PaddleOCR installé |
| `tpl-proximity-alert` | Proximité personne-véhicule | security | `person_vehicle_proximity` | Disponibles | implémenté | verify-e2e-pytest-catalog.sh | Chaîne IA branchée (YOLO/heuristiques) |
| `tpl-queue-forming` | Formation de file | behavior | `queue_forming` | Disponibles | implémenté | verify-e2e-pytest-catalog.sh | Chaîne IA branchée (YOLO/heuristiques) |
| `tpl-red-light` | Feu rouge | road-enforcement | `red_light_violation` | Disponibles | implémenté | verify-e2e-bientot-templates.sh | Chaîne IA branchée (YOLO/heuristiques) |
| `tpl-running` | Personne en course | behavior | `running` | Disponibles | implémenté | verify-e2e-family-identity.sh | Chaîne IA branchée (YOLO/heuristiques) |
| `tpl-running-person` | Course / fuite | speed | `—` | Disponibles | partiel | verify-e2e-family-identity.sh | event_type non extrait de la définition |
| `tpl-scene-occupancy` | Occupation scène | behavior | `—` | Disponibles | partiel | verify-e2e-pytest-catalog.sh | event_type non extrait de la définition |
| `tpl-seatbelt` | Ceinture de sécurité | road-enforcement | `seatbelt_violation` | Disponibles | implémenté | verify-e2e-bientot-templates.sh | Chaîne IA branchée (YOLO/heuristiques) |
| `tpl-slow-vehicle` | Véhicule trop lent | traffic | `speed_below_minimum` | Disponibles | implémenté | verify-e2e-pytest-catalog.sh | Émis si calibration caméra configurée |
| `tpl-speed-threshold` | Vitesse > seuil | traffic | `—` | Disponibles | partiel | verify-e2e-pytest-catalog.sh | event_type non extrait de la définition |
| `tpl-speeding` | Excès de vitesse véhicule | speed | `—` | Disponibles | partiel | verify-e2e-pytest-catalog.sh | event_type non extrait de la définition |
| `tpl-speeding-premium` | Excès de vitesse | road-enforcement | `speeding` | Disponibles | implémenté | verify-e2e-pytest-catalog.sh | Émis si calibration caméra configurée |
| `tpl-stopped-traffic` | Véhicule arrêté sur voie | traffic | `vehicle_stopped` | Disponibles | implémenté | verify-e2e-family-road.sh | Chaîne IA branchée (YOLO/heuristiques) |
| `tpl-sudden-stop` | Arrêt brusque | speed | `sudden_stop` | Disponibles | implémenté | verify-e2e-family-road.sh | Émis si calibration caméra configurée |
| `tpl-tailgating` | Tailgating | behavior | `tailgating` | Disponibles | implémenté | verify-e2e-family-spatial.sh | Chaîne IA branchée (YOLO/heuristiques) |
| `tpl-theft-composite` | Vol suspect (composite) | composite | `zone_enter` | Disponibles | implémenté | verify-e2e-sequence-theft.sh | Chaîne IA branchée (YOLO/heuristiques) |
| `tpl-traffic-jam` | Embouteillage | traffic | `—` | Disponibles | partiel | verify-e2e-pytest-catalog.sh | event_type non extrait de la définition |
| `tpl-traffic-pipeline` | Pipeline voiture → plaque + vitesse | road-enforcement | `vehicle_corridor` | Disponibles | implémenté | verify-e2e-pytest-catalog.sh | Émis si PaddleOCR installé |
| `tpl-unauthorized-exit` | Sortie non autorisée | spatial | `unauthorized_exit` | Disponibles | implémenté | verify-e2e-spatial-semantic.sh | Chaîne IA branchée (YOLO/heuristiques) |
| `tpl-unknown-face` | Visage inconnu | identity | `face_unknown` | Disponibles | implémenté | verify-e2e-pytest-catalog.sh | Émis si InsightFace installé |
| `tpl-unknown-plate` | Plaque inconnue | identity | `plate_unknown` | Disponibles | implémenté | verify-e2e-pytest-catalog.sh | Émis si PaddleOCR installé |
| `tpl-vandalism` | Vandalisme suspect | composite | `crowd_gathering` | Disponibles | implémenté | verify-e2e-bientot-templates.sh | Chaîne IA branchée (YOLO/heuristiques) |
| `tpl-vehicle-count` | Nombre véhicules élevé | behavior | `vehicle_count_threshold` | Disponibles | implémenté | verify-e2e-family-road.sh | Chaîne IA branchée (YOLO/heuristiques) |
| `tpl-vehicle-stopped` | Véhicule arrêté | behavior | `vehicle_stopped` | Disponibles | implémenté | verify-e2e-family-road.sh | Chaîne IA branchée (YOLO/heuristiques) |
| `tpl-vehicle-wrong-direction` | Véhicule sens interdit | traffic | `wrong_way` | Disponibles | implémenté | verify-e2e-pytest-catalog.sh | Chaîne IA branchée (YOLO/heuristiques) |
| `tpl-video-blur` | Vidéo floue | quality | `video_blur` | Disponibles | implémenté | verify-e2e-pytest-catalog.sh | Chaîne IA branchée (YOLO/heuristiques) |
| `tpl-video-darkness` | Vidéo sombre | quality | `video_darkness` | Disponibles | implémenté | verify-e2e-pytest-catalog.sh | Chaîne IA branchée (YOLO/heuristiques) |
| `tpl-wandering` | Errance prolongée | presence | `—` | Disponibles | partiel | verify-e2e-family-identity.sh | event_type non extrait de la définition |
| `tpl-watchlist-match` | Visage liste de surveillance | identity | `face_watchlist_match` | Disponibles | implémenté | verify-e2e-pytest-catalog.sh | Émis si InsightFace installé |
| `tpl-wrong-direction` | Sens interdit | spatial | `wrong_way` | Disponibles | implémenté | verify-e2e-pytest-catalog.sh | Chaîne IA branchée (YOLO/heuristiques) |
| `tpl-wrong-lane` | Mauvaise voie | traffic | `wrong_way` | Disponibles | implémenté | verify-e2e-pytest-catalog.sh | Chaîne IA branchée (YOLO/heuristiques) |
| `tpl-wrong-way` | Sens interdit | behavior | `wrong_way` | Disponibles | implémenté | verify-e2e-family-spatial.sh | Chaîne IA branchée (YOLO/heuristiques) |
| `tpl-zone-absence` | Absence prolongée dans une zone | presence | `zone_absence` | Disponibles | implémenté | verify-e2e-pytest-catalog.sh | Chaîne IA branchée (YOLO/heuristiques) |
| `tpl-zone-enter` | Entrée dans une zone | spatial | `zone_enter` | Disponibles | implémenté | verify-e2e-family-spatial.sh | Chaîne IA branchée (YOLO/heuristiques) |
| `tpl-zone-exit` | Sortie d'une zone | spatial | `zone_exit` | Disponibles | implémenté | verify-e2e-family-spatial.sh | Chaîne IA branchée (YOLO/heuristiques) |
| `tpl-zone-occupancy` | Occupation zone élevée | spatial | `—` | Disponibles | partiel | verify-e2e-pytest-catalog.sh | event_type non extrait de la définition |
| `tpl-zone-presence` | Présence dans une zone | presence | `zone_presence` | Disponibles | implémenté | verify-e2e-zone-alert.sh | Chaîne IA branchée (YOLO/heuristiques) |

## Règles Bientôt (action requise)

