# Matrice d'honnêteté des règles CitéVision

> Généré automatiquement par `scripts/generate-rule-matrix.mjs` — ne pas éditer à la main.

**Total : 89 templates** — 🟢 70 réels · 🟡 19 partiels · 🔴 0 non supportés.

| Catégorie | Règle | Statut | Pré-requis / Raison |
|-----------|-------|--------|----------------------|
| behavior | Anomalie comportementale | 🟢 Réel | — |
| behavior | Bagarre détectée | 🟢 Réel | — |
| behavior | Chute détectée | 🟢 Réel | — |
| behavior | Débit piétons élevé | 🟡 Partiel | Débit piéton/véhiculaire : agrégat flow_rate pas encore émis par l'IA standard |
| behavior | Densité foule élevée | 🟢 Réel | — |
| behavior | Escalade détectée | 🟢 Réel | — |
| behavior | Formation de file | 🟢 Réel | — |
| behavior | Goulot d'étranglement | 🟡 Partiel | Détection de goulot d'étranglement : agrégat flow_bottleneck pas encore émis par l'IA standard |
| behavior | Nombre véhicules élevé | 🟢 Réel | — |
| behavior | Occupation scène | 🟡 Partiel | Taux d'occupation de zone : agrégat scene_occupancy pas encore émis par l'IA standard |
| behavior | Personne en course | 🟢 Réel | — |
| behavior | Personne immobile prolongée | 🟢 Réel | — |
| behavior | Position accroupie | 🟢 Réel | — |
| behavior | Rassemblement foule | 🟢 Réel | — |
| behavior | Sens interdit | 🟢 Réel | — |
| behavior | Seuil foule atteint | 🟢 Réel | — |
| behavior | Tailgating | 🟢 Réel | — |
| behavior | Transport d'objet | 🟡 Partiel | Détecte le transport d'objets via l'heuristique carry_detected — fiabilité dépend de la taille des objets et de la résolution flux |
| behavior | Véhicule arrêté | 🟢 Réel | — |
| composite | Accident routier probable | 🟢 Réel | — |
| composite | Vandalisme suspect | 🟢 Réel | — |
| composite | Vol suspect (composite) | 🟢 Réel | — |
| crowd | Attroupement suspect | 🟡 Partiel | Attroupement détecté via crowd_gathering — le seuil neighbor_count >= 5 peut nécessiter ajustement selon densité habituelle |
| crowd | Panique de foule | 🟢 Réel | — |
| identity | Comptage visages | 🟡 Partiel | Comptage des visages nécessite le module InsightFace (non installé par défaut) |
| identity | Corrélation identité | 🟢 Réel | — |
| identity | Personne liste noire | 🟡 Partiel | Nécessite le module InsightFace (non installé par défaut) |
| identity | Plaque autorisée | 🟢 Réel | — |
| identity | Plaque bloquée | 🟢 Réel | — |
| identity | Plaque détectée | 🟢 Réel | — |
| identity | Plaque inconnue | 🟢 Réel | — |
| identity | Plaque non enregistrée | 🟡 Partiel | Nécessite le module PaddleOCR (non installé par défaut) |
| identity | Plaque récurrente | 🟢 Réel | — |
| identity | Visage détecté | 🟢 Réel | — |
| identity | Visage inconnu | 🟢 Réel | — |
| identity | Visage liste de surveillance | 🟡 Partiel | Correspondance liste noire nécessite le module InsightFace + base de données de visages configurée |
| identity | Visage récurrent | 🟢 Réel | — |
| incident | Bagarre probable | 🟢 Réel | — |
| industrial | Intrusion site industriel | 🟢 Réel | — |
| objects | Objet abandonné | 🟢 Réel | — |
| objects | Objet retiré | 🟢 Réel | — |
| presence | Absence prolongée dans une zone | 🟢 Réel | — |
| presence | Apparition d'objet | 🟢 Réel | — |
| presence | Disparition d'objet | 🟢 Réel | — |
| presence | Errance prolongée | 🟡 Partiel | Errance détectée via heuristique wandering — nécessite activité continue ≥45s dans le champ |
| presence | Immobilité prolongée | 🟢 Réel | — |
| presence | Mouvement erratique | 🟢 Réel | — |
| presence | Présence dans une zone | 🟢 Réel | — |
| quality | Vidéo floue | 🟢 Réel | — |
| quality | Vidéo sombre | 🟢 Réel | — |
| road-enforcement | Accident (arrêt brutal) | 🟡 Partiel | Détection composite : nécessite calibration caméra pour les métriques de vitesse |
| road-enforcement | Ceinture de sécurité | 🟡 Partiel | Nécessite le modèle ONNX « seatbelt » (scripts/download-secondary-models) + caméra orientée conducteur (angle ≤45°). Repli heuristique bêta sinon. |
| road-enforcement | Embouteillage | 🟢 Réel | — |
| road-enforcement | Excès de vitesse | 🟡 Partiel | Nécessite une calibration caméra (homographie) + module ANPR optionnel |
| road-enforcement | Feu rouge | 🟢 Réel | — |
| road-enforcement | Franchissement ligne continue | 🟢 Réel | — |
| road-enforcement | Pipeline voiture → plaque + vitesse | 🟡 Partiel | Pipeline multi-étapes : nécessite calibration vitesse + module ANPR (PaddleOCR) |
| road-enforcement | Plaque détectée (OCR) | 🟢 Réel | — |
| road-enforcement | Sens interdit | 🟢 Réel | — |
| road-enforcement | Téléphone au volant | 🟡 Partiel | Nécessite le modèle ONNX « driver_phone » (scripts/download-secondary-models). Repli heuristique bêta sinon — fiabilité variable. |
| security | Flânerie près entrée | 🟢 Réel | — |
| security | Intrusion hors horaires | 🟢 Réel | — |
| security | Intrusion zone interdite | 🟢 Réel | — |
| security | Intrusion zone interdite | 🟢 Réel | — |
| security | Plusieurs personnes, un véhicule | 🟢 Réel | — |
| security | Proximité personne-véhicule | 🟢 Réel | — |
| spatial | Entrée dans une zone | 🟢 Réel | — |
| spatial | Franchissement bidirectionnel | 🟢 Réel | — |
| spatial | Franchissement de ligne | 🟢 Réel | — |
| spatial | Intrusion périmétrique | 🟢 Réel | — |
| spatial | Occupation zone élevée | 🟢 Réel | — |
| spatial | Présence multi-zones | 🟢 Réel | — |
| spatial | Sens interdit | 🟢 Réel | — |
| spatial | Sortie d'une zone | 🟢 Réel | — |
| spatial | Sortie de zone | 🟢 Réel | — |
| spatial | Sortie non autorisée | 🟢 Réel | — |
| speed | Arrêt brusque | 🟡 Partiel | Nécessite une calibration caméra pour détecter les variations de vitesse |
| speed | Course / fuite | 🟢 Réel | — |
| speed | Excès de vitesse véhicule | 🟡 Partiel | Nécessite une calibration caméra (homographie) pour mesurer la vitesse en km/h |
| time | Dépassement temps de présence | 🟢 Réel | — |
| time | Présence prolongée (loitering) | 🟢 Réel | — |
| traffic | Embouteillage | 🟢 Réel | — |
| traffic | Mauvaise voie | 🟢 Réel | — |
| traffic | Piéton en zone véhicules | 🟢 Réel | — |
| traffic | Stationnement illégal | 🟢 Réel | — |
| traffic | Véhicule arrêté sur voie | 🟢 Réel | — |
| traffic | Véhicule sens interdit | 🟢 Réel | — |
| traffic | Véhicule trop lent | 🟡 Partiel | Nécessite une calibration caméra pour estimer les vitesses relatives |
| traffic | Vitesse > seuil | 🟡 Partiel | Nécessite une calibration caméra (homographie) pour mesurer la vitesse en km/h |

## Légende

- **🟢 Réel** : fonctionne immédiatement avec le moteur par défaut (YOLOv8 + tracking).
- **🟡 Partiel** : fonctionne après une étape supplémentaire (calibration, ANPR, modèle ONNX, reconnaissance faciale) ou détection heuristique « bêta ».
- **🔴 Non supporté** : présent au catalogue mais pas câblé de bout en bout.
