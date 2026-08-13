# Matrice d'honnêteté des règles CitéVision

> Base générée par `scripts/generate-rule-matrix.mjs` — lignes ci-dessous **mises à jour manuellement** (honesty sync 2026-08) pour redirects / wrong_way / compteurs.

**Note honesty** : les redirects catalogue (traffic-pipeline, plate-pipeline, face-watchlist, plate-unknown, illegal-parking, object-disappeared) ne sont plus des produits live. Sens interdit = `tpl-wrong-way` (zone arêtes). Observation = « Compteur scénario ».

| Catégorie | Règle | Statut | Pré-requis / Raison |
|-----------|-------|--------|----------------------|
| behavior | Densité foule élevée | 🟢 Réel | — |
| behavior | Nombre véhicules élevé | 🟢 Réel | — |
| behavior | Personne immobile prolongée | 🟢 Réel | — |
| behavior | Seuil foule atteint | 🟢 Réel | — |
| behavior | Véhicule arrêté | 🟢 Réel | — |
| identity | Corrélation visage + plaque | 🟡 Partiel | RULE_SET face_watchlist_match + plate_detected (120 s) — InsightFace + OCR. |
| identity | Plaque autorisée | 🟡 Partiel | Nécessite Gemini OCR (GEMINI_ENABLED) ou PaddleOCR + liste blanche configurée. |
| identity | Plaque bloquée | 🟡 Partiel | Nécessite Gemini OCR (GEMINI_ENABLED) ou PaddleOCR + liste noire configurée. |
| identity | Plaque détectée | 🟡 Partiel | Nécessite Gemini OCR (GEMINI_ENABLED) ou PaddleOCR actif sur une zone dédiée. |
| identity | Plaque inconnue | 🟡 Partiel | Nécessite Gemini OCR (GEMINI_ENABLED) ou PaddleOCR + liste blanche configurée. |
| identity | Plaque récurrente | 🟡 Partiel | Nécessite le module de lecture de plaques (PaddleOCR) actif sur une zone dédiée. |
| identity | Visage détecté | 🟡 Partiel | Module face local ou Frigate→Gemini. Badge partial — pas de full/real sans validation. |
| identity | Visage inconnu | 🟡 Partiel | InsightFace recommandé ; ou Frigate person∩zone → Gemini (FRIGATE_VLM_BRIDGE). Partial tant que non validé bout-en-bout. |
| identity | Visage liste de surveillance | 🟡 Partiel | Préfère InsightFace + embeddings watchlist. Avec FRIGATE_VLM_BRIDGE : person∩zone Frigate → Gemini. Partial jusqu'à validate_rule. |
| industrial | Intrusion site industriel | 🟢 Réel | — |
| objects | Objet abandonné | 🟡 Partiel | Bridge Frigate bags/umbrella ; event `object_abandoned`. |
| objects | Objet retiré | 🟢 Réel | — |
| presence | Absence prolongée dans une zone | 🟢 Réel | — |
| presence | Présence dans une zone | 🟢 Réel | — |
| quality | Vidéo floue | 🟢 Réel | — |
| quality | Vidéo sombre | 🟢 Réel | — |
| road-enforcement | Ceinture de sécurité | 🟡 Partiel | Nécessite FRIGATE_VLM_BRIDGE + GEMINI_ENABLED + clé API. Partial jusqu'à validate_rule — pas de claim full/real. |
| road-enforcement | Embouteillage | 🟢 Réel | — |
| road-enforcement | Excès de vitesse | 🟡 Partiel | Exige polygone 4 points + edge_distances_m (Frigate) ou calibration zone_speed locale. Partial tant que non validé bout-en-bout. |
| road-enforcement | Feu rouge | 🟡 Partiel | Heuristique HSV (pas un modèle feu dédié). Preuve complète possible via frigate_track ou fallback demo_ring_buffer — vérifier capture_source. |
| road-enforcement | Franchissement ligne continue | 🟢 Réel | — |
| road-enforcement | Sens interdit | 🟢 Réel | Zone `wrong_way` + arêtes entry/exit ; event `wrong_way` (bridge ou local XOR). |
| road-enforcement | Téléphone au volant | 🟡 Partiel | Nécessite FRIGATE_VLM_BRIDGE + GEMINI_ENABLED + clé API. Partial jusqu'à validate_rule — pas de badge full. |
| security | Flânerie près entrée | 🟢 Réel | — |
| security | Intrusion hors horaires | 🟢 Réel | — |
| security | Intrusion zone interdite | 🟢 Réel | — |
| security | Plusieurs personnes, un véhicule | 🟢 Réel | — |
| security | Proximité personne-véhicule | 🟢 Réel | — |
| spatial | Compteur scénario (N types) | 🟢 Réel | Composite rules-engine — ≥2 event chips ; pas un détecteur. |
| spatial | Compteur scénario (OU) | 🟢 Réel | Composite rules-engine — ≥2 event chips ; pas un détecteur. |
| spatial | Entrée dans une zone | 🟢 Réel | — |
| spatial | Franchissement bidirectionnel | 🟢 Réel | — |
| spatial | Franchissement de ligne | 🟢 Réel | — |
| spatial | Intrusion périmétrique | 🟢 Réel | — |
| spatial | Présence multi-zones | 🟢 Réel | — |
| spatial | Sortie d'une zone | 🟢 Réel | — |
| spatial | Sortie non autorisée | 🟢 Réel | — |
| speed | Arrêt brusque | 🟡 Partiel | Nécessite une calibration caméra pour détecter les variations de vitesse |
| time | Dépassement temps de présence | 🟢 Réel | — |
| time | Présence prolongée (loitering) | 🟢 Réel | — |
| traffic | Piéton en zone véhicules | 🟢 Réel | — |
| traffic | Véhicule trop lent | 🟡 Partiel | Nécessite une calibration caméra pour estimer les vitesses relatives |

## Redirects (plus de fiches live)

| Ancien template | Redirige vers |
|-----------------|---------------|
| `tpl-traffic-pipeline` | `tpl-speeding-premium` |
| `tpl-plate-pipeline` | `tpl-plate-detected` |
| `tpl-face-watchlist` | `tpl-watchlist-match` |
| `tpl-plate-unknown` | `tpl-unknown-plate` |
| `tpl-illegal-parking` | `tpl-vehicle-stopped` |
| `tpl-object-disappeared` | `tpl-object-removed` |
| `tpl-wrong-lane` / `tpl-wrong-direction` | `tpl-wrong-way` |

## Légende

- **🟢 Réel** : fonctionne immédiatement avec le moteur par défaut (YOLOv8 + tracking / Frigate bridge selon règle).
- **🟡 Partiel** : fonctionne après une étape supplémentaire (calibration, ANPR, modèle ONNX, reconnaissance faciale) ou détection heuristique « bêta ».
- **🔴 Non supporté** : présent au catalogue mais pas câblé de bout en bout.
