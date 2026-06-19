#!/usr/bin/env python3
"""
Add partial badge labels and post-activation diagnostic translations to fr.json
"""
import json
from pathlib import Path

fr_file = Path("frontend/src/i18n/fr.json")
data = json.loads(fr_file.read_text(encoding="utf-8"))

rules = data.setdefault("rules", {})

# Partial badge translations
partial = rules.setdefault("partial", {})
partial.update({
    "requires_calibration": "Calibration requise",
    "requires_ocr": "Module OCR requis",
    "requires_face_ai": "Module Visage requis",
    "partial_aggregate": "Données partielles"
})

# Post-activation diagnostic translations
activation = rules.setdefault("activation", {})
activation.update({
    "successTitle": "Règle activée",
    "successDesc": "Votre règle surveille {context}. La première alerte devrait arriver en moins de 30 secondes si un événement est détecté.",
    "contextCamera": "la caméra {cameraName}",
    "contextZone": "la zone « {zoneName} » sur {cameraName}",
    "contextLine": "la ligne « {lineName} » sur {cameraName}",
    "watchingTitle": "En attente du premier événement…",
    "watchingDesc": "La règle est active. Le système vérifie le flux vidéo.",
    "noEventTitle": "Aucun événement depuis 3 minutes",
    "noEventDesc": "Vérifiez les points suivants :",
    "checkZone": "Une zone ou ligne est-elle dessinée sur la caméra ?",
    "checkCamera": "La caméra est-elle en ligne et le flux RTSP actif ?",
    "checkAi": "Le moteur IA est-il démarré (voyant vert dans Santé système) ?",
    "checkActivity": "Y a-t-il de l'activité dans le champ de la caméra ?",
    "goToHealth": "Vérifier la santé du système",
    "goToZones": "Gérer les zones"
})

fr_file.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print("Patched fr.json with partial badge + activation diagnostic labels")

# Validate JSON
json.loads(fr_file.read_text(encoding="utf-8"))
print("JSON valid ✓")
