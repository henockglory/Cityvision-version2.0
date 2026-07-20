#!/usr/bin/env python3
"""Patch fr.json with all missing keys for the UX revolution."""
from pathlib import Path
import json

fr_file = Path("frontend/src/i18n/fr.json")
data = json.loads(fr_file.read_text(encoding="utf-8"))

rules = data.setdefault("rules", {})

# Keys for reset all
rules.update({
    "resetAll": "Réinitialiser toutes les règles",
    "resetError": "Erreur lors de la réinitialisation. Veuillez réessayer.",
    "confirmResetAllTitle": "Réinitialiser toutes les règles ?",
    "confirmResetAllMessage": "Cette action supprimera définitivement {{count}} règles configurées. Vous repartirez d'une page vierge.",
})

# Catalog category translations
cat_t = rules.setdefault("catalogCategory", {})
cat_t.update({
    "security": "Sécurité & Intrusion",
    "spatial": "Zones & Lignes",
    "crowd": "Foule & Incidents",
    "identity": "Identité & Reconnaissance",
    "road-enforcement": "Circulation & Véhicules",
    "traffic": "Circulation & Véhicules",
    "speed": "Vitesse & Infractions",
    "presence-motion": "Présence & Mouvement",
    "behavior": "Comportements",
    "composite": "Règles composites",
    "incident": "Incidents",
    "alerts": "Alertes avancées",
    "live": "Flux temps réel",
    "other": "Autres",
    "extended": "Règles étendues",
    "intrusion-loitering": "Intrusion & Attente",
    "access-control": "Contrôle d'accès",
    "line-cross": "Franchissement de ligne",
    "zone-monitoring": "Surveillance de zone",
    "theft": "Vol & Sécurité",
    "industrial": "Sécurité industrielle",
    "multi-camera": "Multi-caméras",
    "time-based": "Règles horaires",
})

# rules.catalogTab missing keys
catalog_tab = rules.setdefault("catalogTab", {})
catalog_tab.update({
    "emptyFilter": "Aucune règle ne correspond à ce filtre.",
    "search": "Rechercher une règle…",
})

# rules.catalogCard missing keys
catalog_card = rules.setdefault("catalogCard", {})
catalog_card.update({
    "showGuide": "→ Voir comment ça marche",
    "hideGuide": "↑ Masquer le guide",
    "configured": "Configurée",
    "configure": "Configurer",
    "reactivate": "Réactiver",
    "disabling": "Désactivation de {{name}}…",
})

fr_file.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
json.loads(fr_file.read_text(encoding="utf-8"))
print("fr.json ✓")
