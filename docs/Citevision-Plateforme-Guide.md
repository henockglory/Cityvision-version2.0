# CitéVision — Plateforme de surveillance intelligente
## Guide technique & manuel des grandes lignes

**Version document :** juillet 2026  
**Éditeur :** HOLOGRAM.CD  
**Public :** décideurs, intégrateurs, exploitants

---

> *« De l'installation au premier événement utile : une seule logique, quelle que soit votre plateforme. »*

---

## Table des matières

1. [Vision en une phrase](#1-vision-en-une-phrase)
2. [Pourquoi CitéVision change la donne](#2-pourquoi-citévision-change-la-donne)
3. [Architecture & technologies](#3-architecture--technologies)
4. [Installation : une logique, toutes les plateformes](#4-installation--une-logique-toutes-les-plateformes)
5. [Du démarrage à l'exploitation](#5-du-démarrage-à-lexploitation)
6. [Manuel des grandes lignes](#6-manuel-des-grandes-lignes)
7. [Palette de capacités](#7-palette-de-capacités)
8. [Fonctions game-changer](#8-fonctions-game-changer)
9. [Ce que vous pouvez lui confier sans vous soucier](#9-ce-que-vous-pouvez-lui-confier-sans-vous-soucier)
10. [Annexes pratiques](#10-annexes-pratiques)

---

## 1. Vision en une phrase

**CitéVision** est une plateforme de vidéosurveillance intelligente qui relie **caméras**, **intelligence artificielle embarquée**, **règles métier** et **preuves exploitables** dans un flux unique — installable sur **Windows** ou **Linux**, opérable par des non-spécialistes, et assez puissante pour les scénarios les plus exigeants (vitesse, identité, foule, routier, sécurité).

---

## 2. Pourquoi CitéVision change la donne

La plupart des solutions du marché vous obligent à choisir :

- soit de la **vidéo passive** (enregistrer et regarder après coup),
- soit de l'**IA en silo** (détecter sans vraiment décider),
- soit des **règles rigides** codées par un intégrateur à chaque changement.

CitéVision unifie tout cela autour d'une chaîne de vérité simple et redoutablement efficace :

```
Zone dessinée → IA qui comprend la scène → Règle qui décide → Preuve qui convainc
```

Vous ne « bricolez » pas des briques disparates : vous **décrivez l'intention**, et la plateforme **assume l'exécution** — détection, suivi, corrélation, alerte, archivage, notification.

Le résultat : une efficacité déconcertante pour des besoins allant du comptage de véhicules à l'infraction routière, de l'intrusion nocturne à la reconnaissance de visage ou de plaque, **sans réécrire le système à chaque nouveau cas d'usage**.

---

## 3. Architecture & technologies

### 3.1 Une stack moderne, choisie pour la performance réelle

| Couche | Technologie | Rôle |
|--------|-------------|------|
| **Interface** | React, TypeScript, Vite | Expérience fluide, temps réel, multilingue (FR/EN) |
| **API & orchestration** | Go (Golang) | Backend rapide, fiable, faible empreinte mémoire |
| **Intelligence artificielle** | Python, FastAPI, ONNX Runtime | Inférence GPU (CUDA) : YOLO, InsightFace, PaddleOCR |
| **Moteur de règles** | Go, MQTT | Évaluation déclarative ET/OU/NON, fenêtres temporelles |
| **Messagerie temps réel** | MQTT (Mosquitto) | Bus d'événements entre IA, règles et services |
| **Données** | PostgreSQL, Redis | Persistance, cache, anti-doublons |
| **Preuves & médias** | MinIO (S3), FFmpeg, go2rtc | Clips, images, flux WebRTC, stockage objet |
| **Conteneurs** | Docker Compose | Infra reproductible, portable, isolée |
| **Sécurité** | JWT, RBAC, audit signé | Accès par rôles, traçabilité des actions |

### 3.2 L'IA n'est pas un gadget : c'est un moteur de production

CitéVision embarque un **registre IA extensible** vérifié avant chaque démarrage :

- **YOLO (ONNX)** — détection véhicules, personnes, objets ; profil matériel adaptatif (YOLO nano à small selon le GPU).
- **ByteTrack** — suivi multi-objets stable caméra par caméra.
- **InsightFace** — reconnaissance faciale (modèle buffalo_l).
- **PaddleOCR** — lecture automatique de plaques (ANPR).
- **Modèles secondaires ONNX** — comportements routiers (téléphone au volant, ceinture, feux, etc.).

Chaque composant expose son état via `/health` : **pas de démarrage « en cachette »** avec une IA à moitié chargée. Si le GPU est disponible, il est **prioritaire** ; le CPU n'est qu'un filet de sécurité.

### 3.3 Le moteur de règles : votre chef d'orchestre silencieux

Là où d'autres solutions encombrent l'utilisateur de scripts, CitéVision propose un **catalogue de règles honnête** — chaque option affichée correspond à un événement réellement émis, avec un badge de maturité (`réel`, `partiel`, `bêta`).

Les règles combinent :

- conditions spatiales (zone, ligne, vitesse),
- conditions temporelles (plages horaires, jours),
- conditions d'objet (type, durée, seuil),
- logique booléenne **ET / OU / NON**,
- actions : alerte, e-mail SMTP, webhook, preuve automatique.

### 3.4 Vidéo : analyse ET exploitation

- **go2rtc** — flux WebRTC basse latence, compatibilité large (RTSP, fichiers, démo).
- **FFmpeg** — encodage H.264, clips de preuve, transcodage.
- **Mur vidéo & vue directe** — supervision multi-caméras sans logiciel tiers.

---

## 4. Installation : une logique, toutes les plateformes

CitéVision a été conçue pour que **la même intelligence d'installation** fonctionne partout. Pas de double manuel, pas de « version Windows light ».

### 4.1 Trois portes d'entrée, un seul cœur

| Contexte | Point d'entrée | Comportement |
|----------|----------------|--------------|
| **Windows (poste de travail)** | `setup.bat` → installateur web (port 7315) | Interface guidée, choix manuel/auto, délégation WSL pour l'IA |
| **WSL / Linux (développement & prod)** | `scripts/setup-wsl.sh` | Bootstrap complet : paquets, Docker, Go, Node, Python, modèles IA |
| **Serveur Linux headless (SSH)** | `scripts/install-headless.sh` | Installation sans navigateur, service systemd, vérifications séquentielles |

### 4.2 Ce que fait l'installateur pour vous (sans que vous le voyiez)

1. **Détecte le profil matériel** (GPU, VRAM, CPU) et génère `generated.env` — le bon modèle YOLO, le bon débit, le bon backend CUDA.
2. **Installe et valide la stack IA** — YOLO, InsightFace, PaddleOCR, modèles secondaires ; boucle de correction automatique si un maillon manque.
3. **Persiste votre choix de démarrage** (manuel ou automatique au boot) — fichier, marqueur système, mécanismes Windows (tâches planifiées) ou Linux (systemd), **aligné avec Paramètres → Système**.
4. **Lance la stack** et vérifie **chaque service** : backend, IA, règles, frontend, ingest — avec redémarrage automatique si l'ingest IA est lent au cold start.
5. **Répare les flux démo** — synchronisation des MP4 et enregistrement go2rtc pour lecture immédiate après réinstallation.

### 4.3 Windows & Linux : la même philosophie

- **Windows** : WSL2 comme moteur IA natif (CUDA via NVIDIA), Docker Engine dans WSL, lancement via `start-citevision.bat` ou tâches planifiées.
- **Linux** : Docker Compose, systemd `citevision.service`, scripts `start-linux.sh` / `stop-linux.sh`.
- **Dans les deux cas** : watchdog backend et ingest, `doctor-linux.sh` pour diagnostic, désinstallation guidée depuis l'interface.

> **Pragmatisme sans égal :** vous choisissez *manuel* ou *automatique* une seule fois à l'installation ; la plateforme s'occupe du reste, même si une stack tourne déjà sur la machine.

---

## 5. Du démarrage à l'exploitation

### 5.1 Séquence de démarrage (automatique)

```
Docker (Postgres, Redis, MQTT, MinIO, go2rtc, MailHog)
    ↓
Vérification / correction AI stack (GPU, modèles, registre)
    ↓
Backend Go → migrations, API, WebSocket alertes
    ↓
Réparation flux vidéo démo (fichiers + go2rtc)
    ↓
Rules Engine → abonnement MQTT, évaluation des règles actives
    ↓
AI Engine → YOLO + tracking + zones + événements MQTT
    ↓
Frontend Vite → interface opérateur
    ↓
Watchdogs → relance si crash ou ingest figé
```

### 5.2 Première connexion

1. Ouvrir **http://localhost:5174/setup** (ou `/login` si déjà configuré).
2. Créer l'organisation et le compte administrateur.
3. Suivre le **tutoriel intégré** en 3 étapes : caméras → zones → règles.

### 5.3 Exploitation au quotidien

- **Tableau de bord** — vue synthétique : caméras en ligne, alertes, événements 24 h, règles actives.
- **Alertes temps réel** — WebSocket : pas besoin d'actualiser la page.
- **Santé système** — état des services, GPU, providers ONNX réels exposés.
- **Paramètres** — mode de démarrage, routage e-mail, politique de preuves par défaut, désinstallation.

---

## 6. Manuel des grandes lignes

### 6.1 Connecter vos caméras (simple)

1. Aller dans **Caméras → Ajouter**.
2. **Scanner le réseau** (CIDR) ou saisir l'URL RTSP directement.
3. L'assistant reconnaît **Hikvision, Dahua** et construit les URLs courantes ; test TCP automatique.
4. **Aperçu live** avant validation — vous voyez ce que l'IA verra.

*Vous n'êtes pas intégrateur vidéo : l'assistant fait le travail ingrat.*

### 6.2 Définir où regarder (zones & lignes)

1. **Éditeur de zones** — dessinez polygones et lignes sur l'image réelle de la caméra.
2. Calibrez les **comportements** : entrée/sortie, franchissement, vitesse, comptage.
3. Les géométries vivent en **base de données** — pas de coordonnées codées en dur, modifiables à tout moment.

*La scène devient un langage que l'IA comprend.*

### 6.3 Créer des règles (du simple au sophistiqué)

1. **Catalogue de règles** — parcourez les familles : présence, intrusion, trafic, vitesse, identité, foule, sécurité, routier…
2. **Activer une règle** — choisissez caméra, zone, seuils, horaires, sévérité.
3. **Politique de preuves** — clip H.264 (6 s par défaut), images clés, plaque si contexte routier.
4. **Routage** — e-mail SMTP, webhook (n8n, ticketing, SI tiers).

*Une règle validée une fois prouve le mécanisme pour toutes les autres : même pipeline, même exigence de preuve.*

### 6.4 Réagir aux alertes

1. **Alertes** — file priorisée, acquittement, lien vers preuves.
2. **Événements** — historique brut IA / règles pour audit et analyse.
3. **Centre démo** — scénarios préconfigurés (Kinshasa) pour formation et démonstration client.

### 6.5 Administrer sereinement

- **Utilisateurs & rôles** — RBAC fin (organisation, permissions).
- **Audit** — journal signé des actions sensibles.
- **Paramètres système** — démarrage manuel/auto, arrêt/démarrage stack, désinstallation propre.

---

## 7. Palette de capacités

CitéVision n'est pas « une fonction » : c'est un **éventail** que vous activez à la carte.

### 7.1 Surveillance classique, élevée au rang d'intelligent

| Besoin | Ce que CitéVision fait |
|--------|------------------------|
| Intrusion zone | Détection + entrée zone + alerte + clip |
| Franchissement de ligne | Comptage sens A/B, feux, voies |
| Flânerie / présence prolongée | Durée dans zone, seuil configurable |
| Comptage foule / files | Agrégation par zone, tendances |

### 7.2 Routier & traffic — l'efficacité déconcertante

| Besoin | Ce que CitéVision fait |
|--------|------------------------|
| Excès de vitesse | Calibration zone, km/h, preuve + plaque |
| Feu rouge / comportement | Modèles dédiés, corrélation spatiale |
| Téléphone au volant, ceinture | ONNX secondaires, badge honnête catalogue |
| Lecture de plaques (ANPR) | PaddleOCR, listes autorisées / interdites |

### 7.3 Identité & sécurité renforcée

| Besoin | Ce que CitéVision fait |
|--------|------------------------|
| Reconnaissance faciale | InsightFace, corrélation événement |
| Personnes recherchées | Règles identité + alerte immédiate |
| Multi-sites | Organisations, caméras, cartographie SIG |

### 7.4 Intégration & automatisation

| Besoin | Ce que CitéVision fait |
|--------|------------------------|
| E-mail d'alerte premium | SMTP configurable, MailHog en démo |
| Webhook / n8n | Payload structuré à la création d'alerte |
| Preuves juridiques | MinIO, métadonnées, visionneuse intégrée |
| Mur vidéo / ops center | Vue directe multi-flux WebRTC |

### 7.5 Du plus simple au plus complexe — un seul fil conducteur

- **Simple** : « Prévenez-moi si quelqu'un entre dans le parking après 22 h. »
- **Intermédiaire** : « Comptez les véhicules qui franchissent la ligne A→B entre 7 h et 9 h. »
- **Avancé** : « Alerte vitesse > 50 km/h dans la zone scolaire, avec clip, deux images et lecture de plaque. »
- **Expert** : « Combine intrusion zone A **ET** visage inconnu **ET** horaire nuit, webhook vers le SOC. »

Tout cela sans changer d'outil — seulement des **règles** et des **zones**.

---

## 8. Fonctions game-changer

### Chaîne zone → IA → règle → preuve

La promesse n'est pas théorique : c'est l'architecture runtime. Chaque alerte « sérieuse » peut exiger des preuves **avant** d'être présentée comme définitive — clip, images, plaque si le contexte l'exige.

### IA registre + gate de démarrage

Pas de démarrage aveugle : le registre IA impose que YOLO, InsightFace, PaddleOCR et les modèles secondaires soient **réellement chargés** (GPU inclus). L'installateur et le lancement corrigent automatiquement avant de vous dire « prêt ».

### Zones dessinées, jamais codées en dur

Vous modifiez la géométrie dans l'éditeur ; l'IA et les règles suivent. Idéal pour les sites qui évoluent, les chantiers, les démonstrations.

### Catalogue de règles véridique

Chaque entrée UI = un événement réel. Badges de maturité visibles. Fini les cases à cocher « marketing » qui ne déclenchent rien.

### Auto-réparation à l'installation et au lancement

- IA incomplète → boucle de correction automatique.
- Ingest figé → redémarrage AI + watchdog.
- Flux démo manquants → resynchronisation fichiers et go2rtc.
- Mode démarrage → vérification fichier, marqueur, OS et Paramètres.

### Une install, deux mondes (Windows / Linux)

Même scripts cœur, même ports, même API, même interface. Windows s'appuie sur WSL pour l'IA CUDA ; Linux natif pour le datacenter.

### Démo & formation intégrées

Centre démo, vidéos téléversables, flux WebRTC reconstitués après réinstall — **formation client sans caméras sur site**.

### Exploitation responsable

RBAC, audit, désinstallation guidée, mode manuel pour environnements sensibles, watchdog pour la continuité.

### Temps réel natif

MQTT entre composants, WebSocket vers le navigateur : l'opérateur voit l'alerte quand elle naît.

### Tutoriels contextuels & aide intégrée

Prise en main en 3 étapes, tours guidés par écran — **adoption rapide** sans formation externe coûteuse.

---

## 9. Ce que vous pouvez lui confier sans vous soucier

| Vous confiez… | CitéVision assume… |
|---------------|-------------------|
| L'installation sur un poste Windows inconnu | Profil matériel, dépendances, IA, Docker, choix manuel/auto vérifié |
| Le redémarrage après une coupure | Watchdog backend & ingest, mode auto si configuré |
| La cohérence après une réinstall | Resync flux démo, chemins projet, registre IA |
| La décision métier | Moteur de règles ET/OU/NON, fenêtres, anti-doublons |
| La preuve devant un tiers | Clip, images, métadonnées, stockage MinIO |
| La notification | SMTP, webhooks, routage par règle |
| La montée en charge caméras | Budget ressources adaptatif, profil high/medium/low |
| La traçabilité | Audit signé, historique événements |

**En termes simples :** vous décrivez *ce qui doit inquiéter* et *où* ; CitéVision s'occupe de *voir*, *comprendre*, *décider*, *enregistrer* et *prévenir*.

---

## 10. Annexes pratiques

### 10.1 Ports par défaut

| Service | Port |
|---------|------|
| Interface web | 5174 |
| API backend | 8081 |
| Moteur IA | 8001 |
| Moteur de règles | 8010 |
| go2rtc (WebRTC) | 1984 |
| Installateur (setup) | 7315 |
| MinIO (preuves) | 9003 |
| MailHog (démo mail) | 8025 |

### 10.2 Commandes utiles

```bash
# Démarrer (WSL / Linux)
bash scripts/start-linux.sh

# Arrêter
bash scripts/stop-linux.sh

# Diagnostic
bash scripts/doctor-linux.sh
```

```powershell
# Windows — démarrage manuel
start-citevision.bat

# Installation guidée
setup.bat
```

### 10.3 Parcours recommandé (première heure)

1. Installer via `setup.bat` ou `setup-wsl.sh`.
2. Choisir le mode de démarrage (manuel recommandé pour premier essai).
3. Créer l'organisation dans `/setup`.
4. Ajouter une caméra ou utiliser le **Centre démo**.
5. Dessiner une zone dans l'**Éditeur de zones**.
6. Activer une règle du **catalogue**.
7. Observer une alerte avec **preuves** dans l'interface.

### 10.4 Support & évolution

CitéVision est conçue pour évoluer par **catalogue** (nouvelles règles), **registre IA** (nouveaux modèles ONNX) et **API** — sans remettre en cause l'architecture zone → IA → règle → preuve.

---

## Mot de fin

CitéVision n'est pas seulement un logiciel de caméras. C'est une **plateforme de responsabilité visuelle** : elle transforme des flux vidéo bruts en **décisions actionnables**, des décisions en **alertes ciblées**, des alertes en **preuves exploitables** — avec une installation qui respecte votre temps, votre matériel et votre système d'exploitation.

Que vous déployiez un pilote ministériel, un site industriel ou un parc de caméras urbaines, la logique reste la même : **décrivez l'intention, la plateforme exécute le reste.**

---

*Document produit pour la plateforme CitéVision v2 — HOLOGRAM.CD © 2026*
