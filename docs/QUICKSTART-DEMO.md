# CitéVision 2.0 — Démo Kinshasa (démarrage rapide)

Guide pour tester **100 % en local** la vidéo modèle `benedicte.mp4`, les zones, règles, détections et alertes — contexte **Ministère de l'Urbanisme et des Transports, Kinshasa**.

## Prérequis

- Windows 11 + **WSL2 Ubuntu 24.04**
- Docker Desktop (WSL integration)
- Fichier vidéo : `C:\Users\gheno\Videos\benedicte.mp4`
- Projet actif : `citevision-v2` (pas l'ancien dossier `citevision`)

## Installation en une commande

```bash
cd ~/citevision-v2
bash scripts/sync-to-wsl.sh          # si vous éditez depuis Windows
bash scripts/setup-demo-kinshasa.sh   # YOLO + infra + caméra + règles
```

La première exécution télécharge PyTorch/ultralytics et exporte `yolov8n.onnx` (~10–20 min selon le réseau).

Modèle seul :

```bash
bash scripts/download-yolo-model.sh
```

## Connexion

| Champ | Valeur |
|-------|--------|
| URL | http://localhost:5174/login |
| Email | `glory.henock@hologram.cd` |
| Mot de passe | `Hologram2026!` |

Reset mot de passe : `bash scripts/reset-admin-password.sh`

**Important :** Ctrl+Shift+R après redémarrage du frontend.

## Parcours recommandé (15 min)

1. **Démo Kinshasa** (`/demo`) — checklist et état des services
2. **Vue Live** — flux WebRTC `benedicte` (vidéo en boucle)
3. **Éditeur zones** — dessiner un polygone sur la vidéo → Enregistrer
4. **Règles** — activer des modèles du catalogue (intrusion, loitering, foule…)
5. **Tableau de bord** — panneau « Flux détections » (événements MQTT → API)
6. **Alertes** — après 1–2 min de lecture vidéo avec YOLO actif

## URLs utiles

| Service | URL |
|---------|-----|
| Interface | http://localhost:5174 |
| Vidéo directe go2rtc | http://localhost:1984/stream.html?src=benedicte |
| Backend health | http://localhost:8081/health |
| Moteur IA | http://localhost:8001/health |
| MinIO console | http://localhost:9001 |

## Caméra réelle (optionnel)

- IP : `192.168.1.108`
- Identifiants : `admin` / `hids+1234`
- Ajout via **Caméras → Ajouter** (assistant 3 étapes)

## Vérifier les détections

```bash
bash scripts/validate-detections.sh    # écoute MQTT 5 min
curl -s http://localhost:8001/cameras | jq .
curl -s -H "Authorization: Bearer <token>" http://localhost:8081/api/v1/events | jq '. | length'
```

Si `yolo_loaded: false` → relancer `bash scripts/download-yolo-model.sh` puis `bash scripts/start-linux.sh`.

## Dépannage

| Symptôme | Action |
|----------|--------|
| Page blanche / ancienne UI | Ctrl+Shift+R ; vérifier port 5174 dans `logs/frontend.pid` |
| Pas de vidéo | `curl http://localhost:1984/api/streams` doit lister `benedicte` |
| 0 événement | Modèle YOLO absent ; AI engine down ; MQTT port 1884 |
| Login échoue | Utiliser `glory.henock@hologram.cd`, pas `admin@citevision.local` |
| Script CRLF | `perl -pi -e 's/\r$//' scripts/*.sh` |

## Reprise agent IA

Voir `AGENT_CHECKPOINT.md` à la racine du projet.
