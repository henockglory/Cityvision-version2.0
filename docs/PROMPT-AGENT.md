# PROMPT AGENT — Citévision 2.0

> **Document maître** pour agents IA (Cursor et autres) construisant Citévision 2.0.
> Version : 2.0.0 | Dernière mise à jour : 2026-06-12
> Dépôt cible : `henockglory/Cityvision-version2.0` (privé)
> Environnement principal : WSL Ubuntu 24.04 — `/home/gheno/citevision`

---

## Table des matières

0. [Mode de fonctionnement agent](#section-0--mode-de-fonctionnement-agent)
1. [Vision produit](#section-1--vision-produit)
2. [Stack technique](#section-2--stack-technique)
3. [Pipeline 15 couches](#section-3--pipeline-15-couches)
4. [15 familles de détections](#section-4--15-familles-de-détections)
5. [Compléments enterprise](#section-5--compléments-enterprise)
6. [RBAC — 7 rôles](#section-6--rbac--7-rôles)
7. [UX et design system](#section-7--ux-et-design-system)
8. [14 livrables détaillés L1–L14](#section-8--14-livrables-détaillés-l1l14)
9. [Matrice de tests](#section-9--matrice-de-tests)
10. [Documentation et continuité](#section-10--documentation-et-continuité)
11. [Structure du dépôt](#section-11--structure-du-dépôt)
12. [Décisions figées](#section-12--décisions-figées)

---

## Section 0 — Mode de fonctionnement agent

### 0.1 Lecture obligatoire en début de session

Avant toute modification de code, l'agent **DOIT** relire intégralement :

| Fichier | Rôle |
|---------|------|
| `docs/PROMPT-AGENT.md` | Ce document — source de vérité fonctionnelle et technique |
| `docs/STATE.md` | État courant du projet, livrable en cours, blocages |
| `docs/DECISIONS.md` | Décisions architecturales figées (ADR) |

Si un conflit existe entre ce prompt et `DECISIONS.md`, **`DECISIONS.md` prime** pour les ADR enregistrés ; ce prompt prime pour le périmètre produit global.

### 0.2 Livrables séquentiels L1–L14

L'implémentation est découpée en **14 livrables strictement séquentiels**. Règles non négociables :

1. **Ne jamais sauter un livrable** — L(n+1) interdit tant que L(n) n'est pas validé.
2. **Ne jamais avancer** si `scripts/validate-lX.sh` échoue pour le livrable X concerné.
3. **Un livrable = un périmètre de fichiers** — ne pas modifier des composants d'un livrable futur.
4. **Mettre à jour `docs/STATE.md`** à la fin de chaque livrable validé.
5. **Commit Git uniquement au L14** — aucun commit intermédiaire sauf demande explicite du propriétaire.

Commande de validation globale (après L13) :

```bash
bash scripts/validate-final.sh
make validate
```

### 0.3 Interdictions absolues

| Interdiction | Détail |
|--------------|--------|
| Hardcoder IP / secrets | Toute adresse caméra, mot de passe, clé API, PAT GitHub doit venir de `.env` |
| SaaS cloud | Aucun appel OpenAI, Google Vision, AWS Rekognition, Azure CV, etc. |
| Placeholders UI sans ticket | Pas de composant « Lorem ipsum », pas de page vide sans entrée dans `STATE.md` |
| Réimplémentation aveugle | Recherche GitHub obligatoire avant tout code maison pour les librairies listées |
| Modifier les anciens projets | Citévision 2.0 est isolé ; ne pas toucher aux dépôts antérieurs |
| Émojis dans l'UI | Interdits — utiliser des icônes outline (Lucide) |
| Push Git avant L14 | Le push vers `henockglory/Cityvision-version2.0` se fait au L14 uniquement |

### 0.4 Recherche GitHub obligatoire

Avant de réimplémenter une fonctionnalité déjà disponible en open source, l'agent **DOIT** consulter et évaluer (intégration, licence, compatibilité offline) :

| Projet | Usage Citévision |
|--------|------------------|
| [bluenviron/mediamtx](https://github.com/bluenviron/mediamtx) | Relais RTSP/WebRTC, rebroadcast caméras |
| [AlexxIT/go2rtc](https://github.com/AlexxIT/go2rtc) | Streaming multi-protocole, intégration navigateur |
| [FoundationVision/ByteTrack](https://github.com/ifzhang/ByteTrack) | Tracking multi-objets |
| [ultralytics/ultralytics](https://github.com/ultralytics/ultralytics) | YOLOv8 export ONNX, inférence |
| [deepinsight/insightface](https://github.com/deepinsight/insightface) | Reconnaissance faciale locale |
| [PaddlePaddle/PaddleOCR](https://github.com/PaddlePaddle/PaddleOCR) | OCR plaques et texte scène |
| [shadcn/ui](https://github.com/shadcn-ui/ui) | Composants React accessibles (base du design system) |

Documenter dans `docs/DECISIONS.md` toute décision d'intégrer ou de réimplémenter.

### 0.5 Format de travail agent

Pour chaque livrable :

```
--- LIVRABLE X/14 ---
Scope : [description]
Fichiers modifiés : [liste]
Tests exécutés : bash scripts/validate-lX.sh
Résultat : PASS / FAIL
Mise à jour STATE.md : oui/non
--- FIN LIVRABLE X ---
```

En cas de dépassement de contexte : stopper proprement, indiquer le livrable en cours et reprendre au prochain message.

### 0.6 Gestion des secrets et caméra test

- Variables sensibles : **uniquement** dans `.env` (commité en dépôt privé selon ADR — voir Section 12).
- Caméra de test : **uniquement** via variables d'environnement :

```env
TEST_CAMERA_IP=192.168.1.108
TEST_CAMERA_USER=admin
TEST_CAMERA_PASSWORD=hids+1234
```

- **Jamais** inscrire ces valeurs dans le code source, les tests commités ou la documentation publique.

---

## Section 1 — Vision produit

### 1.1 Identité

**Citévision 2.0** est une plateforme de vidéo-analytique intelligente edge-first, conçue pour rivaliser avec Hikvision, Genetec et les solutions Smart City, tout en restant **100 % offline**.

| Attribut | Valeur |
|----------|--------|
| Logo | Œil stylisé (composant `EyeLogo`) — symbole de vigilance |
| Esthétique | Premium futuriste, android/humanoid cyberpunk — sombre par défaut |
| Positionnement | Enterprise + gouvernement + PME — multi-tenant natif |
| Matériel cible MVP | NVIDIA RTX 4050 6 Go VRAM — **12 caméras max** simultanées |
| Connectivité | Aucune dépendance Internet en production |

### 1.2 Promesse utilisateur

1. **Simplicité d'intégration caméra** — saisie IP, scan réseau ONVIF ou sélection dans liste découverte ; assistant pas-à-pas.
2. **Détection configurable sans code** — moteur de règles déclaratif condition-action.
3. **Parité fonctionnelle** — health caméra, mur vidéo, carte, replay forensique, recherche, masques vie privée, PTZ, webhooks, métriques Prometheus.
4. **Résilience** — dégradation gracieuse sous charge GPU/CPU, reprise automatique flux RTSP.

### 1.3 Internationalisation et accessibilité

| Exigence | Implémentation |
|----------|----------------|
| Langues | Français (défaut) + Anglais — i18n via `react-i18next`, fichiers `fr.json` / `en.json` |
| Thèmes | Light et Dark — bascule persistée (`ThemeToggle`) |
| Icônes | Lucide React — style **outline** uniquement |
| Émojis | **Interdits** dans toute l'interface |
| Onboarding | Tour guidé skippable (`OnboardingTour`) |
| Tooltips | Aide contextuelle sur actions non évidentes |

### 1.4 Cas d'usage cibles

- Sécurité périmétrique et intrusion
- Retail — vol, attroupement, files d'attente
- Trafic urbain — congestion, infractions, accidents
- Sites industriels — zones machines, EPI, logistique
- Smart city — foule, incidents, infrastructure
- Domotique avancée — résidence multi-caméras

### 1.5 Critères de succès produit

Le produit est considéré **complet** lorsque :

- Les 14 livrables passent leurs scripts de validation
- Les 15 familles de détections sont configurables via règles (au minimum via événements atomiques + composites)
- L'UI couvre toutes les vues enterprise (Section 5)
- RBAC 7 rôles opérationnel avec audit immuable
- Charge 12 caméras stable sur profil RTX 4050 6 Go
- Zéro appel réseau sortant vers cloud en mode production

---

## Section 2 — Stack technique

### 2.1 Vue d'ensemble

```
┌─────────────┐   RTSP    ┌────────────────┐   frames   ┌─────────────────┐
│  Caméras IP │──────────▶│ Video Engine   │───────────▶│   AI Engine     │
│  ONVIF      │           │ C++ / FFmpeg   │  HTTP/shm  │ Python/FastAPI  │
└─────────────┘           └────────────────┘            │ ONNX Runtime    │
                                                        └────────┬────────┘
                                                                 │ MQTT
┌─────────────┐   REST/WS   ┌────────────────┐                  ▼
│  Frontend   │◀───────────▶│ Backend Go     │         ┌─────────────────┐
│ React/Vite  │             │ chi / pgx      │◀────────│ Mosquitto MQTT  │
│ Tailwind TS │             └───────┬────────┘         └─────────────────┘
└─────────────┘                     │
                    ┌───────────────┼───────────────┐
                    ▼               ▼               ▼
              PostgreSQL         Redis            MinIO
              (source vérité)   (cache/sessions)  (evidence S3)
```

### 2.2 Frontend

| Technologie | Version / détail |
|-------------|------------------|
| React | 18+ |
| Vite | Build et HMR |
| TypeScript | Strict |
| Tailwind CSS | Design tokens `cv-*` |
| TanStack Query | État serveur |
| React Router | Navigation |
| react-i18next | FR + EN |
| Lucide React | Icônes outline |
| shadcn/ui | Base composants (Button, Dialog, Table, etc.) |

### 2.3 Backend

| Technologie | Usage |
|-------------|-------|
| Go 1.22+ | API REST, WebSocket |
| chi | Router HTTP |
| pgx v5 | PostgreSQL driver |
| zerolog | Logs structurés JSON |
| paho.mqtt.golang | Client MQTT |
| JWT + bcrypt | Auth |
| TOTP | 2FA |

### 2.4 Video Engine

| Technologie | Usage |
|-------------|-------|
| C++17 | Performance |
| CMake | Build |
| FFmpeg | Décodage RTSP, encodage H.264 |
| Pipeline dual | Analyse basse résolution + enregistrement 720p |

### 2.5 AI Engine

| Technologie | Usage |
|-------------|-------|
| Python 3.12 | Runtime |
| FastAPI | API HTTP |
| ONNX Runtime | Inférence YOLO (CPU/GPU EP) |
| ByteTrack | Tracking |
| InsightFace | Reconnaissance faciale (stub → prod) |
| PaddleOCR | ANPR / OCR (stub → prod) |

### 2.6 Infrastructure

| Service | Image / version | Rôle |
|---------|-----------------|------|
| PostgreSQL | 17 | Données structurées, règles, audit |
| Redis | 7 | Cache, sessions, états transitoires |
| Mosquitto | Eclipse | Bus événementiel MQTT |
| MinIO | Latest | Stockage S3-compatible (evidence, clips) |
| Docker Compose | v2 | Orchestration dev/prod |

### 2.7 Protocoles et bus

- **MQTT** : topics `cv/detections/{camera_id}`, `cv/events/{camera_id}`, `cv/alerts/{tenant_id}`
- **REST** : API Go `:8080`
- **WebSocket** : alertes temps réel, statut caméras
- **RTSP/ONVIF** : ingest vidéo

---

## Section 3 — Pipeline 15 couches

Le pipeline transforme un flux vidéo brut en décisions actionnables. Chaque couche est **découplée** et communique via structures normalisées (`shared/schemas/`).

### 3.1 Schéma global

```
P1 Perception → P2 Détection → P3 Tracking → P4 Scène → P5 Événements
    → P6 Comportement → P7 État → P8 Corrélation → P9 Règles → P10 Actions
    → P11 Face → P12 ANPR → P13 Trafic/Densité → P14 Sécurité → P15 Composites
```

### 3.2 Détail des 15 couches

#### P1 — Perception (acquisition vidéo)

- Ingest RTSP/ONVIF multi-flux
- Décodage FFmpeg/GStreamer (accélération GPU si disponible)
- Normalisation frames, horodatage, gestion pertes/latence
- Reconnexion automatique, health par caméra
- **Service** : `video-engine/`

#### P2 — Détection d'objets

- YOLOv8n ONNX via ONNX Runtime (modèle unique — économie VRAM)
- Classes : personne, véhicule, moto, camion, bus, vélo, animal, sac, arme, outil, plaque, visage
- Sortie : `{ class, confidence, bbox, timestamp, camera_id }`
- **Service** : `ai-engine/src/citevision_ai/detection/`

#### P3 — Tracking

- ByteTrack — track_id persistant, trajectoires
- Robustesse occlusions et croisements
- Re-ID léger optionnel (post-MVP)
- **Service** : `ai-engine/src/citevision_ai/tracking/`

#### P4 — Modélisation de scène

- Zones polygonales (interdite, parking, entrée, etc.)
- Lignes virtuelles (franchissement, sens interdit)
- Géométrie pure CPU — pas d'IA
- **Service** : backend + frontend `ZoneEditor`

#### P5 — Génération d'événements atomiques

Événements élémentaires produits par interaction objet × scène :

- Présence / absence / apparition / disparition
- Entrée / sortie zone, traversée ligne
- Immobilité prolongée, regroupement, séparation
- Métadonnées : durée, vitesse, direction, densité locale

**Service** : `ai-engine/src/citevision_ai/events/`

#### P6 — Analyse comportementale

- Trajectoires complètes, fenêtres temporelles glissantes
- Errance, rondes, arrêts suspects, flux anormaux
- Heatmaps de présence, vitesse moyenne
- Heuristiques CPU — pas de modèle lourd
- **Service** : `ai-engine/src/citevision_ai/analytics/behavior.py`

#### P7 — Moteur d'état

États dynamiques par entité : `normal` → `observé` → `suspect` → `critique`

- Accumulation événements dans le temps
- Réduction faux positifs
- **Service** : `ai-engine/src/citevision_ai/analytics/state.py`

#### P8 — Corrélation multi-entités

Relations : personne-objet, véhicule-plaque, groupes, infrastructure fixe

- Scénarios : vol, agression, intrusion coordonnée, accident
- **Service** : `ai-engine/src/citevision_ai/analytics/correlation.py`

#### P9 — Moteur de règles déclaratives

Structure condition-action :

```
OBJETS + CONTEXTE SPATIAL + ÉVÉNEMENTS + CONDITIONS TEMPORELLES → ACTIONS
```

- Opérateurs ET / OU / NON
- Seuils durée, vitesse, densité, probabilité
- Simulation avant activation
- **Service** : `backend/internal/rules/`

#### P10 — Système d'actions

Actions déclenchées par règles validées :

- Alerte UI / push / email / SMS / webhook
- Enregistrement clip contextuel MinIO
- Incident PostgreSQL
- Déclenchement relais (MQTT → IoT)
- **Service** : `backend/internal/alerts/`

#### P11 — Reconnaissance faciale (optionnelle par caméra)

- InsightFace — détection RetinaFace, embedding ArcFace
- Watchlist locale, corrélation multi-caméra
- Activation sélective pour économie GPU
- **Service** : `ai-engine/src/citevision_ai/face/`

#### P12 — Reconnaissance plaques (ANPR)

- PaddleOCR — détection + OCR + normalisation
- Base véhicules locale
- **Service** : `ai-engine/src/citevision_ai/anpr/`

#### P13 — Trafic et densités

- Agrégation statistique objets trackés
- Congestion, embouteillage, flux, saturation
- Sans modèle density map lourd en MVP
- **Service** : analytics + règles

#### P14 — Sécurité et infrastructures

- Intrusion, accès hors horaires, périmètre
- Zones machines, EPI, logistique
- Principalement règles + événements — pas d'IA supplémentaire

#### P15 — Scénarios composites

Combinaison multi-événements dans fenêtres temporelles :

- Vol suspect, vandalisme, accident, bagarre, intrusion avancée
- Cœur de l'intelligence « métier » du produit
- **Service** : moteur de règles + corrélation

### 3.3 Budget GPU adaptatif

Géré par `ResourceBudgetManager` (`ai-engine/src/citevision_ai/budget/resource_budget.py`).

| Caméras actives | Résolution analyse | FPS cible | Sampling | Modules optionnels |
|-----------------|-------------------|-----------|----------|-------------------|
| 1 | 1080p (1920×1080) | 5 | 1 frame / 3 | Face + ANPR activables |
| 2–4 | 640p (640×480) | 5 | 1 frame / 4 | Face sélectif |
| 5–12 | 320p (320×240) | 5 | 1 frame / 5 | Face/ANPR suspendus |

Enregistrement : **720p H.264** indépendamment de l'analyse (pipeline dual ADR-001).

Sous saturation GPU : réduire FPS → suspendre modules optionnels → prioriser caméras marquées « critiques ».

---

## Section 4 — 15 familles de détections

Chaque famille est implémentée via **événements atomiques (P5)** + **règles (P9)** + éventuellement **composites (P15)**. Aucune famille ne nécessite de modifier le code moteur — seulement de la configuration.

### 4.1 Famille 1 — Présence et mouvement (niveau base)

| Type de détection | Code événement suggéré |
|-------------------|------------------------|
| Apparition d'un objet (personne, véhicule, etc.) | `object.appeared` |
| Disparition d'un objet | `object.disappeared` |
| Présence dans une zone | `zone.presence` |
| Absence dans une zone | `zone.absence` |
| Déplacement dans une zone | `zone.movement` |
| Immobilité prolongée | `object.stationary` |
| Mouvement anormal (changement brusque de direction) | `track.direction_change` |
| Errance (trajet non linéaire prolongé) | `behavior.loitering_path` |
| Stationnement (véhicule ou objet statique) | `object.parked` |

### 4.2 Famille 2 — Franchissement spatial

| Type de détection | Code événement suggéré |
|-------------------|------------------------|
| Entrée dans une zone | `zone.enter` |
| Sortie d'une zone | `zone.exit` |
| Passage de frontière | `zone.cross_boundary` |
| Traversée de ligne (line crossing) | `line.cross` |
| Sens interdit (direction inversée) | `line.wrong_direction` |
| Contournement interdit | `zone.bypass` |
| Accès à zone restreinte | `zone.restricted_access` |
| Intrusion périmétrique | `perimeter.intrusion` |
| Sortie non autorisée | `zone.unauthorized_exit` |

### 4.3 Famille 3 — Temps et durée

| Type de détection | Code événement suggéré |
|-------------------|------------------------|
| Présence prolongée (loitering) | `time.loitering` |
| Stationnement interdit dépassé | `time.illegal_parking` |
| Rester trop longtemps dans zone sensible | `time.zone_overstay` |
| Temps d'attente anormal | `time.abnormal_wait` |
| Accumulation temporelle dans une zone | `time.accumulation` |
| Absence prolongée (personne attendue non présente) | `time.expected_absence` |

### 4.4 Famille 4 — Vitesse et dynamique

| Type de détection | Code événement suggéré |
|-------------------|------------------------|
| Excès de vitesse véhicule | `speed.exceeding` |
| Accélération brutale | `speed.hard_acceleration` |
| Décélération brutale | `speed.hard_braking` |
| Changement de direction anormal | `speed.abnormal_turn` |
| Mouvement erratique | `speed.erratic` |
| Course / fuite (personne) | `speed.running` |
| Conduite dangereuse | `speed.dangerous_driving` |
| Arrêt brusque | `speed.sudden_stop` |

### 4.5 Famille 5 — Trafic et circulation

| Type de détection | Code événement suggéré |
|-------------------|------------------------|
| Embouteillage (densité + faible vitesse) | `traffic.jam` |
| Congestion | `traffic.congestion` |
| Flux anormal de véhicules | `traffic.abnormal_flow` |
| Contre-sens routier | `traffic.wrong_way` |
| Stationnement illégal | `traffic.illegal_park` |
| Blocage de voie | `traffic.lane_blocked` |
| Route saturée | `traffic.saturated` |
| Accident probable (arrêt + densité + dispersion) | `traffic.accident_probable` |

### 4.6 Famille 6 — Foule et comportement collectif

| Type de détection | Code événement suggéré |
|-------------------|------------------------|
| Attroupement (crowd formation) | `crowd.formation` |
| Dissolution de groupe | `crowd.dispersion` |
| Mouvement de foule coordonné | `crowd.coordinated_movement` |
| Panique (dispersion rapide) | `crowd.panic` |
| Regroupement suspect | `crowd.suspicious_gathering` |
| Densité excessive dans une zone | `crowd.overdensity` |
| File d'attente anormale | `crowd.abnormal_queue` |
| Migration de masse | `crowd.mass_migration` |

### 4.7 Famille 7 — Sécurité et intrusion

| Type de détection | Code événement suggéré |
|-------------------|------------------------|
| Intrusion zone interdite | `security.zone_intrusion` |
| Intrusion nuit / hors horaires | `security.after_hours` |
| Présence non autorisée | `security.unauthorized_presence` |
| Double entrée non validée | `security.tailgating` |
| Contournement de contrôle | `security.checkpoint_bypass` |
| Passage hors point d'accès | `security.off_entry_point` |
| Escalade de périmètre (mur, barrière) | `security.perimeter_breach` |
| Infiltration progressive | `security.progressive_infiltration` |

### 4.8 Famille 8 — Objets et manipulation

| Type de détection | Code événement suggéré |
|-------------------|------------------------|
| Objet abandonné | `object.abandoned` |
| Objet déplacé | `object.moved` |
| Objet volé | `object.stolen` |
| Objet laissé sans surveillance | `object.unattended` |
| Prise d'objet | `object.pickup` |
| Dépôt d'objet | `object.dropoff` |
| Échange d'objet entre personnes | `object.handoff` |
| Objet suspect dans zone publique | `object.suspicious` |

### 4.9 Famille 9 — Vol et comportement criminel

| Type de détection | Code événement suggéré |
|-------------------|------------------------|
| Approche → prise → fuite | `theft.approach_grab_flee` |
| Disparition d'objet après interaction humaine | `theft.object_vanish` |
| Vol en mouvement | `theft.in_motion` |
| Vol en groupe (coordination multi-personnes) | `theft.group_coordination` |
| Observation préalable (loitering + focus objet) | `theft.casing` |
| Dissimulation d'objet | `theft.concealment` |
| Comportement furtif | `theft.furtive_behavior` |

### 4.10 Famille 10 — Vandalisme

| Type de détection | Code événement suggéré |
|-------------------|------------------------|
| Dégradation d'objet fixe | `vandalism.property_damage` |
| Mouvement violent sur infrastructure | `vandalism.violent_interaction` |
| Rassemblement + action rapide + dispersion | `vandalism.hit_and_run_group` |
| Temps court + forte activité locale | `vandalism.burst_activity` |
| Chute / destruction d'objet | `vandalism.destruction` |
| Interaction répétée sur zone sensible | `vandalism.repeated_targeting` |

### 4.11 Famille 11 — Reconnaissance d'identité

| Type de détection | Code événement suggéré |
|-------------------|------------------------|
| Personne connue / inconnue | `identity.known / identity.unknown` |
| Liste noire (watchlist) | `identity.blacklist_match` |
| Présence répétée d'un individu | `identity.repeat_presence` |
| Association visage + comportement suspect | `identity.face_behavior_link` |
| Véhicule identifié / non identifié | `identity.vehicle_known` |
| Plaque enregistrée / non enregistrée | `identity.plate_known` |
| Corrélation personne-véhicule | `identity.person_vehicle_link` |

### 4.12 Famille 12 — Transport et véhicules

| Type de détection | Code événement suggéré |
|-------------------|------------------------|
| Véhicule en infraction | `vehicle.violation` |
| Véhicule arrêté illégalement | `vehicle.illegal_stop` |
| Dépassement de vitesse | `vehicle.speeding` |
| Sens interdit | `vehicle.wrong_way` |
| Stationnement prolongé | `vehicle.extended_parking` |
| Blocage de voie | `vehicle.lane_block` |
| Entrée interdite véhicule | `vehicle.restricted_entry` |
| Véhicule suspect stationnaire | `vehicle.suspicious_stationary` |
| Changement de voie dangereux | `vehicle.dangerous_lane_change` |

### 4.13 Famille 13 — Incidents urbains

| Type de détection | Code événement suggéré |
|-------------------|------------------------|
| Accident probable (arrêt + regroupement + dispersion) | `urban.accident` |
| Bagarre (mouvement violent multi-personnes) | `urban.fight` |
| Fuite de foule | `urban.crowd_flee` |
| Blocage total de route | `urban.road_blocked` |
| Incident critique (multi-zones affectées) | `urban.critical_incident` |
| Dégradation infrastructure publique | `urban.infrastructure_damage` |

### 4.14 Famille 14 — Industriel / infrastructures

| Type de détection | Code événement suggéré |
|-------------------|------------------------|
| Intrusion site sécurisé | `industrial.site_intrusion` |
| Mouvement dans zone machine dangereuse | `industrial.machine_zone` |
| Arrêt d'activité anormal | `industrial.activity_stop` |
| Fuite de personnel | `industrial.personnel_evacuation` |
| Congestion logistique | `industrial.logistics_congestion` |
| Mauvais sens circulation interne | `industrial.wrong_internal_flow` |

### 4.15 Famille 15 — Composites (priorité maximale)

Scénarios multi-signaux — configurés via règles P9 + corrélation P8 :

| Scénario composite | Conditions combinées |
|--------------------|---------------------|
| **Vol suspect** | personne + zone magasin + attente + prise objet + sortie rapide |
| **Embouteillage** | densité élevée + vitesse faible + durée > seuil |
| **Intrusion avancée** | franchissement zone + absence autorisation + présence prolongée |
| **Vandalisme** | groupe + activité rapide + objet fixe affecté + dispersion |
| **Accident routier** | arrêt brutal + véhicules multiples + absence mouvement + alerte secondaire |
| **Bagarre** | ≥2 personnes + mouvement violent + proximité < seuil |
| **Effraction** | intrusion périmètre + horaire nuit + présence non autorisée |

---

## Section 5 — Compléments enterprise

Fonctionnalités attendues pour parité Hikvision / Genetec. Implémentation progressive post-scaffold ; chaque feature = ticket `STATE.md`.

### 5.1 Santé caméra (Camera Health)

- Ping RTSP, FPS réel, latence, frames perdues
- Statuts : `online`, `degraded`, `offline`, `auth_error`
- Dashboard `SystemHealth` + alertes automatiques
- Reprise automatique avec backoff exponentiel

### 5.2 PTZ (Pan-Tilt-Zoom)

- Contrôle ONVIF PTZ depuis fiche caméra
- Presets, patrol, suivi objet (post-MVP)
- Journalisation audit de chaque commande PTZ

### 5.3 Mur vidéo (Video Wall)

- Vue `VideoWall` — grille 1×1 à 4×4 configurable
- Drag-and-drop caméras, plein écran par cellule
- Synchronisation horodatage multi-flux

### 5.4 Carte (Map)

- Vue `Map` — sites et caméras géolocalisés
- Clusters, statut couleur, clic → live view
- Fond tuiles offline (MBTiles local) — pas de Mapbox cloud

### 5.5 Replay forensique

- Timeline événements + lecture synchronisée enregistrements MinIO
- Export clip avec chaîne de custody (hash SHA-256 + audit)
- Navigation frame-par-frame, marqueurs événements

### 5.6 Recherche avancée

- Full-text PostgreSQL + filtres (date, caméra, type, sévérité, tenant)
- Recherche par track_id, plaque, identité
- Recherche sémantique (post-MVP, embeddings locaux)

### 5.7 Masques de confidentialité (Privacy Masks)

- Polygones de floutage permanents par caméra
- Anonymisation visages automatique (option RGPD)
- Masques exclus de l'enregistrement et de l'analyse IA

### 5.8 Calendriers et plages horaires

- Règles actives selon calendrier (jour/nuit, semaine, jours fériés)
- Fuseau par site (`sites.timezone`)
- Exceptions temporaires (maintenance, événement)

### 5.9 Mode simulation

- Injection d'événements synthétiques pour tester règles
- Replay fichier vidéo local sans caméra live
- Rapport PASS/FAIL par règle simulée

### 5.10 Déploiement canary

- Activer règle/modèle IA sur sous-ensemble caméras
- Comparer taux alertes canary vs production
- Promotion automatique ou rollback

### 5.11 Webhooks

- POST JSON signé HMAC vers URL configurée par tenant
- Retry avec backoff, dead-letter queue Redis
- Payload : événement, clip URL signée MinIO, métadonnées

### 5.12 Prometheus et observabilité

- Endpoint `/metrics` par service (Go, Python)
- Métriques : `cv_detections_total`, `cv_events_total`, `cv_gpu_utilization`, `cv_camera_status`, `cv_rule_eval_duration_seconds`
- Dashboard Grafana (docker-compose profile `monitoring`)

### 5.13 Multi-tenant

- Isolation stricte : `organizations` → `sites` → `cameras`
- Row-level security PostgreSQL par `org_id`
- Aucune fuite inter-tenant — tests d'isolation obligatoires

---

## Section 6 — RBAC — 7 rôles

### 6.1 Rôles système

| Rôle | Code | Description |
|------|------|-------------|
| Super administrateur | `super_admin` | Accès global tous tenants, configuration système |
| Administrateur organisation | `org_admin` | Gestion complète d'un tenant |
| Opérateur | `operator` | Surveillance live, acquittement alertes, PTZ |
| Analyste | `analyst` | Recherche, replay, rapports — pas de config |
| Superviseur | `supervisor` | Opérateur + validation alertes + gestion équipe |
| Lecteur seul | `viewer` | Consultation live et historique — lecture seule |
| Profil technique | `technician` | Santé système, caméras, logs — pas de données métier sensibles |

### 6.2 Granularité des permissions

Permissions assignables à chaque niveau :

| Niveau | Exemples |
|--------|----------|
| Global | `system.config`, `tenant.create` |
| Organisation | `org.users.manage`, `org.rules.edit` |
| Site | `site.cameras.view`, `site.zones.edit` |
| Caméra | `camera.live.view`, `camera.ptz.control`, `camera.config` |
| Zone | `zone.rules.apply` |
| Type d'alerte | `alert.acknowledge`, `alert.export` |
| Type d'événement | `event.view.security`, `event.view.traffic` |
| Module IA | `ai.face.enable`, `ai.anpr.enable` |

### 6.3 Permissions seed (minimum)

```
cameras:read, cameras:write, cameras:ptz
zones:read, zones:write
rules:read, rules:write, rules:simulate
alerts:read, alerts:ack, alerts:export
events:read, events:search
users:read, users:write
audit:read
system:health, system:config
recordings:read, recordings:export
```

### 6.4 Audit trail immuable

- Table `audit_logs` append-only
- Signature HMAC-SHA256 par entrée (`AUDIT_SIGNING_KEY` dans `.env`)
- Trigger PostgreSQL interdisant UPDATE/DELETE
- Champs : `actor_id`, `action`, `resource`, `payload_hash`, `ip`, `timestamp`

### 6.5 Authentification 2FA TOTP

- Activation optionnelle par utilisateur
- QR code à l'inscription 2FA (issuer : Citévision)
- Codes de secours hashés bcrypt
- JWT access 15 min + refresh 7 jours

### 6.6 Politique mot de passe

- Minimum 12 caractères
- Interdiction mots de passe communs
- Verrouillage après 5 échecs (15 min)

---

## Section 7 — UX et design system

### 7.1 Direction artistique

Esthétique **cyberpunk android/humanoid** — premium, sombre, précision chirurgicale.

- Fond dégradé profond navy → deep space
- Grille subtile cyan (scan lines optionnelles)
- Cartes glassmorphism (`backdrop-blur`, bordures lumineuses)
- Animations : fade-in, slide-in, pulse-slow — jamais agressives

### 7.2 Palette de couleurs

| Token | Hex | Usage |
|-------|-----|-------|
| `cv-deep` | `#050A12` | Fond principal dark |
| `cv-navy` | `#0A1628` | Surfaces, navbar |
| `cv-accent` | `#00D4FF` | Actions, liens, focus |
| `cv-accent-dim` | `#00A8CC` | Hover accent |
| `cv-surface` | `#0F1D32` | Cartes, panels |
| `cv-border` | `#1A2D4A` | Bordures |
| `cv-muted` | `#6B7F99` | Texte secondaire |

Thème light : accent `#0099CC`, fonds clairs — même structure.

### 7.3 Typographie

| Rôle | Police | Usage |
|------|--------|-------|
| Display | Rajdhani | Titres, logo, chiffres dashboard |
| Sans | Inter | Corps, labels, tables |

### 7.4 Composants UI

Basés sur shadcn/ui + classes utilitaires :

- `.cv-card`, `.cv-card-hover` — cartes
- `.cv-btn-primary`, `.cv-btn-secondary`, `.cv-btn-ghost` — boutons
- `.cv-input` — champs formulaire
- `SeverityBadge` — alertes (info, warning, critical)
- `PageHeader` — en-tête de page uniforme
- `LoadingState` — skeletons

### 7.5 Layout

```
┌──────────────────────────────────────────────┐
│ Navbar — logo œil, titre, theme, langue, user│
├──────────┬───────────────────────────────────┤
│ Sidebar  │ MainContent                       │
│ nav      │ pages (Dashboard, Live, Rules…)   │
└──────────┴───────────────────────────────────┘
```

Navigation : `frontend/src/config/navigation.ts` — filtrée par permissions RBAC.

### 7.6 Sons UI

Via Web Audio API (`useSound`) — désactivables (`MuteToggle`) :

| Son | Déclencheur | Caractère |
|-----|-------------|-----------|
| `click` | Boutons, toggles | Square wave court — feedback tactile |
| `sonar` | Alerte nouvelle | Sine sweep — ping cyberpunk |

### 7.7 Onboarding

- Tour guidé 5 étapes : Dashboard → Caméras → Zones → Règles → Alertes
- Skippable, rejouable depuis Paramètres
- Bulles d'aide contextuelle sur première visite de chaque page

### 7.8 Vues applicatives obligatoires

| Vue | Route | Rôle principal |
|-----|-------|----------------|
| Dashboard | `/` | KPIs, alertes récentes |
| Live View | `/live` | Flux caméra sélectionnée |
| Video Wall | `/wall` | Multi-flux |
| Map | `/map` | Géolocalisation |
| Caméras | `/cameras` | CRUD + discovery |
| Zone Editor | `/zones` | Polygones et lignes |
| Règles | `/rules` | Builder visuel |
| Alertes | `/alerts` | Acquittement |
| Événements | `/events` | Timeline |
| Utilisateurs | `/users` | RBAC admin |
| Audit | `/audit` | Journal immuable |
| Santé système | `/health` | Métriques |
| Paramètres | `/settings` | Profil, 2FA, préférences |

---

## Section 8 — 14 livrables détaillés L1–L14

### L1 — Architecture et squelettes

| Champ | Détail |
|-------|--------|
| **Scope** | Arborescence monorepo complète, squelettes tous services, Docker Compose base, docs initiales, **ce fichier PROMPT-AGENT.md** |
| **Fichiers clés** | `README.md`, `Makefile`, `docker-compose.yml`, `.env.example`, `.env`, `backend/go.mod`, `frontend/package.json`, `ai-engine/pyproject.toml`, `video-engine/CMakeLists.txt`, `shared/schemas/*.json`, `infrastructure/*`, `docs/*.md` |
| **Critères PASS** | `bash scripts/validate-l1.sh` — 0 FAIL |
| **Commandes test** | `bash scripts/validate-l1.sh` |

### L2 — Schémas JSON partagés

| Champ | Détail |
|-------|--------|
| **Scope** | Schémas `detection.json`, `event.json`, `rule.json` valides et documentés |
| **Fichiers clés** | `shared/schemas/detection.json`, `event.json`, `rule.json` |
| **Critères PASS** | JSON parseable Python ; champs requis présents |
| **Commandes test** | `bash scripts/validate-l2.sh` |

### L3 — Infrastructure Docker

| Champ | Détail |
|-------|--------|
| **Scope** | PostgreSQL 17, Redis 7, Mosquitto, MinIO + init bucket |
| **Fichiers clés** | `docker-compose.yml`, `infrastructure/mosquitto.conf`, `infrastructure/init-minio.sh` |
| **Critères PASS** | Services déclarés ; `docker compose up -d` sans erreur |
| **Commandes test** | `bash scripts/validate-l3.sh` ; `docker compose ps` |

### L4 — Packaging AI Engine

| Champ | Détail |
|-------|--------|
| **Scope** | Structure Python FastAPI, Dockerfile, dépendances |
| **Fichiers clés** | `ai-engine/pyproject.toml`, `requirements.txt`, `Dockerfile`, `src/citevision_ai/main.py` |
| **Critères PASS** | Fichiers packaging présents |
| **Commandes test** | `bash scripts/validate-l4.sh` |

### L5 — Détection YOLO + ByteTrack

| Champ | Détail |
|-------|--------|
| **Scope** | Inférence YOLOv8n ONNX + tracker ByteTrack fonctionnels |
| **Fichiers clés** | `ai-engine/src/citevision_ai/detection/yolo_onnx.py`, `tracking/bytetrack.py` |
| **Critères PASS** | Modules importables ; inférence sur frame test |
| **Commandes test** | `bash scripts/validate-l5.sh` ; `make download-model` |

### L6 — ResourceBudgetManager

| Champ | Détail |
|-------|--------|
| **Scope** | Budget GPU adaptatif 1/4/12 caméras |
| **Fichiers clés** | `ai-engine/src/citevision_ai/budget/resource_budget.py` |
| **Critères PASS** | Tests unitaires résolution/FPS par count |
| **Commandes test** | `bash scripts/validate-l6.sh` ; `pytest ai-engine/tests/test_resource_budget.py` |

### L7 — Publisher MQTT

| Champ | Détail |
|-------|--------|
| **Scope** | Publication détections sur `cv/detections/{camera_id}` |
| **Fichiers clés** | `ai-engine/src/citevision_ai/mqtt/publisher.py` |
| **Critères PASS** | Topic correct ; message JSON schema-valid |
| **Commandes test** | `bash scripts/validate-l7.sh` ; `mosquitto_sub -t 'cv/detections/#' -v` |

### L8 — Générateur d'événements

| Champ | Détail |
|-------|--------|
| **Scope** | Événements zone enter/exit, line cross, loitering |
| **Fichiers clés** | `ai-engine/src/citevision_ai/events/generator.py` |
| **Critères PASS** | Événements conformes `event.json` |
| **Commandes test** | `bash scripts/validate-l8.sh` |

### L9 — Moteurs analytiques

| Champ | Détail |
|-------|--------|
| **Scope** | Behavior, state engine, correlation engine |
| **Fichiers clés** | `ai-engine/src/citevision_ai/analytics/behavior.py`, `state.py`, `correlation.py` |
| **Critères PASS** | Modules présents et importables |
| **Commandes test** | `bash scripts/validate-l9.sh` |

### L10 — Stubs Face et ANPR

| Champ | Détail |
|-------|--------|
| **Scope** | Interfaces InsightFace et PaddleOCR (stubs retournant résultats vides) |
| **Fichiers clés** | `ai-engine/src/citevision_ai/face/insightface_stub.py`, `anpr/paddleocr_stub.py` |
| **Critères PASS** | Stubs intégrables au pipeline sans crash |
| **Commandes test** | `bash scripts/validate-l10.sh` |

### L11 — Tests pytest

| Champ | Détail |
|-------|--------|
| **Scope** | Suite pytest AI engine + tests budget, events, tracking |
| **Fichiers clés** | `ai-engine/tests/test_resource_budget.py`, `ai-engine/tests/*` |
| **Critères PASS** | `pytest` vert |
| **Commandes test** | `bash scripts/validate-l11.sh` ; `bash scripts/run-all-tests.sh` |

### L12 — Video Engine C++

| Champ | Détail |
|-------|--------|
| **Scope** | Projet CMake FFmpeg-ready, ingest RTSP stub, health HTTP |
| **Fichiers clés** | `video-engine/CMakeLists.txt`, `video-engine/README.md`, `src/*` |
| **Critères PASS** | CMake configure ; binaire compile sur WSL |
| **Commandes test** | `bash scripts/validate-l12.sh` ; `make build-video` |

### L13 — Documentation complète

| Champ | Détail |
|-------|--------|
| **Scope** | Docs à jour : STATE, DECISIONS, ARCHITECTURE, PORTS, INSTALL, OPERATIONS |
| **Fichiers clés** | `docs/STATE.md`, `docs/DECISIONS.md`, `docs/ARCHITECTURE.md`, etc. |
| **Critères PASS** | Tous fichiers docs présents et cohérents avec code |
| **Commandes test** | `bash scripts/validate-l13.sh` |

### L14 — Validation finale et commit Git

| Champ | Détail |
|-------|--------|
| **Scope** | Exécution validate-final, commit intégral, push dépôt privé |
| **Fichiers clés** | Tout le dépôt |
| **Critères PASS** | `validate-final.sh` PASS ; `run-all-tests.sh` PASS ; git clean |
| **Commandes test** | `bash scripts/validate-final.sh` ; `make validate` |

**Procédure L14 :**

```bash
bash scripts/validate-final.sh
git add -A
git status   # vérifier .env inclus (dépôt privé)
git commit -m "Citévision 2.0 — livraison L1-L14 complète"
git push -u origin main
```

Mettre à jour `docs/STATE.md` : livrable 14 = **Terminé**.

---

## Section 9 — Matrice de tests

### 9.1 Tests unitaires

| Domaine | Outil | Cible | Seuil |
|---------|-------|-------|-------|
| Python AI | pytest | budget, events, tracking, schemas | ≥ 80 % modules critiques |
| Go backend | go test | auth, rbac, rules parser | ≥ 70 % packages |
| Frontend | vitest | hooks, stores, utils | Composants pure logic |

### 9.2 Tests d'intégration

| Scénario | Vérification |
|----------|--------------|
| AI → MQTT → Backend | Message detection consommé et persisté |
| Backend → PostgreSQL | Migrations, CRUD caméra, règle |
| Video → AI | Frame HTTP POST `/analyze/frame` |
| Auth flow | Login → JWT → route protégée → refresh |
| Multi-tenant | User tenant A ne voit pas caméras tenant B |

### 9.3 Tests end-to-end (e2e)

| Parcours | Outil suggéré |
|----------|---------------|
| Login → Dashboard → Live view | Playwright |
| Ajout caméra → apparition live | Playwright + TEST_CAMERA via .env |
| Création règle → simulation → alerte | Playwright |

### 9.4 Tests de charge

| Profil | Critère |
|--------|---------|
| 1 caméra 1080p | GPU < 70 %, latence inference < 200 ms |
| 4 caméras 640p | GPU < 85 %, 0 crash 1 h |
| 12 caméras 320p | GPU ≤ 95 %, débit événements stable 30 min |

Outil : script `scripts/load-test.sh` (à créer) + métriques Prometheus.

### 9.5 Tests de performance

- Latence bout-en-bout detection → alerte UI < 2 s (P95)
- Démarrage cold start stack Docker < 60 s
- Requête recherche événements 10k rows < 500 ms

### 9.6 Tests esthétiques

- Thème dark + light sans régression visuelle
- Responsive 1280px → 1920px → 2560px
- Pas d'émojis ; icônes outline uniquement
- Contraste WCAG AA minimum sur texte principal

### 9.7 Tests de robustesse

| Condition | Comportement attendu |
|-----------|---------------------|
| Caméra RTSP coupée | Reconnexion auto, statut `offline` |
| MQTT broker down | Buffer local, retry |
| PostgreSQL restart | Reconnexion pool pgx |
| GPU OOM | Dégradation résolution, pas de crash process |
| Inondation alertes | Rate limiting règles, anti-duplication |

### 9.8 Tests sécurité OWASP

| Risque | Test |
|--------|------|
| Injection SQL | Requêtes paramétrées pgx — fuzz inputs |
| XSS | Échappement React ; CSP headers |
| CSRF | SameSite cookies / token double submit |
| Auth bypass | Routes sans JWT → 401 |
| IDOR | Accès ressource autre tenant → 403 |
| Secrets exposés | Scan repo — aucun secret hors .env |
| Audit tampering | UPDATE audit_logs → trigger deny |

---

## Section 10 — Documentation et continuité

### 10.1 Format STATE.md

Mettre à jour **après chaque livrable** :

```markdown
# Citévision 2.0 — Project State

**Last updated:** YYYY-MM-DD
**Version:** 2.0.x

## Current Phase
[Description phase courante]

## Component Status
| Component | Status | Notes |
...

## Livrables L1-L14
| # | Nom | Statut | Validé le |
...

## Completed
- [x] ...

## Next Steps
- [ ] ...

## Known Issues
- ...
```

### 10.2 Format DECISIONS.md

Une ADR par décision :

```markdown
## ADR-NNN: Titre court

**Decision:** [choix retenu]
**Rationale:** [pourquoi]
**Alternatives considered:** [rejetées]
**Date:** YYYY-MM-DD
```

Numérotation séquentielle. Ne jamais supprimer une ADR — deprecate avec lien vers remplaçante.

### 10.3 Documents obligatoires

| Fichier | Contenu |
|---------|---------|
| `PROMPT-AGENT.md` | Ce document |
| `STATE.md` | État courant |
| `DECISIONS.md` | ADR |
| `ARCHITECTURE.md` | Diagrammes, flux |
| `PORTS.md` | Référence ports |
| `INSTALL.md` | Installation WSL/Docker |
| `OPERATIONS.md` | Runbook prod |

### 10.4 Reprise par un nouvel agent

Checklist reprise :

1. Lire PROMPT-AGENT.md + STATE.md + DECISIONS.md
2. Identifier livrable courant dans STATE.md
3. Exécuter `bash scripts/validate-l{X}.sh` pour état réel
4. Reprendre au livrable indiqué — ne pas recommencer from scratch

---

## Section 11 — Structure du dépôt

### 11.1 Chemin canonique

| Environnement | Chemin |
|---------------|--------|
| WSL Ubuntu 24.04 | `/home/gheno/citevision` |
| Windows (Cursor) | `C:\Users\gheno\citevision` |
| Équivalence | `/mnt/c/Users/gheno/citevision` depuis WSL |

**OS cible dev** : WSL Ubuntu 24.04 — bash pour tous les scripts.

### 11.2 Arborescence

```
citevision/
├── ai-engine/              # Python FastAPI — détection, tracking, MQTT
│   ├── src/citevision_ai/
│   ├── tests/
│   ├── models/             # YOLO ONNX (non versionné — download)
│   ├── Dockerfile
│   └── pyproject.toml
├── backend/                # Go API — auth, RBAC, règles, caméras
│   ├── cmd/api/
│   ├── cmd/seed/
│   ├── internal/
│   └── migrations/
├── frontend/               # React Vite TS — dashboard
│   ├── src/
│   └── public/
├── video-engine/           # C++ FFmpeg — RTSP ingest
│   ├── src/
│   └── CMakeLists.txt
├── infrastructure/         # Config Docker services
├── shared/schemas/         # JSON Schema inter-services
├── scripts/                # validate-l*.sh, setup, start/stop
├── docs/                   # Documentation projet
├── data/                   # Enregistrements locaux (gitignored contenu)
├── models/                 # Modèles partagés
├── docker-compose.yml
├── Makefile
├── .env                    # Secrets (commité — dépôt privé)
├── .env.example            # Template sans secrets réels
└── README.md
```

### 11.3 Conventions

| Élément | Convention |
|---------|------------|
| Branches | `main` — livraison L14 |
| Commits | Conventional commits en anglais |
| Migrations SQL | `backend/migrations/NNNNNN_description.up.sql` |
| MQTT topics | `cv/{type}/{id}` |
| IDs caméra | `cam-NNN` (ex: `cam-001`) |
| Logs | JSON structuré, niveau via `LOG_LEVEL` |

### 11.4 Ports (référence rapide)

| Service | Port |
|---------|------|
| Backend API | 8080 |
| AI Engine | 8000 |
| Frontend dev | 5173 |
| PostgreSQL | 5432 |
| Redis | 6379 |
| MQTT | 1883 |
| MQTT WS | 9001 |
| MinIO API | 9000 |
| MinIO Console | 9090 |
| Video Engine health | 9010 |

Détail complet : `docs/PORTS.md`.

---

## Section 12 — Décisions figées

> Décisions validées par le propriétaire — **ne pas remettre en question** sans ADR explicite.

### ADR-001 : Pipeline vidéo dual

Analyse basse résolution + enregistrement 720p séparés. Voir `docs/DECISIONS.md`.

### ADR-002 : MQTT pour transport détections

Topic `cv/detections/{camera_id}` via Mosquitto.

### ADR-003 : Budget ressources adaptatif

| Caméras | Résolution | FPS |
|---------|------------|-----|
| 1 | 1080p | 5 |
| 2–4 | 640p | 5 |
| 5–12 | 320p | 5 |

### ADR-004 : ONNX Runtime pour inférence

YOLOv8n export ONNX — pas de PyTorch en production.

### ADR-005 : ByteTrack pour tracking

Baseline sans Re-ID embeddings en MVP.

### ADR-006 : Stubs Face et ANPR

Interfaces InsightFace / PaddleOCR — stubs jusqu'à activation GPU budget.

### ADR-007 : MVP 12 caméras max

Limite matérielle RTX 4050 6 Go — `MAX_CAMERAS=12` dans `.env`.

### ADR-008 : Dépôt privé avec .env commité

Le fichier `.env` réel est **commité** dans le dépôt privé `henockglory/Cityvision-version2.0` par choix explicite du propriétaire. `.env.example` reste le template documenté. **Régénérer le PAT GitHub** si fuite.

### ADR-009 : Rétention données

| Type | Durée défaut | Configurable |
|------|--------------|--------------|
| Événements / alertes PostgreSQL | 30 jours | Oui |
| Enregistrements vidéo MinIO | 7 jours | Oui |
| Snapshots / vignettes | 7 jours | Oui |
| Embeddings faciaux | 30 jours | Oui |
| Logs techniques | 7 jours | Oui |
| Audit immuable | **Illimité** | Non (archivage froid optionnel) |

### ADR-010 : Commit Git uniquement L14

Aucun commit intermédiaire sauf demande explicite. Push final vers GitHub au L14.

### ADR-011 : Offline 100 %

Zéro dépendance SaaS cloud en production. Tous modèles IA locaux.

### ADR-012 : i18n FR + EN dès le départ

Français défaut, anglais secondaire — pas de langue unique.

### ADR-013 : shadcn/ui + Lucide outline

Base composants frontend — pas d'émojis, pas d'icônes filled par défaut.

### ADR-014 : WSL Ubuntu 24.04 environnement principal

Scripts bash, pas PowerShell, pour validation et CI locale.

### ADR-015 : TEST_CAMERA via .env uniquement

`192.168.1.108` / `admin` / `hids+1234` — jamais hardcodés.

---

## Annexe A — Commandes de référence rapide

```bash
# Setup initial
cp .env.example .env   # si .env absent
bash scripts/setup-wsl.sh

# Infrastructure
docker compose up -d postgres redis mosquitto minio

# Modèle YOLO
make download-model

# Validation livrable X
bash scripts/validate-lX.sh

# Validation complète
make validate

# Tests Python
bash scripts/run-all-tests.sh

# Dev AI engine
make ai-dev

# Build video engine
make build-video
```

---

## Annexe B — Checklist agent avant clôture L14

- [ ] L1 à L13 : tous `validate-lX.sh` PASS
- [ ] `validate-final.sh` PASS
- [ ] `run-all-tests.sh` PASS
- [ ] `docs/STATE.md` à jour (livrable 14 terminé)
- [ ] `docs/DECISIONS.md` contient toutes ADR
- [ ] Aucun secret hardcodé hors `.env`
- [ ] Aucun placeholder UI sans ticket STATE
- [ ] i18n FR+EN complet sur strings UI
- [ ] Thèmes light/dark fonctionnels
- [ ] Commit + push dépôt privé

---

*Fin du prompt agent Citévision 2.0*
