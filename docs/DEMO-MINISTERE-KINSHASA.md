# Démo Ministère — Urbanisme & Transport · Kinshasa

Scénario de présentation **15 minutes** pour CitéVision 2.0.

## Préparation (5 min avant)

```bash
cd ~/citevision-v2
bash scripts/sync-to-wsl.sh
bash scripts/setup-demo-kinshasa.sh
bash scripts/validate-commercial-gate.sh
```

Checklist :

- [ ] http://localhost:5174/demo — vidéo LIVE visible
- [ ] Statut « GPU CUDA ✓ » (ou CPU en secours dev)
- [ ] Identifiants testés

## Identifiants

| Champ | Valeur |
|-------|--------|
| URL | http://localhost:5174/demo |
| Email | glory.henock@hologram.cd |
| Mot de passe | Hologram2026! |

## Scénario (15 min)

### 1. Accueil (2 min)

- Connexion → redirection automatique vers **Démonstration CitéVision**
- Montrer la vidéo benedicte en WebRTC (fluide, badge LIVE)
- Statuts services : Serveur, Vidéo, Analyse IA, GPU

### 2. Zonage (4 min)

- Menu **Éditeur de zones**
- 3 clics sur la vidéo → **Fermer polygone** → **Enregistrer**
- Montrer la zone listée à droite

### 3. Règles (4 min)

- Retour **Démo** → section **Catalogue de règles**
- Cliquer **Activer** sur « Intrusion zone interdite » ou « Présence personne »
- Badge **Active** confirmé

### 4. Résultats (4 min)

- Panneaux **Détections live** et **Alertes live**
- Attendre 30–60 s si nécessaire
- **Acquitter** une alerte en un clic
- Option : Vue Live, Mur vidéo, Centre d'alertes

### 5. Clôture (1 min)

- Rappeler : stack souveraine, GPU NVIDIA, extensible 100+ détections
- Vidéo directe secours : http://localhost:1984/stream.html?src=benedicte

## Dépannage rapide

| Problème | Solution |
|----------|----------|
| Écran noir | `bash scripts/validate-video-playback.sh` |
| Pas de détections | `curl localhost:8001/health` → yolo_loaded |
| Gate échoue GPU | docs/GPU-WSL2.md |
| Relancer tout | `bash scripts/stop-linux.sh && bash scripts/setup-demo-kinshasa.sh` |
