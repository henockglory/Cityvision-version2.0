# CitéVision — Architecture complète RTSP → notification + retour d’expérience 1-hit Gemini payant

> **Fichier destiné à un assistant IA (et à un humain)** : lire de bout en bout avant toute modification runtime.  
> **Date de rédaction** : 2026-08-01  
> **Chemin Windows** : `C:\Users\gheno\citevision\docs\HANDOFF-ARCHITECTURE-COMPLETE-1HIT-GEMINI.md`  
> **Runtime de vérité** : WSL `~/citevision-v2` (pas Docker Desktop ; pas synchronisation manuelle Windows↔WSL comme source d’exécution).  
> **Socle non négociable** : zone → IA → règle → preuve · pas de hardcode de zones · pas de forge de preuves · « validé » = artefacts complets.

Ce document est volontairement **très long**. Il décrit :

1. L’architecture fonctionnelle de bout en bout.  
2. **Toutes** les familles de règles du catalogue (matrice d’honnêteté + `event_type`).  
3. Le détail des 5 règles démo et le rôle de Frigate / IA locale / Gemini.  
4. Le déroulé des tests 1-hit Gemini payant, les blocages, ce qui a été corrigé, et pourquoi les résultats finaux sont ce qu’ils sont.  
5. Une analyse spécifique **feu rouge** (pourquoi le 1-hit échoue alors que « on voit le feu rouge + une voiture »).  
6. Des propositions de **re-orchestration** Frigate + IA locale + Gemini (avec bouts de code).  
7. Des **dizaines de questions** à trancher + **micro-tests** avant le prochain 1-hit.

---

## 0. Comment un assistant IA doit utiliser ce fichier

1. Ne pas affirmer « 5/5 validé » sans artefacts `validate_rule.sh` + captures UI.  
2. Ne jamais écrire de zones en dur ni scripts `_fix_zone_*` qui réécrivent la géométrie.  
3. Distinguer **émission d’événement** (`event_type`) et **alerte finale avec preuves** (`evidence_status=complete`).  
4. Distinguer **échec quota Gemini** (`rate_limited`) et **échec jugement** (`unclear` / `visible=false` / fail-closed).  
5. Quand `FRIGATE_VLM_BRIDGE=1`, le chemin local HSV **n’émet plus** `red_light_violation` : il ne fait que le **gate couleur** ; Gemini décide l’émission.

---

## 1. Carte mentale en une page

```text
Caméra / fichier démo
        │ RTSP (ou loop ffmpeg)
        ▼
   go2rtc  ──────────────────────────► UI Live (WebRTC/MSE)
        │
        ├──► Frigate (detect + track + zones + speed estimate + snapshots/clips)
        │         │ MQTT frigate/events
        │         ▼
        │    AI Engine · FrigateEventBridge
        │         ├── speed_measurement → emit speeding (si > limite)
        │         ├── red_light_observation + HSV red → enqueue Gemini
        │         ├── seatbelt / phone (cabin) → enqueue Gemini
        │         ├── plate_ocr / face → enqueue Gemini (si activé)
        │         └── snapshots Frigate (bbox crop)
        │
        └──► AI Engine pipeline locale (YOLO/ONNX + analytics + HSV)
                  │ MQTT citevision events
                  ▼
            Rules-engine (conditions JSON sur event_type / zone / …)
                  │
                  ▼
            Backend (persist event → alert si règle match)
                  │
                  ▼
            Evidence service (clip 6s, scene, subject, plate…)
                  │
                  ▼
            Canaux : UI Alerts · Mail (Mailhog démo) · webhooks…
```

**Principe produit** : une règle UI n’est « vraie » que si un `event_type` réel est émis **et** (selon politique) des preuves sont assemblées. Gemini est un **juge sémantique async**, jamais un bloqueur du flux RTSP.

---

## 2. Environnement & vérité opérationnelle

| Sujet | Vérité |
|-------|--------|
| Édition + runtime | WSL `~/citevision-v2` |
| Miroir Windows | `C:\Users\gheno\citevision` (docs, code source miroir ; **ne pas** traiter comme runtime) |
| Docker | dockerd natif WSL uniquement |
| Org / caméras | IDs **jamais** hardcodés dans la logique métier — résolution live API/DB |
| Secrets Gemini | **uniquement** `~/citevision-v2/.env` — jamais commit / `.env.example` / docs |
| Health AI | `GET http://127.0.0.1:8001/health` |
| Blockers debug | `GET http://127.0.0.1:8001/debug/rule-blockers` |
| Frigate | `http://127.0.0.1:5000` |

Variables critiques (extrait conceptuel) :

```bash
GEMINI_ENABLED=1
GEMINI_API_KEY=***   # ne jamais logger
GEMINI_MODEL=gemini-2.5-flash   # Pro seulement si Flash insuffisant
GEMINI_MIN_INTERVAL_SEC=5
GEMINI_QUEUE_SIZE=4
GEMINI_PROCESS_EVERY_N=25
FRIGATE_VLM_BRIDGE=1
FRIGATE_SPEED_BRIDGE=1
FRIGATE_VLM_BRIDGE_CROP_MODE=vehicle_bbox
```

Fichier config Pydantic : `ai-engine/src/citevision_ai/config.py` (`gemini_*`, `frigate_vlm_bridge`, `frigate_speed_bridge`).

---

## 3. Flux détaillé RTSP → notification

### 3.1 Ingest vidéo

1. Caméra IP ou **vidéo démo** (fichier) est publiée dans **go2rtc** (streams RTSP/WebRTC).  
2. Le backend peut « heal » / enregistrer les streams (`repair-streams`, ingest orchestrator).  
3. Frigate consomme le RTSP go2rtc ; l’AI engine peut aussi lire le flux (pipeline unifiée / overlay).

### 3.2 Frigate

Rôle : détection objets, tracking, **zones compilées** depuis la DB CitéVision (`cv_zone_<uuid>`), estimations de vitesse, snapshots, clips.

Le compilateur Frigate côté backend : `backend/internal/frigate/compiler.go` — transforme polygones/lignes/behaviors ZoneEditor → YAML Frigate. **Les géométries vivent dans ZoneEditor/DB**, pas dans le code.

MQTT typique : topic `frigate/events` avec payload `before` / `after` (label, box, zones, estimated speed…).

### 3.3 Bridge Frigate → AI (`FrigateEventBridge`)

Fichier : `ai-engine/src/citevision_ai/frigate_bridge/bridge.py`.

Boucle conceptuelle :

```python
# Pseudocode fidèle à bridge.py
for mqtt_event in frigate_events:
    after = event["after"]
    label = after["label"]          # car, truck, person…
    zones = current ∪ entered
    for zone in zones:
        behavior = zone.behavior    # depuis index spatial DB
        if behavior in cabin_behaviors and VLM:
            _maybe_cabin(...)       # seatbelt / phone
        if behavior == "red_light_observation" and VLM:
            _maybe_red_light(...)   # gate HSV puis Gemini
        if behavior == "plate_ocr":
            _maybe_plate(...)
        if person + face enabled:
            _maybe_face(...)
    for exited_zone in exited:
        if behavior == "speed_measurement" and SPEED_BRIDGE:
            _maybe_speed(...)       # compare estimate vs limit → emit speeding
```

### 3.4 Pipeline IA locale

Fichier : `ai-engine/src/citevision_ai/pipeline.py`.

- YOLO / tracking / analytics spatiales (zone_enter, line_cross, loitering…).  
- `TrafficLightAnalyzer` HSV (`road_enforcement/traffic_light.py`).  
- Secondary ONNX (cabin) si Gemini off.  
- Face / plate engines locaux selon modules.  
- Publication MQTT événements + déclenchement evidence.

**Point critique feu rouge** :

```1037:1048:ai-engine/src/citevision_ai/pipeline.py
        # HSV colour state always; violation emits only when bridge OFF.
        # With FRIGATE_VLM_BRIDGE: state_only gate for Gemini red_light.
        if tl_active:
            all_events.extend(
                self.traffic_light.process_frame(
                    camera_id,
                    frame,
                    track_dicts,
                    ts,
                    zones_cfg,
                    state_only=bool(settings.frigate_vlm_bridge),
                )
            )
```

Donc : **avec le bridge ON, le moteur local que vous avez vu « marcher avant » n’émet plus l’infraction** ; il ne maintient que l’état HSV pour ouvrir/fermer la porte Gemini.

### 3.5 Gemini VLM (async)

- Client : `ai-engine/src/citevision_ai/vlm/gemini_client.py`  
- File d’attente : `ai-engine/src/citevision_ai/vlm/queue.py`  
- Jamais dans le hot-path RTSP.  
- Gate d’émission :

```336:350:ai-engine/src/citevision_ai/vlm/gemini_client.py
def should_emit(verdict: GeminiVerdict, *, min_confidence: float) -> bool:
    """Canonical emit gate for cabin/face/plate (violation=true means positive detection)."""
    if not verdict.raw_ok or verdict.error:
        return False
    if not verdict.visible:
        return False
    if "unclear" in {s.lower() for s in verdict.signals}:
        return False
    ...
    if not verdict.violation:
        return False
    return float(verdict.confidence) >= float(min_confidence)
```

Si Gemini dit `visible=false` ou `signals=["unclear"]` → **reject**, compteur `vlm_queue_unclear`, **aucune alerte**. C’est volontaire (fail-closed / R.2).

### 3.6 Rules-engine

Les règles stockées en DB ont des conditions du type :

```json
{ "op": "eq", "field": "event_type", "value": "red_light_violation" }
```

Sync : `rules-engine/internal/syncrules/sync.go`.  
Une règle match → le backend crée / met à jour une **alerte**.

### 3.7 Evidence (preuve différée)

Politique R.2 : détection rapide ≠ preuve prête.

Chaîne typique routière :

1. Événement avec `frigate_event_id` + bbox.  
2. Attente clip Frigate / `end_time`.  
3. Composition : clip ~6 s, scene, subject, plaque si applicable.  
4. `evidence_status` : `complete` | `partial` | `missing` (+ cause : `scene_green`, `align_too_large`, `clip_not_ready`, …).  
5. **Interdit** : fabriquer une plaque = subject JPEG.

Handlers backend : `backend/internal/handler/evidence.go`, `backend/internal/evidence/service.go`.  
AI evidence : `ai-engine/src/citevision_ai/evidence/`.

### 3.8 Notification

- UI : pages Events / Alerts / LiveView.  
- Email premium si configuré → Mailhog en démo.  
- Autres canaux via panneaux output rules.

**DoD « validé »** = événement + preuves + alerte persistée + mail si configuré + capture UI — pas seulement un log MQTT.

---

## 4. Zones & behaviors (le langage commun des 3 acteurs)

Sans zones correctement typées dans ZoneEditor, **rien** de routier Gemini/Frigate ne marche.

Behaviors critiques (non exhaustif) :

| Behavior zone | Rôle |
|---------------|------|
| `traffic_light_color` | ROI feu — HSV local classifie rouge/vert/ambre |
| `red_light_observation` | Zone où un véhicule « en infraction potentielle » est observé |
| `speed_measurement` | Zone Frigate avec distances → estimated speed |
| `driver_cabin` / `phone_use` / `seatbelt` | Zones cabine → crops Gemini |
| `plate_ocr` | Zone plaque |
| Lignes `line_cross` | Comptage / franchissement |

Compilation Frigate : noms `cv_zone_<uuid>` — le bridge résout via `parse_zone_uuid`.

---

## 5. Catalogue complet des règles (54 templates) — matrice d’honnêteté

Source : `docs/rule-honesty-matrix.md` (générée, ne pas éditer à la main).

**Légende** : 🟢 réel (chemin moteur défaut) · 🟡 partiel (calibration / OCR / Gemini / heuristique).

### 5.1 behavior
| Règle | Statut | Mécanisme typique |
|-------|--------|-------------------|
| Densité foule élevée | 🟢 | Analytics densité / `scene_density_high` |
| Nombre véhicules élevé | 🟢 | Seuil comptage véhicules |
| Personne immobile prolongée | 🟢 | Track dwell / `person_stopped` |
| Seuil foule atteint | 🟢 | `crowd_count_threshold` |
| Véhicule arrêté | 🟢 | `vehicle_stopped` |

### 5.2 composite
| Règle | Statut | Mécanisme |
|-------|--------|-----------|
| Vol suspect (composite) | 🟢 | Composition de plusieurs signaux |

### 5.3 identity (souvent 🟡)
| Règle | Statut | Acteurs |
|-------|--------|---------|
| Corrélation identité | 🟡 | Face + plaque simultanés |
| Personne liste noire | 🟡 | InsightFace et/ou Gemini |
| Plaque autorisée / bloquée / inconnue / non enregistrée / récurrente / détectée | 🟡 | PaddleOCR / Gemini OCR + listes |
| Visage détecté / inconnu / liste de surveillance | 🟡 | InsightFace et/ou Frigate person→Gemini |

### 5.4 industrial
| Règle | Statut |
|-------|--------|
| Intrusion site industriel | 🟢 |

### 5.5 objects
| Règle | Statut | Note |
|-------|--------|------|
| Objet abandonné | 🟡 | Distinct de `object_appeared` |
| Objet retiré | 🟢 | `object_removed` |

### 5.6 presence
| Règle | Statut |
|-------|--------|
| Absence prolongée dans une zone | 🟢 |
| Disparition d'objet | 🟢 |
| Présence dans une zone | 🟢 |

### 5.7 quality
| Règle | Statut | event_type |
|-------|--------|------------|
| Vidéo floue | 🟢 | `video_blur` |
| Vidéo sombre | 🟢 | `video_darkness` |

### 5.8 road-enforcement (cœur démo + Gemini)
| Règle | Statut | Acteurs |
|-------|--------|---------|
| Ceinture de sécurité | 🟡 | Frigate cabin zone → Gemini `seatbelt_violation` |
| Embouteillage | 🟢 | Analytics trafic |
| Excès de vitesse | 🟡 | Frigate speed estimate + limite zone **ou** calibration locale |
| Feu rouge | 🟡 | HSV + (bridge) Gemini `red_light_violation` |
| Franchissement ligne continue | 🟢 | Géométrie ligne |
| Pipeline voiture → plaque + vitesse | 🟡 | Multi-étapes ANPR + speed |
| Plaque détectée (OCR) | 🟡 | Gemini OCR / PaddleOCR |
| Téléphone au volant | 🟡 | Frigate cabin → Gemini `phone_use_violation` |

### 5.9 security
| Règle | Statut |
|-------|--------|
| Flânerie près entrée | 🟢 |
| Intrusion hors horaires | 🟢 |
| Intrusion zone interdite | 🟢 |
| Plusieurs personnes, un véhicule | 🟢 |
| Proximité personne-véhicule | 🟢 |

### 5.10 spatial
| Règle | Statut | event_type typique |
|-------|--------|--------------------|
| Comptage ensemble (N-sur-M / OU) | 🟢 | agrégats |
| Entrée / sortie zone | 🟢 | `zone_enter` / `zone_exit` |
| Franchissement ligne / bidirectionnel | 🟢 | `line_cross` |
| Intrusion périmétrique | 🟢 | `perimeter_breach` |
| Présence multi-zones | 🟢 | |
| Sortie non autorisée | 🟢 | `unauthorized_exit` |

### 5.11 speed / time / traffic
| Règle | Statut | Note |
|-------|--------|------|
| Arrêt brusque | 🟡 | calibration |
| Dépassement temps / loitering | 🟢 | `dwell_time_exceeded` / `loitering` |
| Piéton en zone véhicules | 🟢 | |
| Stationnement illégal | 🟢 | |
| Véhicule trop lent | 🟡 | `speed_below_minimum` + calibration |

### 5.12 `event_type` UI (frontend honesty)

Fichier : `frontend/src/lib/conditionValueOptions.ts`.

Tags honnêteté explicités :

| event_type | Honesty |
|------------|---------|
| `zone_enter`, `zone_exit`, `line_cross`, `loitering`, `dwell_time_exceeded`, `speeding`, `object_abandoned` | `emitted` |
| `red_light_violation`, `seatbelt_violation`, `phone_use_violation`, faces Gemini | `requires_external` |
| plaques | `requires_ocr` |
| `face_recognized` | `requires_face` |
| tout le reste non listé | `heuristic_partial` (défaut) |

Labels FR additionnels dans `frontend/src/i18n/fr.json` → `rules.events.*` (ex. `running`, `wrong_way`, `falling`, `fighting`, `crowd_panic`, `phone_driving` alias UI, etc.).

**[A.4]** : pas de `supported: true` silencieux sur une heuristique fragile sans badge.

---

## 6. Les 5 règles démo — anatomie complète

Seed : `backend/cmd/seed-demo-rules/main.go`.

| Alias démo | Nom | event_type | Déclencheur principal |
|------------|-----|------------|------------------------|
| feu | Démo · Feu rouge | `red_light_violation` | Bridge + Gemini (si VLM bridge) |
| comptage | Démo · Comptage véhicules | `line_cross` | Frigate / analytics ligne |
| vitesse | Démo · Excès de vitesse | `speeding` | `FRIGATE_SPEED_BRIDGE` |
| téléphone | Démo · Téléphone au volant | `phone_use_violation` | Cabin Frigate → Gemini |
| ceinture | Démo · Non-port ceinture | `seatbelt_violation` | Cabin Frigate → Gemini (`Zone_bbox2`) |

> Phase A produit exige **5/5** preuves, jamais « vitesse seule ». Le run documenté ci-dessous a volontairement rejoué un sous-ensemble 4-rules séquentiel (comptage→vitesse→ceinture→feu) + téléphone souvent actif en parallèle sur la même cam cabine.

### 6.1 Comptage (`line_cross`)

1. Ligne définie ZoneEditor.  
2. Frigate / pipeline détecte franchissement.  
3. Event `line_cross` → règle match → alerte.  
4. Preuves selon politique (souvent plus légères que routier).  

**Résultat 1-hit payant** : **PASS** stable.

### 6.2 Vitesse (`speeding`)

Code bridge (extrait) :

```663:704:ai-engine/src/citevision_ai/frigate_bridge/bridge.py
    def _maybe_speed(...):
        limit = self._speed_limit(zinfo)
        ...
        # average_estimated_speed / current_estimated_speed
        if speed is None:
            self._stats["speed_no_estimate"] += 1
            return
        if speed < limit:
            self._stats["speed_below_limit"] += 1
            return
        # else emit speeding with frigate_event_id + bbox
```

**Pas Gemini.** Échec 1-hit = surtout « sous la limite pendant la fenêtre », pas « API down ».

Compteurs observés (fin learn-rerun) :

- `speed_below_limit ≈ 128`  
- `speed_emitted ≈ 16` (hors fenêtre 1-hit dédiée)  
- 1-hit isolé vitesse : `RESULT: FAIL` (0 alert pendant max ~720 s)  
- Export gallery plus tard : 1 hit vitesse `partial` avec `bbox_source=frigate_mqtt`, `capture_source=frigate_track`

### 6.3 Ceinture / téléphone (cabin Gemini)

1. Véhicule (ou person) entre zone cabin.  
2. Snapshot/crop Frigate (mode `vehicle_bbox`).  
3. Queue VLM, prompt fail-closed.  
4. `should_emit` → publish event → règle → evidence.

Prompts (esprit) : violation=true **seulement** si clair ; sinon `unclear`.

Observations run payant :

```json
"vlm_queue": {
  "enqueued": 129,
  "dropped_full": 93,
  "completed": 127,
  "emitted": 0,
  "rejected": 127,
  "unclear": 127,
  "rate_limited": 0
}
```

Rejects récents typiques :

```json
{ "kind": "vlm_reject", "rule": "seatbelt_violation", "violation": false, "visible": false }
{ "kind": "vlm_reject", "rule": "phone_use_violation", "violation": false, "visible": false }
```

Interprétation : **Gemini répond**, facturation OK, mais **ne voit pas assez clairement** le conducteur/ceinture/téléphone sur le crop → fail-closed → 0 alerte. Ce n’est pas un silence d’API.

### 6.4 Feu rouge — chemin actuel (bridge)

#### Gate HSV (local)

```127:143:ai-engine/src/citevision_ai/road_enforcement/traffic_light.py
    def bridge_gate_state(self, camera_id: str) -> str:
        """Require stable majority AND current-frame raw both red."""
        stable = str(self._stable_state.get(camera_id) or "unknown")
        raw = str(self._raw_state.get(camera_id) or "unknown")
        if stable == "red" and raw == "red":
            return "red"
        ...
```

#### Enqueue Gemini seulement si gate rouge

```415:447:ai-engine/src/citevision_ai/frigate_bridge/bridge.py
        light_state = str(self._light_state(camera_id) or "unknown").lower()
        if light_state == "unknown":
            self._stats["red_light_skipped_unknown"] += 1
            return
        if light_state != "red":
            self._stats["red_light_skipped_not_red"] += 1
            return
        if self._dedupe(f"red:{event_id}:{rule}", ttl=8.0):
            return
```

#### Prompt Gemini feu

```148:158:ai-engine/src/citevision_ai/vlm/gemini_client.py
    "red_light_violation": (
        "... decide if the visible signal is RED and a vehicle is (or was) crossing against it. "
        "Set violation=true only if you are confident the light is red AND a vehicle is committing "
        "or has clearly crossed on red. "
        "If unclear, violation=false and signals must include \"unclear\"."
    ),
```

#### Compteurs 1-hit feu (resume Pro)

```
frigate_bridge_red_light_enqueued 6
frigate_bridge_red_light_skipped_not_red 45
vlm_queue_emitted 0
RESULT: Démo · Feu rouge: FAIL
```

HSV post-seq : caméra feu souvent `"green"`.

---

## 7. Pourquoi le feu rouge « laisse passer » alors que vous voyez rouge + voiture

C’est **la** question la plus importante. Réponse détaillée et réaliste.

### 7.1 Ce que vous observez (humain)

- Une zone feu devient rouge parfois.  
- Ensuite au moins une voiture traverse la zone d’observation.  
- Donc « évidemment » il devrait y avoir 1-hit.

### 7.2 Ce que la machine fait aujourd’hui (avec bridge)

Elle exige **la conjonction temporelle machine** de plusieurs conditions, plus strictes que l’œil humain :

| # | Condition machine | Effet si faux |
|---|-------------------|---------------|
| A | Frigate publie un event véhicule **avec** zone `red_light_observation` active | Pas d’appel `_maybe_red_light` |
| B | HSV `bridge_gate_state` = **red** (stable **ET** raw) | `skipped_not_red` (45 fois vs 6 enqueue) |
| C | Dedupe 8 s ne bloque pas | Skip silencieux |
| D | Snapshot JPEG Frigate OK | `red_light_snapshot_fail` |
| E | Gemini `violation=true`, `visible=true`, conf ≥ min, pas `unclear` | reject / unclear |
| F | Rules-engine match + evidence path | sinon pas d’alerte « finale » |

**Vous pouvez voir A humainement vrai pendant que B machine est faux** (HSV dit encore green/amber/unknown, ou raw déjà green alors que stable sticky red — d’où la double contrainte anti-sticky).  
Ou B vrai une demi-seconde, mais le MQTT zone observation arrive **après** le vert.  
Ou A+B vrais, Gemini reçoit un crop où le feu est petit/flou → `visible=false` / `unclear`.

### 7.3 Pourquoi « l’IA locale seule » semblait mieux marcher

Parce qu’**avant / sans bridge**, `TrafficLightAnalyzer` pouvait **émettre directement** `red_light_violation` via synergie HSV + track dans observation (`detection_method: zone_traffic_light_synergy`), sans juge Gemini fail-closed.

Avec `FRIGATE_VLM_BRIDGE=1` :

```text
state_only=True  →  plus d’emit local
Gemini only      →  emit seulement si jugement clair
```

Donc le système actuel **n’est pas** « Frigate + local + Gemini à fond en synergie ».  
C’est plutôt : **local = thermomètre couleur**, **Frigate = détecteur véhicule/zone**, **Gemini = juge unique d’émission** (très conservateur).

Votre intuition produit (« les 3 doivent travailler à fond ») **n’est pas encore l’architecture runtime**. C’est exactement l’écart à re-designer (section 11).

### 7.4 Analogie simple

Local seul = policier qui verbalise dès qu’il croit voir rouge + voiture.  
Bridge actuel = policier qui note la couleur, envoie une photo au juge distant, et **n’écrit le PV que si le juge est certain**.  
Le juge a dit 100+ fois « photo pas claire » → 0 PV.  
Ce n’est pas que « personne n’a vu la voiture » : c’est que **le PV est interdit sans certitude Gemini**.

---

## 8. Déroulé du test Gemini payant + observations

### 8.1 Objectif du plan

Configurer clé payante → smoke health → séquentiel 1-hit comptage→vitesse→ceinture→feu → si FAIL replay isolé → export gallery → rappeler rotation de clé.

### 8.2 Ce qui a été résolu en amont (historique utile)

| Problème | Remédiation |
|----------|-------------|
| Free-tier 429 systématique | Clé billing ; `rate_limited→0` |
| Disque C: plein / I/O WSL | Libération espace |
| Cabin YOLO→Gemini vs Frigate-only | Cabin Frigate-only (`cabin_source=frigate`) |
| Bbox `ia_overlay` au lieu de Frigate | Conservation `bbox_source=frigate_mqtt` sur bridge |
| Gemini flood | intervalle, queue size, process every N, cabin dedupe ~60 s |
| Scripts learn qui se self-kill via `pkill` trop large | Patterns pkill restreints |
| Flash mass `unclear` | Exception plan : bascule **Pro** pour learn-rerun |
| Frigate DOWN mid-rerun | Resume script feu→ceinture→export après healthy |

### 8.3 Smoke

- `gemini_configured=true`  
- modèle Flash puis Pro  
- `cabin_source=frigate`  
- bridges true  
- **`vlm_queue_rate_limited=0`** ← billing OK

### 8.4 Séquentiel (`demo-4rules-20260731T150219Z`)

| Règle | Résultat 1-hit |
|-------|----------------|
| Comptage | PASS |
| Vitesse | FAIL |
| Ceinture | FAIL (unclear) |
| Feu | FAIL (skip HSV + unclear) |

### 8.5 Replay isolé + export (`demo-4rules-20260731T164103Z`)

| Règle | rc | Notes |
|-------|----|-------|
| Vitesse | 1 FAIL | 0 alert fenêtre ; emits speed plus tard |
| Feu | 1 FAIL | enqueue 6, skip_not_red 45, emitted 0 |
| Ceinture | 1 FAIL | cabin_enqueued 123+, emitted 0, visible=false fréquent |

Gallery Windows :

`C:\Users\gheno\citevision\validation-evidence\demo-4rules-20260731T164103Z\index.html`

Logs utiles WSL :

- `~/citevision-v2/logs/paid_learn_resume.out`  
- `~/citevision-v2/logs/blockers-paid-final-20260731T164103Z.json`  
- `~/citevision-v2/logs/rerun-feu-20260731T161251Z.log`

### 8.6 Verdict honnête final

- **Billing Gemini** : OK.  
- **Architecture bridge** : câblée.  
- **1-hit multi-règles** : **non validé**.  
- **Pas** de claim `validate_rule` 5/5 DoD.  
- Cause dominante VLM : **unclear / not visible**, pas quota.  
- Cause dominante feu : **désalignement HSV gate + jugement Gemini**, pas « absence totale de voitures ».  
- Cause dominante vitesse 1-hit : **estimations ≤ limite** pendant la fenêtre.

**Sécurité** : clé chat = compromise → **rotation AI Studio obligatoire**.

---

## 9. Fichiers « carte » pour naviguer le code

| Domaine | Chemins |
|---------|---------|
| Bridge Frigate | `ai-engine/src/citevision_ai/frigate_bridge/bridge.py`, `snapshot.py`, `ids.py` |
| HSV feu | `ai-engine/src/citevision_ai/road_enforcement/traffic_light.py` |
| Legacy HSV ROI | `ai-engine/src/citevision_ai/road_enforcement/detector.py` |
| Pipeline | `ai-engine/src/citevision_ai/pipeline.py` |
| Gemini | `ai-engine/src/citevision_ai/vlm/gemini_client.py`, `queue.py` |
| Config | `ai-engine/src/citevision_ai/config.py` |
| Evidence AI | `ai-engine/src/citevision_ai/evidence/` |
| Compiler Frigate | `backend/internal/frigate/compiler.go` |
| MQTT backend | `backend/internal/mqtt/subscriber.go` |
| Seed démo | `backend/cmd/seed-demo-rules/main.go` |
| Honesty UI | `frontend/src/lib/conditionValueOptions.ts` |
| Matrice | `docs/rule-honesty-matrix.md` |
| Scripts 1-hit | `scripts/_tmp_demo_4rules_sequential.sh`, `_tmp_rerun_one_rule.sh`, `_observe_1hit_blockers.py`, `_validate_rule_frigate_1hit.py` |

---

## 10. Observabilité : quels compteurs lire

`GET /health` / `/debug/rule-blockers` :

| Compteur | Signification |
|----------|---------------|
| `vlm_queue_rate_limited` | Quota / backoff |
| `vlm_queue_unclear` / `rejected` | Gemini fail-closed |
| `vlm_queue_emitted` | Jugements positifs émis |
| `frigate_bridge_red_light_skipped_not_red` | HSV dit pas rouge |
| `frigate_bridge_red_light_enqueued` | Candidats envoyés à Gemini |
| `frigate_bridge_cabin_enqueued` | Crops cabine |
| `frigate_bridge_speed_below_limit` | Vitesse vue mais sous seuil |
| `frigate_bridge_speed_emitted` | Speeding émis |
| `dropped_full` | Queue Gemini saturée (perd des chances) |
| `hsv_light_states` | Dernier état par caméra |

---

## 11. Propositions de re-orchestration « 3 acteurs à fond » (à trancher)

> Ces propositions sont des **options de design**. Aucune n’est appliquée par ce document.  
> Objectif déclaré utilisateur : **0 raté** sur règles actives, synergie Frigate + local + Gemini, y compris scène pleine périodique.

### 11.1 Modèle A — « Local emit + Gemini confirm async » (hybride)

```text
HSV+track local émet red_light_violation (candidate, severity=pending)
    → alerte UI « provisional »
Gemini confirme/infirme sous N secondes
    → promote complete / demote cancelled
Evidence clip Frigate attaché dans les deux cas si possible
```

**Pour** : retrouve le comportement « local qui catch ».  
**Contre** : risque fausses alertes provisoires ; contredit R.2/A.9 si on présente provisional comme final.

Snippet conceptuel :

```python
# ILLUSTRATIF — pas upstream
if not state_only and local_red and vehicle_in_obs:
    emit_event(type="red_light_violation", metadata={"pending_gemini": True})
if bridge and local_red and vehicle_in_obs:
    enqueue_gemini(confirm_job)
# on Gemini verdict:
#   violation True  -> clear pending_gemini, evidence_status path
#   unclear         -> keep provisional OR cancel according to policy knob
```

### 11.2 Modèle B — « Multi-evidence Gemini » (votre idée scène 3 s)

Toutes les 3 s pendant rouge stable :

1. Snapshot **full scene** Frigate.  
2. Crop feu (`traffic_light_color`).  
3. Crop(s) véhicules dans `red_light_observation`.  
4. Un job Gemini multi-image : « feu rouge ? véhicule dans zone obs ? »

```python
# ILLUSTRATIF
def periodic_red_light_audit(camera_id):
    if hsv.bridge_gate_state(camera_id) != "red":
        return
    scene = frigate_snapshot_full(camera_id)
    light = crop_polygon(scene, light_poly)
    vehicles = list_tracks_in_behavior(camera_id, "red_light_observation")
    for v in vehicles:
        enqueue(VlmJob(images=[scene, light, crop(v)], rule="red_light_violation",
                       extra_context="multi_view_audit every_3s"))
```

**Pour** : aligne l’intuition humaine ; plus de chances de clarté.  
**Contre** : coût $ ; latence ; toujours fail-closed si unclear — « 0 raté » **absolu** est mathématiquement incompatible avec fail-closed strict sauf si on accepte aussi plus de faux positifs.

### 11.3 Modèle C — « Two-man rule »

- Vote 1 : local HSV+géométrie → score L.  
- Vote 2 : Frigate zone dwell pendant rouge → score F.  
- Vote 3 : Gemini → score G.  
- Emit si `(L∧F) ∨ (G∧F) ∨ (L∧G)` selon matrice configurable.

### 11.4 Modèle D — « Gemini primary, HSV soft-gate only »

Assouplir B : enqueue Gemini si `raw==red` **OU** `stable==red` **OU** même si green mais « transition récente < 2 s » (véhicule déjà engagé).  
Réduit `skipped_not_red` excessif.

```python
# ILLUSTRATIF soft-gate
def soft_red(camera_id) -> bool:
    st = hsv.bridge_gate_state(camera_id)
    if st == "red":
        return True
    if recent_red_until.get(camera_id, 0) > time.time():
        return True  # grace after red→green
    return False
```

### 11.5 Modèle E — « Local autoritaire hors Gemini »

Kill-switch : si Gemini unclear rate > seuil, **fallback emit local** (badge honesty `heuristic_partial` explicite).

### 11.6 Ceinture / téléphone

- Multi-frame burst (5 crops / 1 s) → Gemini majority.  
- Full cabin + zoom driver.  
- Prompt séparé « is driver visible? » puis « seatbelt? ».  
- Si `visible=false` chronique → alerter **qualité caméra** (règle quality), pas forger ceinture.

### 11.7 Vitesse

- Ne pas dépendre du seul exit zone : emit aussi sur max speed in-zone.  
- Aligner `speed_limit_kmh` zone avec réalité vidéo démo.  
- Micro-test : histogramme des estimates Frigate vs limite.

---

## 12. Questions pertinentes à répondre AVANT le prochain 1-hit

### 12.1 Produit / politique de vérité

1. Une alerte **provisoire** (local) affichée avant Gemini est-elle acceptable ?  
2. Préfère-t-on **0 faux positif** (fail-closed actuel) ou **0 faux négatif** (votre « 0 raté ») ? Ces deux objectifs sont en tension.  
3. Pour le feu, Gemini doit-il **confirmer** une décision locale, ou **décider seul** ?  
4. Badge UI : si fallback local, doit-on forcer `partial` / `beta` visible ?  
5. L’alerte sans clip complet peut-elle apparaître en UI comme non-finale (`evidence_status=missing`) ?

### 12.2 Feu rouge — géométrie & timing

6. Les polygones `traffic_light_color` et `red_light_observation` sont-ils toujours ceux validés humainement (pas un vieux seed) ?  
7. Sur la vidéo démo, durée typique du rouge ? overlap moyen rouge∩présence véhicule ?  
8. Accepte-t-on une **grâce post-rouge** (véhicule engagé) de N secondes ? Quelle N ?  
9. Faut-il exiger stable∧raw, ou soft-gate ?  
10. Frigate MQTT : la zone observation est-elle `entered` assez tôt, ou seulement `current` tardif ?  
11. Veut-on un audit scène pleine toutes les 3 s **seulement si règle feu enabled** ? Budget $ / jour ?

### 12.3 Gemini

12. Rester Flash payant ou Pro pour routier ? Budget max USD/jour ?  
13. Faut-il baisser `min_confidence` zone behavior_config ? À quelle valeur ?  
14. Prompt feu : juger **séparément** « light_is_red » et « vehicle_in_box » puis AND local ?  
15. Multi-image (scène+feu+véhicule) autorisé malgré coût ?  
16. Que faire de `visible=false` répété : skip, retry autre crop, ou fallback local ?  
17. `dropped_full=93` : augmenter `GEMINI_QUEUE_SIZE` ou réduire enqueue cabin concurrent ?

### 12.4 Ceinture / téléphone

18. La caméra cabine permet-elle réellement de voir la ceinture (résolution, angle) ?  
19. Crop `vehicle_bbox` trop large/étroit ? Essayer `driver_roi` ?  
20. Faut-il séparer les règles téléphone/ceinture sur des fenêtres 1-hit **sans** l’autre enabled (contention queue) ?  
21. Dedupe cabin 60 s trop agressif pour 1-hit ?

### 12.5 Vitesse

22. `speed_limit_kmh` de la zone démo est-il aligné sur les estimates Frigate réels ?  
23. Emit on max-in-zone plutôt que exit-only ?  
24. Pendant 1-hit vitesse, les autres caméras doivent-elles être pausées pour charge Frigate ?

### 12.6 Preuves & DoD

25. 1-hit « PASS » exige-t-il evidence complete + mail, ou seulement event+alert+frigate_track ?  
26. `bbox_source` doit-il être strictement `frigate_mqtt` pour PASS feu/vitesse ?  
27. Plaque manquante (`plate_status=missing`) = FAIL routier ou PASS partiel acceptable en Phase A ?

### 12.7 Orchestration globale

28. Un **RuleOrchestrator** central (state machine par rule_id) est-il souhaité vs bridges dispersés ?  
29. Priorité queue Gemini par règle active (feu > ceinture > face) ?  
30. Faut-il un mode `AGGRESSIVE_DEMO=1` qui active Model B+D uniquement sur cams démo ?

---

## 13. Micro-tests (batterie avant prochain 1-hit)

Chaque micro-test = **une** hypothèse, résultat chiffré, pas de claim global.

### Feu / HSV
1. Loguer 5 min `raw_state` vs `stable_state` vs `bridge_gate_state` (CSV).  
2. Compter overlap frames : `gate==red` ∧ véhicule∈obs.  
3. Relâcher temporairement soft-gate (raw only) — mesurer Δ `enqueued`.  
4. Grace 2 s post-rouge — mesurer Δ enqueue + faux positifs subjectifs.  
5. Forcer enqueue même si green (debug only, flagged) — voir si Gemini dit red (diagnostic crop).  
6. Dump JPEG light ROI quand humain dit rouge / machine dit green.  
7. Comparer emit local `state_only=False` 2 min (sandbox) vs bridge.  
8. Vérifier UUID zones Frigate `zone_miss` logs.  
9. Mesurer latence MQTT entered_zones vs HSV red edge.  
10. Test dedupe ttl 8→2 s.

### Gemini feu
11. Envoyer 20 full-scene manuelles labelées (humain rouge+voiture).  
12. Même set en crop véhicule seul.  
13. Même set multi-image.  
14. Prompt split light/vehicle.  
15. Flash vs Pro sur même set (coût + unclear rate).  
16. min_confidence 0.45→0.30.  
17. Interval 5→2 s pendant rouge only.  
18. Queue size 4→16 ; watch `dropped_full`.

### Ceinture / téléphone
19. Sauver 50 crops rejetés `visible=false` — revue humaine.  
20. Burst 5 frames.  
21. Alternate crop modes.  
22. Disable phone rule pendant test ceinture.  
23. Mesurer taille bbox min vs rejects.  
24. Prompt « driver visible? » seul.  
25. Pro only cabin 10 min — unclear rate.

### Vitesse
26. Histogramme `average_estimated_speed` 15 min.  
27. Comparer à `speed_limit_kmh`.  
28. Emit on max-in-zone prototype.  
29. 1-hit vitesse seul 720 s avec Frigate healthy garanti (pas rebuild mid-window).  
30. Vérifier `edge_distances_m` zone.

### Comptage / régression
31. 1-hit comptage 60 s smoke.  
32. Vérifier qu’activer feu agressif ne casse pas comptage.

### Evidence
33. Pour chaque emit : `capture_source`, `bbox_source`, `evidence_status`.  
34. Clip ready latency p50/p95.  
35. Mailhog presence si policy mail.

### Orchestration
36. Priority queue simulation (replay MQTT dump).  
37. Mode AGGRESSIVE_DEMO shadow (log only, no emit).  
38. Chaos : restart Frigate mid-1hit — recovery time.  
39. Disk margin `df -h /mnt/c` pré-run.  
40. `/debug/rule-blockers` snapshot avant/après chaque micro-test.

### Synergie 3 acteurs (nouveaux)
41. Timer 3 s full-scene pendant rouge — log only.  
42. Local candidate + Gemini confirm — shadow mode.  
43. Vote L∧F sans Gemini — compare recalls.  
44. Vote (L∧F)∨G — shadow.  
45. End-to-end 1-hit feu après choix politique verrouillé.

---

## 14. Exemples de code / logs de référence

### 14.1 Reject VLM (queue)

```155:159:ai-engine/src/citevision_ai/vlm/queue.py
            logger.info(
                "vlm_reject rule=%s violation=%s visible=%s conf=%.2f min=%.2f reason=%s signals=%s err=%s",
                job.rule,
                bool(getattr(verdict, "violation", False)),
                bool(getattr(verdict, "visible", False)),
                ...
            )
```

### 14.2 Extrait log résultat

```text
RESULT: Démo · Feu rouge: FAIL
frigate_bridge_red_light_enqueued 6
frigate_bridge_red_light_skipped_not_red 45
vlm_queue_emitted 0
RESULT: Démo · Non-port ceinture: FAIL
DONE_LEARN vitesse=1 feu=1 ceinture=1
SECURITY: rotate Gemini API key in AI Studio — it was exposed in chat.
```

### 14.3 Blockers JSON (structure)

```json
{
  "vlm_queue": {
    "enqueued": 129,
    "dropped_full": 93,
    "emitted": 0,
    "rejected": 127,
    "unclear": 127,
    "rate_limited": 0
  },
  "frigate_bridge": {
    "cabin_enqueued": 123,
    "red_light_enqueued": 6,
    "red_light_skipped_not_red": 45,
    "speed_emitted": 16,
    "speed_below_limit": 128
  }
}
```

---

## 15. Synthèse pour l’assistant IA suivant

1. **Ne confonds pas** « Gemini payant OK » et « règles 1-hit PASS ».  
2. **Feu** : le local n’émet plus sous bridge ; HSV skip dominant ; Gemini unclear sur le peu d’enqueue. L’œil humain ≠ conjonction machine A∩B∩E.  
3. **Ceinture/téléphone** : volume d’enqueue élevé, `visible=false` / unclear, `dropped_full` élevé → contention + qualité crop.  
4. **Vitesse** : mécanisme vivant hors fenêtre ; 1-hit échoue sur seuil/timing.  
5. **Comptage** : preuve que le socle spatial marche.  
6. Pour viser « 0 raté », il **faut une décision produit** explicite (section 12) puis implémenter un modèle A/B/C/D — le runtime actuel ne le fait pas.  
7. Enchaîner micro-tests 1→45 **avant** un nouveau séquentiel 1-hit marketing.  
8. Toujours rappeler rotation de clé si exposée.  
9. Runtime = WSL `~/citevision-v2`.  
10. Ce fichier Windows est la **mémoire longue** : le mettre à jour après chaque campagne 1-hit.

---

## 16. Annexes chemins Windows utiles

| Artefact | Chemin |
|----------|--------|
| Ce document | `C:\Users\gheno\citevision\docs\HANDOFF-ARCHITECTURE-COMPLETE-1HIT-GEMINI.md` |
| Matrice règles | `C:\Users\gheno\citevision\docs\rule-honesty-matrix.md` |
| Gallery seq | `C:\Users\gheno\citevision\validation-evidence\demo-4rules-20260731T150219Z\` |
| Gallery replay | `C:\Users\gheno\citevision\validation-evidence\demo-4rules-20260731T164103Z\` |
| Socle Cursor | `C:\Users\gheno\citevision\.cursor\rules\citevision-socle.mdc` |

---

*Fin du document — rédigé pour transmission maximale de contexte entre sessions agents.*

---

## 17. Résultats campagne micro-tests 1-45 (20260801T215936Z)

Append-only — runtime WSL `~/citevision-v2`, rapport [`docs/MICROTEST-REPORT-20260801T215936Z.md`](MICROTEST-REPORT-20260801T215936Z.md).

### Synthèse gates

| Gate | Verdict | Notes |
|------|---------|-------|
| A — feu HSV (tests 1-10) | **NO-GO** | `delta_red_light_enqueued=0` sur 90s ; `hsv_gate_debug` vide (caméras TL non résolues dans blockers) |
| B — Q18 cabin dump | **ge50** (auto) | 20 JPEG 90–170 KB → `validation-evidence/cabin-dump-20260801T220229Z/` ; revue humaine recommandée |
| C — Gemini feu (11-18) | **NO-GO** | 10 crops feu → `feu-roi-20260801T220238Z/` ; **HTTP 404** sur toutes requêtes `gemini-2.5-flash` |
| D — comptage (31) | **PASS** | 1-hit comptage rc=0, counter_delta=16 |
| F — 1-hit feu (45) | **FAIL** | 720s, 0 alert ; Frigate 502/500 mid-run ; post-run bridge `red_light_enqueued=8`, `skipped_not_red=35`, `vlm_rejected=8`, `emitted=0` |

### Livrables produits

- Scripts : `scripts/microtest/*` (runner, dumps feu/cabin, gates)
- Code : D1/D2 gate OR+grâce, `hsv_gate_debug`, `FRIGATE_CABIN_DEDUPE_SEC`, flags shadow
- Evidence : cabin-dump (20), feu-roi (10), blockers archivés sous `logs/microtest-*`
- Checklist : `docs/MICROTEST-BATTERY-1HIT-GEMINI.md` (section résultats)

### Blocages identifiés (priorité)

1. **HSV gate debug vide** — spatial configs / cam IDs feu non exposés dans `/debug/rule-blockers` pendant poll → gate A NO-GO malgré enqueue post-test.
2. **Gemini HTTP 404** — modèle ou endpoint API ; vérifier `GEMINI_MODEL` vs modèles disponibles sur la clé payante.
3. **1-hit feu** — enqueue bridge sans émission VLM ni alerte persistée ; aligner fenêtre démo + pré-heal Frigate avant test 45.

**PASS_1HIT feu : non atteint.** Ne pas claim DoD. Rotation clé Gemini si exposée en chat.

---

## 18. Fix blocages micro-test (20260802T000652Z)

Scripts : [`scripts/microtest/_microtest_fix_blockers.sh`](scripts/microtest/_microtest_fix_blockers.sh), [`scripts/microtest/_microtest_raw_hsv_probe.py`](scripts/microtest/_microtest_raw_hsv_probe.py). Rapport : [`docs/microtest-fix-20260802T000652Z/fix-report.md`](docs/microtest-fix-20260802T000652Z/fix-report.md).

### Corrections appliquees

| Bloquant | Action | Resultat |
|----------|--------|----------|
| 1 — Gemini 404 | `patch_env_kv()` ne force plus `gemini-2.5-flash` ; auto-fix vers `gemini-3.1-flash-lite` | generateContent OK, ping yes |
| 2 — hsv_gate_debug vide | `spatial_tl_summary` + `spatial_camera_count` dans `/debug/rule-blockers` | Hors fenetre 1-hit : `spatial_camera_count=0` — verdict `config_routing` |
| 3 — Test 45 | Relance apres fix Gemini + demarrage cam feu via 1-hit | **PASS_1HIT** rc=0 : 1 alert, `frigate_track=1`, `vlm_queue_emitted=1` |

**PASS_1HIT feu : atteint** apres fix modele Gemini. Toujours pas PASS_DoD. Cause racine bloquant 1 : `gemini-2.5-flash` indisponible (404 API nouveaux utilisateurs).

---

## 19. Script apply fixes + 1-hit (20260802T005519Z)

Script : [`scripts/microtest/_microtest_apply_fixes_and_1hit.sh`](scripts/microtest/_microtest_apply_fixes_and_1hit.sh). Rapport : [`docs/microtest-fix-20260802T005519Z/final-fix-report.md`](docs/microtest-fix-20260802T005519Z/final-fix-report.md).

| Etape | Resultat |
|-------|----------|
| A Gemini | deja gemini-3.1-flash-lite |
| B Spatial | spatial_ok, cam feu 8ed20433, zones TL DB OK |
| C Spatial fix | SKIP (MICROTEST_AUTO_YES=1) |
| D Reprobe | warm-start OK, bridge_red_enqueued=7 |
| E 1-hit | PASS_1HIT TEST45_RC=0, vlm_emitted=1 |

Note : spatial_camera_count=0 au repos = normal sans worker AI ; MQTT Frigate independant. Warm-start via microtest_warm_feu_camera() avant probe/1-hit.

---

## 20. Stabilite 1-hit feu x3 (20260802T011746Z)

Script : [`scripts/microtest/_microtest_1hit_feu_stability_x3.sh`](scripts/microtest/_microtest_1hit_feu_stability_x3.sh). Rapport : [`docs/microtest-stability-20260802T011746Z/stability-summary.md`](docs/microtest-stability-20260802T011746Z/stability-summary.md).

| Run | TEST45_RC | vlm_emitted | skipped_not_red | align_delta_ms | Verdict |
|-----|-----------|-------------|-----------------|----------------|---------|
| 1 | 0 | 1 | 13 | 2731 | PASS_1HIT |
| 2 | 0 | 1 | 48 | 3768 | PASS_1HIT |
| 3 | 0 | 1 | 30 | 1392 | PASS_1HIT |

**3/3 PASS_1HIT** — stabilite confirmee (pas un coup de chance isole). Toujours pas PASS_DoD.

---

## 21. Document synergie 3 acteurs (20260802)

Document detaille architecture 3 acteurs, campagne 1–45, synergie LF_OR_G, questions Q46–Q60, batterie 46–90+ :

[`docs/HANDOFF-SYNERGIE-3-ACTEURS.md`](HANDOFF-SYNERGIE-3-ACTEURS.md)

Implementations phase 2 : `RED_LIGHT_VOTE_MODE=lf_or_g`, `FRIGATE_VLM_BRIDGE_CROP_MODE=driver_roi`, scripts `_microtest_synergy.sh` et `_microtest_cabin_crop_compare.sh`.
