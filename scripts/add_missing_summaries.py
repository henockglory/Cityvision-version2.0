"""Add role_summary_fr to all templates that still lack it."""
import json, glob, os, sys

SUMMARIES = {
    # behavior.json
    "tpl-running": "Alerte dès qu'une personne court dans la zone surveillée — utile pour détecter une fuite ou une urgence.",
    "tpl-crowd-gathering": "Déclenche une alerte quand plusieurs personnes se regroupent rapidement au même endroit.",
    "tpl-crowd-density": "Alerte quand la densité de la scène dépasse le seuil — idéal pour la gestion des flux en espace public.",
    "tpl-vehicle-count": "Alerte quand le nombre de véhicules dans la zone dépasse le seuil configuré.",
    "tpl-scene-occupancy": "Surveille le taux d'occupation global de la scène et alerte en cas de dépassement.",
    "tpl-person-stopped": "Signale une personne restée immobile trop longtemps — peut indiquer un malaise ou un comportement suspect.",
    "tpl-vehicle-stopped": "Détecte un véhicule à l'arrêt prolongé — utile pour les zones de livraison ou d'urgence.",
    "tpl-wrong-way": "Alerte si une personne ou un véhicule circule dans le mauvais sens sur un axe ou dans une zone.",
    "tpl-tailgating": "Détecte quand quelqu'un franchit un accès contrôlé dans le sillage immédiat d'une autre personne.",
    "tpl-falling": "Déclenche une alerte critique si une chute de personne est détectée — priorité sécurité/secours.",
    "tpl-fighting": "Signale des mouvements caractéristiques d'une bagarre ou agression physique.",
    "tpl-queue-forming": "Alerte quand une file d'attente commence à se former au-delà du nombre de personnes configuré.",
    "tpl-bottleneck": "Détecte un goulot d'étranglement dans les flux de circulation sur la scène.",
    "tpl-flow-rate": "Alerte si le débit de piétons ou de véhicules dépasse un seuil sur une période donnée.",
    # crowd-incidents-identity.json
    "tpl-crowd-panic": "Détecte une dispersion soudaine et rapide d'un groupe — signal fort de panique ou d'incident grave.",
    "tpl-group-formation": "Signale la formation rapide d'un attroupement dense dépassant le seuil de personnes configuré.",
    "tpl-fight": "Alerte critique si des mouvements violents multi-personnes sont détectés sur la scène.",
    "tpl-accident": "Détecte un enchaînement arrêt brutal → véhicule immobilisé caractéristique d'un accident routier.",
    "tpl-vandalism": "Alerte si un attroupement suivi d'une activité rapide (dispersion) est détecté — séquence de vandalisme.",
    "tpl-face-watchlist": "Alerte critique si un visage correspondant à la liste de surveillance est reconnu par la caméra.",
    "tpl-plate-unknown": "Signale un véhicule dont la plaque d'immatriculation n'est pas enregistrée dans la base.",
    "tpl-industrial-intrusion": "Alerte si une personne pénètre dans une zone machine ou dangereuse sur site industriel.",
    # extended.json
    "tpl-crouch-detected": "Signale une posture accroupie prolongée — peut indiquer une tentative de dissimulation ou de sabotage.",
    "tpl-climb-detected": "Alerte si quelqu'un tente d'escalader une clôture, un mur ou une infrastructure.",
    "tpl-carry-object": "Détecte une personne transportant un objet potentiellement volé ou dangereux.",
    "tpl-intrusion-after-hours": "Alerte pour toute présence humaine détectée en dehors des horaires d'ouverture définis.",
    "tpl-vehicle-wrong-direction": "Signale un véhicule circulant à contresens sur une voie ou dans une zone de circulation.",
    "tpl-pedestrian-zone": "Alerte si un piéton est détecté dans une zone réservée aux véhicules.",
    "tpl-face-repeat": "Signale un visage vu un nombre anormalement élevé de fois sur une période — comportement récurrent.",
    "tpl-plate-repeat": "Alerte si une même plaque est détectée un nombre anormal de fois — surveillance de véhicule suspect.",
    # identity.json
    "tpl-watchlist-match": "Alerte quand un visage connu de la liste de surveillance est identifié par la caméra.",
    "tpl-unknown-face": "Signale la présence d'un visage non reconnu dans une zone à accès contrôlé.",
    "tpl-face-detected": "Enregistre et alerte à chaque détection de visage — utile pour les zones à faible trafic.",
    "tpl-face-count": "Alerte si le nombre de visages détectés dépasse le seuil configuré sur une période.",
    "tpl-blocked-plate": "Alerte immédiate si une plaque figurant sur la liste noire est reconnue par la caméra.",
    "tpl-unknown-plate": "Signale toute plaque non présente dans la liste blanche — contrôle d'accès véhicules.",
    "tpl-plate-whitelist": "Autorise les véhicules dont la plaque est dans la liste blanche — alerte pour toute autre plaque.",
    "tpl-plate-detected": "Enregistre et alerte à chaque détection de plaque d'immatriculation sur la scène.",
    # intrusion-loitering-line-theft.json
    "tpl-intrusion": "Alerte dès qu'une personne entre dans la zone interdite que vous avez dessinée sur la caméra.",
    "tpl-loitering": "Signale une personne restée dans la zone au-delà de la durée configurée — suspect ou besoin d'assistance.",
    "tpl-line-cross": "Alerte à chaque franchissement de la ligne virtuelle dessinée sur la caméra.",
    "tpl-theft-composite": "Règle composite : alerte si une personne entre dans une zone PUIS y traîne — séquence de vol probable.",
    "tpl-abandoned-object": "Signale l'apparition d'un objet qui reste sans propriétaire dans la zone après le délai configuré.",
    "tpl-crowd-density": "Alerte quand la densité de la scène est élevée — gestion des flux et sécurité en espace public.",
    # road-enforcement.json duplicate
    "tpl-wrong-way": "Alerte si une personne ou un véhicule circule dans le mauvais sens sur un axe ou dans une zone.",
}

ROOT = os.path.join(os.path.dirname(__file__), '..')

updated = 0
for f in sorted(glob.glob(os.path.join(ROOT, 'shared/rule-catalog/*.json'))):
    with open(f, encoding='utf-8') as fh:
        data = json.load(fh)
    is_list = isinstance(data, list)
    templates = data if is_list else data.get('templates', [])
    changed = False
    for t in templates:
        tid = t.get('id', '')
        if not t.get('role_summary_fr') and tid in SUMMARIES:
            t['role_summary_fr'] = SUMMARIES[tid]
            changed = True
            updated += 1
    if changed:
        with open(f, 'w', encoding='utf-8') as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
        print(f'Updated {os.path.basename(f)}')

print(f'\nTotal role_summary_fr added: {updated}')
