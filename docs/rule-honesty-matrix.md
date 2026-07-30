# Matrice d'honnêteté des règles CitéVision

> Généré automatiquement par `scripts/generate-rule-matrix.mjs` — ne pas éditer à la main.

**Total : 54 templates** — 🟢 34 réels · 🟡 20 partiels · 🔴 0 non supportés.

| Catégorie | Règle | Statut | Pré-requis / Raison |
|-----------|-------|--------|----------------------|
| behavior | Densité foule élevée | 🟢 Réel | — |
| behavior | Nombre véhicules élevé | 🟢 Réel | — |
| behavior | Personne immobile prolongée | 🟢 Réel | — |
| behavior | Seuil foule atteint | 🟢 Réel | — |
| behavior | Véhicule arrêté | 🟢 Réel | — |
| composite | Vol suspect (composite) | 🟢 Réel | — |
| identity | Corrélation identité | 🟡 Partiel | Corrélation visage↔plaque : nécessite les modules InsightFace et PaddleOCR actifs simultanément. |
| identity | Personne liste noire | 🟡 Partiel | InsightFace recommandé ; Gemini VLM optionnel (partial) si GEMINI_ENABLED — pas de claim full. |
| identity | Plaque autorisée | 🟡 Partiel | Nécessite Gemini OCR (GEMINI_ENABLED) ou PaddleOCR + liste blanche configurée. |
| identity | Plaque bloquée | 🟡 Partiel | Nécessite Gemini OCR (GEMINI_ENABLED) ou PaddleOCR + liste noire configurée. |
| identity | Plaque détectée | 🟡 Partiel | Nécessite Gemini OCR (GEMINI_ENABLED) ou PaddleOCR actif sur une zone dédiée. |
| identity | Plaque inconnue | 🟡 Partiel | Nécessite Gemini OCR (GEMINI_ENABLED) ou PaddleOCR + liste blanche configurée. |
| identity | Plaque non enregistrée | 🟡 Partiel | Nécessite le module PaddleOCR (non installé par défaut) |
| identity | Plaque récurrente | 🟡 Partiel | Nécessite le module de lecture de plaques (PaddleOCR) actif sur une zone dédiée. |
| identity | Visage détecté | 🟡 Partiel | Module face local ou Frigate→Gemini. Badge partial — pas de full/real sans validation. |
| identity | Visage inconnu | 🟡 Partiel | InsightFace recommandé ; ou Frigate person∩zone → Gemini (FRIGATE_VLM_BRIDGE). Partial tant que non validé bout-en-bout. |
| identity | Visage liste de surveillance | 🟡 Partiel | Préfère InsightFace + embeddings watchlist. Avec FRIGATE_VLM_BRIDGE : person∩zone Frigate → Gemini. Partial jusqu'à validate_rule. |
| industrial | Intrusion site industriel | 🟢 Réel | — |
| objects | Objet abandonné | 🟡 Partiel | Dépend du détecteur abandoned analytics ; distinct de object_appeared (heuristique durée). |
| objects | Objet retiré | 🟢 Réel | — |
| presence | Absence prolongée dans une zone | 🟢 Réel | — |
| presence | Disparition d'objet | 🟢 Réel | — |
| presence | Présence dans une zone | 🟢 Réel | — |
| quality | Vidéo floue | 🟢 Réel | — |
| quality | Vidéo sombre | 🟢 Réel | — |
| road-enforcement | Ceinture de sécurité | 🟡 Partiel | Nécessite FRIGATE_VLM_BRIDGE + GEMINI_ENABLED + clé API. Partial jusqu'à validate_rule — pas de claim full/real. |
| road-enforcement | Embouteillage | 🟢 Réel | — |
| road-enforcement | Excès de vitesse | 🟡 Partiel | Exige polygone 4 points + edge_distances_m (Frigate) ou calibration zone_speed locale. Partial tant que non validé bout-en-bout. |
| road-enforcement | Feu rouge | 🟡 Partiel | Heuristique HSV (pas un modèle feu dédié). Preuve complète possible via frigate_track ou fallback demo_ring_buffer — vérifier capture_source. |
| road-enforcement | Franchissement ligne continue | 🟢 Réel | — |
| road-enforcement | Pipeline voiture → plaque + vitesse | 🟡 Partiel | Pipeline multi-étapes : nécessite calibration vitesse + module ANPR (PaddleOCR) |
| road-enforcement | Plaque détectée (OCR) | 🟡 Partiel | Nécessite GEMINI_ENABLED (OCR cloud) ou PaddleOCR local — partial jusqu'à validate_rule. |
| road-enforcement | Téléphone au volant | 🟡 Partiel | Nécessite FRIGATE_VLM_BRIDGE + GEMINI_ENABLED + clé API. Partial jusqu'à validate_rule — pas de badge full. |
| security | Flânerie près entrée | 🟢 Réel | — |
| security | Intrusion hors horaires | 🟢 Réel | — |
| security | Intrusion zone interdite | 🟢 Réel | — |
| security | Plusieurs personnes, un véhicule | 🟢 Réel | — |
| security | Proximité personne-véhicule | 🟢 Réel | — |
| spatial | Comptage ensemble (N-sur-M) | 🟢 Réel | — |
| spatial | Comptage ensemble (OU) | 🟢 Réel | — |
| spatial | Entrée dans une zone | 🟢 Réel | — |
| spatial | Franchissement bidirectionnel | 🟢 Réel | — |
| spatial | Franchissement de ligne | 🟢 Réel | — |
| spatial | Intrusion périmétrique | 🟢 Réel | — |
| spatial | Présence multi-zones | 🟢 Réel | — |
| spatial | Sortie d'une zone | 🟢 Réel | — |
| spatial | Sortie de zone | 🟢 Réel | — |
| spatial | Sortie non autorisée | 🟢 Réel | — |
| speed | Arrêt brusque | 🟡 Partiel | Nécessite une calibration caméra pour détecter les variations de vitesse |
| time | Dépassement temps de présence | 🟢 Réel | — |
| time | Présence prolongée (loitering) | 🟢 Réel | — |
| traffic | Piéton en zone véhicules | 🟢 Réel | — |
| traffic | Stationnement illégal | 🟢 Réel | — |
| traffic | Véhicule trop lent | 🟡 Partiel | Nécessite une calibration caméra pour estimer les vitesses relatives |

## Légende

- **🟢 Réel** : fonctionne immédiatement avec le moteur par défaut (YOLOv8 + tracking).
- **🟡 Partiel** : fonctionne après une étape supplémentaire (calibration, ANPR, modèle ONNX, reconnaissance faciale) ou détection heuristique « bêta ».
- **🔴 Non supporté** : présent au catalogue mais pas câblé de bout en bout.
