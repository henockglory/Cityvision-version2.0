# Shared — CitéVision v2

Ressources partagées entre les différents services : schémas JSON, templates de règles.

## Contenu

```
shared/
├── schemas/
│   ├── detection.json     ← Schéma JSON des événements de détection AI → MQTT
│   ├── event.json         ← Schéma JSON des événements backend
│   └── rule.json          ← Schéma JSON du DSL de règles
└── rule-templates/
    └── default-templates.json  ← Templates de règles prédéfinis (chargés au seed)
```

## Schéma detection.json

Événements publiés par l'AI engine sur le topic MQTT `citevision/events/{org_id}/{camera_id}`.

Champs principaux : `camera_id`, `org_id`, `timestamp`, `event_type`, `objects[]`, `track_id`, `confidence`, `evidence_url`.

## Schéma rule.json

Le DSL de règles utilise une structure JSON avec :
- `trigger` — condition déclenchante (type d'événement, zone, seuils)
- `conditions[]` — conditions additionnelles (heure, zone, classe d'objet)
- `actions[]` — actions à déclencher (alerte, notification, enregistrement)

## Templates de règles

Les templates par défaut sont chargés lors du premier démarrage (seed) et couvrent :
- Intrusion de zone
- Traversée de ligne
- Stationnement prolongé (loitering)
- Attroupement (crowd)
- Véhicule non autorisé
- Reconnaissance faciale (watchlist)
- ANPR (reconnaissance plaques)
