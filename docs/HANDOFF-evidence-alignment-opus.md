# Passation Opus — alignement preuves vitesse (CitéVision Phase A)

**Destinataire :** agent Opus 4.8 (ou équivalent) reprenant le chantier preuves.  
**Date de rédaction :** 2026-07-08.  
**Contexte critique :** le demandeur **n’aura plus accès à la caméra RTSP `192.168.1.108`**. Toute validation runtime doit donc s’appuyer sur **vidéos fichier**, **tests automatisés**, **MinIO/DB**, et éventuellement une autre caméra RTSP — **jamais** sur l’hypothèse que la 108 est joignable.

**Architecture de vérité (socle, non négociable) :** `zone → IA → règle → preuve`. Une alerte « validée » exige : événement → preuves (clip ~6 s, 2 images, plaque si routier) → alerte persistée → mail si configuré.

---

## 1. Résumé exécutif

### Symptôme utilisateur

Sur les alertes **excès de vitesse** (`speeding`), les preuves stockées (MinIO + `evidence_snapshot` en DB) montrent régulièrement :

| Rôle UI | Attendu | Observé (cas ratés) |
|---------|---------|---------------------|
| **Vue d'ensemble** (`scene`) | Véhicule dans le cadre bleu | Cadre bleu sur **route vide** ; véhicule ailleurs dans l’image ou absent |
| **Cible détectée** (`subject`) | Zoom sur le véhicule | Crop sur **asphalte / béton** sans cible |
| **Plaque** (`plate`) | Crop arrière lisible | Bande noire + texture route ; plaque inexploitable |
| **Clip** (`clip`) | 6 s fluides centrés sur l’infraction | Parfois OK en segment mode ; parfois 262 o / slideshow / décalé |

### Décision récente (2026-07-08)

Le **mode segments 10 s** (Phase A expérimentale, caméra 108 uniquement) a été **abandonné et désactivé** :

- `segment_mode_camera_ids` remis à `""` dans `ai-engine/src/citevision_ai/config.py`
- Caméra 108 repassée en **RTSP live continu** (`RTSPWorker`, pas de trou de ~5 s entre cycles)
- Le code segment **reste dans le dépôt** mais ne doit **pas** être réactivé sans accord explicite

**Le problème de preuves ratées n’est donc PAS clos** — il doit être résolu en **mode live** (+ nettoyage des preuves historiques ratées en stockage).

---

## 2. Identifiants et environnement

### IDs (résolus live via API/DB — ne pas hardcoder en prod, OK pour debug)

| Ressource | UUID / valeur |
|-----------|----------------|
| Caméra démo RTSP « 108 » | `37c7d7fa-12dc-450c-8c4b-ab63ed43a819` |
| Org démo (validate_segment) | `74d51ead-97a7-4e41-a488-503a9b90c466` |
| Org alternatif (scripts diag) | `e312f375-7442-4089-8022-ed232abc09e8` |
| RTSP 108 (historique) | `rtsp://admin:***@192.168.1.108:554/live` — **indisponible pour le successeur** |

### Environnement runtime

| Emplacement | Rôle |
|-------------|------|
| `C:\Users\gheno\citevision` | Édition Windows |
| `~/citevision-v2` (WSL) | **Source de vérité runtime** — sync obligatoire avant livraison |
| AI Engine | `http://127.0.0.1:8001` |
| Backend API | `http://127.0.0.1:8081` |
| Postgres | docker `citevision-v2-postgres` |
| MinIO | bucket `citevision-evidence` (via `.env`) |
| Mailhog | tests mail premium si configuré |

### Sync & restart

```bash
# Windows → WSL
bash /mnt/c/Users/gheno/citevision/scripts/sync-all-targets.sh

# Restart AI (tuer TOUS les uvicorn citevision_ai — un seul processus sur 8001)
python3 ~/citevision-v2/scripts/_restart_ai.py

# Vérifier qu’un seul uvicorn écoute
pgrep -af uvicorn
curl -s http://127.0.0.1:8001/health | jq .
```

### Contraintes socle (`.cursor/rules/citevision-socle.mdc`)

- Pas de zones hardcodées ; géométrie via ZoneEditor / DB uniquement
- Pas de boucle « vitesse seule » — les 5 règles démo ont la même exigence preuve
- « Validé » = preuves complètes, pas des logs MQTT
- GPU prioritaire ; pas de code superflu hors chaîne zone→IA→règle→preuve
- Scripts `_fix_*` gelés — diagnostic lecture seule

---

## 3. Chaîne bout-en-bout (live mode — état cible)

```
RTSP read loop (RTSPWorker._loop)
  ├─ buffer_fn → evidence.push_frame @ RING_FPS (12 Hz) — indépendant du GPU
  └─ queue → infer thread → pipeline.process_frame @ ~8 Hz (priority zones)

pipeline.process_frame
  ├─ YOLO + ByteTrack
  ├─ zone_speed.process_frame → événement speeding + bbox + bbox_ts + (optionnel segment_bbox_frame_index)
  ├─ enrichissement bbox (pick_best_bbox_with_ts + historique) — LIVE ONLY
  └─ _publish_event_with_evidence
        ├─ gate.match_policy (règle active + dedup 60 s)
        └─ evidence.attach_evidence_async(frame, frame_ts=frame_wall_ts)

EvidenceCaptureService (thread background)
  ├─ _resolve_capture_frame : frame live si |bbox_ts - frame_ts| ≤ 0.15 s, sinon ring buffer @ bbox_ts
  ├─ capture_images_from_policy : scene (bbox dessinée), subject (crop sans bbox), plate (rear band)
  ├─ ring buffer.export_clip_mp4(center_ts=bbox_ts)
  └─ EvidenceUploader → POST /api/v1/internal/orgs/{org}/evidence/upload → MinIO + snapshot DB
```

### Horloges — point de confusion majeur

| Mode | `bbox_ts` | Ring buffer `ts` | Compatible ? |
|------|-----------|------------------|--------------|
| **Live** | `time.time()` via `frame_wall_ts` | `time.time()` dans `FrameRingBuffer.maybe_push` | **Oui** si même process |
| **Segment (désactivé)** | `segment_start_wall + video_pts` | **Non alimenté** (segment cameras skip push_frame) | **Non** — source de bugs |

En segment mode, le ring buffer était **volontairement désactivé** (`main.py` : pas de `push_frame` si caméra segment). Toute preuve passait par `capture_from_segment` + MP4 temporaire — voir section 5.

---

## 4. Symptômes détaillés (captures utilisateur)

Descriptions des cas observés (2026-07-08) :

1. **Vue d'ensemble** : bbox bleue au centre de la route ; moto visible **à gauche** au loin → bbox et contenu décorrélés.
2. **Cible détectée** : crop route vide / bord de trottoir — aucun véhicule.
3. **Plaque** : JPEG quasi entièrement noir avec petite bande de bitume — crop `plate_rear` sur mauvaise zone.
4. **Segment mode (avant rollback)** : parfois véhicule visible dans subject mais bbox UI décalée ; EOF flush produisait bbox historique + frame fin de segment.

Ces images prouvent que le problème n’est pas **uniquement** UI : les **JPEG uploadés MinIO** sont mauvais.

---

## 5. Mode segments 10 s — ce qui a été tenté et pourquoi ça a échoué

### Design (Phase A — cam 108 seule)

Fichiers principaux :

- `ai-engine/src/citevision_ai/ingest/segment_cycle_worker.py` — machine RECORD 10 s → PROCESS ≤ 5 s → boucle
- `ai-engine/src/citevision_ai/ingest/timeline.py` — `FrameTimeline`, `SegmentCaptureContext`
- `ai-engine/src/citevision_ai/evidence/segment_align.py` — seek frame par index/PTS
- `ai-engine/src/citevision_ai/evidence/segment_replay_cache.py` — cache JPEG par frame index
- `ai-engine/src/citevision_ai/pipeline.py` — `process_segment_eof`, branche `segment_ctx`
- `scripts/validate_segment_mode_108.py` — validation ffprobe + MinIO

Config (`config.py`) — **désactivée** :

```python
segment_mode_camera_ids: str = ""  # était la UUID cam 108
segment_record_sec: float = 10.0
segment_process_budget_sec: float = 5.0
segment_ingest_fps: float = 12.0
```

### Cycle segment

1. **RECORD** : OpenCV écrit MP4 temp (~12 fps, ~10 s)
2. **PROCESS** : replay offline frame par frame → `process_fn` avec `timeline` + `segment_ctx`
3. Copie `{segment}.evidence.mp4` pour ffmpeg pendant replay
4. **EOF flush** : `zone_speed.process_frame(tracks=[])` → `track_lost` pour véhicules encore « inside »
5. Suppression MP4 — **capture preuve synchrone obligatoire** avant delete

### Bugs racines identifiés (segment)

| # | Bug | Effet |
|---|-----|-------|
| S1 | **Trou ~5 s** entre fin PROCESS et prochain RECORD | Perte d’événements / passages non vus |
| S2 | **Double horloge** : bbox_ts segment vs ring buffer live | Alignement impossible via buffer |
| S3 | **OpenCV seek** (`CAP_PROP_POS_FRAMES` / `POS_MSEC`) sur H.264 | Frame relue ≠ frame replay |
| S4 | Pipeline **écrasait** bbox/`bbox_ts` zone_speed par bbox frame courante | bbox sortie de zone + frame EOF |
| S5 | `_best_bbox` mise à jour **hors zone** (avant fix) | bbox sur route vide « meilleure score » |
| S6 | `resolve_segment_capture_frame` retournait la frame replay courante même si `segment_bbox_frame_index` différent | Crop vide |
| S7 | Processus uvicorn **fantôme** sur 8001 | Ancien code servait les requêtes → clips 262 o malgré fix |
| S8 | Frontend dessinait bbox sur **subject** au lieu de **scene** | Cadre bleu mal positionné sur crop zoomé (corrigé) |

### Correctifs segment appliqués (conservés dans le code)

- Conserver `bbox` / `segment_bbox_frame_index` de `zone_speed._best_bbox` (ne pas écraser en segment)
- `SegmentReplayCache` — frame exacte par index sans re-seek
- `_best_bbox` uniquement quand véhicule **inside** zone (`zone_speed.py`)
- `bbox_region_has_content()` — rejet texture plate dans bbox (`capture.py`)
- Scene = bbox dessinée ; subject = crop sans bbox (`capture.py` + `EvidenceViewer.tsx`)
- `segment_pts_from_frame_index` pour PTS clip

**Malgré tout**, preuves encore ratées → **rollback live** (2026-07-08).

### Réactivation segment (interdit sans accord)

Ne pas remplir `SEGMENT_MODE_CAMERA_IDS` sans validation humaine. Script historique : `scripts/_force_segment_mode_108.py`. Rollback live : `scripts/restore_live_mode_108.py`.

---

## 6. Mode live — mécanismes actuels et lacunes probables

### Ce qui fonctionne (théorie)

1. **Ring buffer 12 s @ 12 fps** alimenté sur **read loop RTSP** (`rtsp_worker.py` → `evidence_buffer_fn` → `push_frame`)
2. **`bbox_ts`** porté par `zone_speed._finalize_crossing` depuis `_best_bbox` (timestamp frame où bbox optimale observée **dans la zone**)
3. **`_resolve_capture_frame`** (`service.py`) :
   - Si `|bbox_ts - frame_ts| ≤ 0.15 s` → frame inference en main
   - Sinon → `buf.get_frame_at_ts(bbox_ts)` (pas `event_ts` émission)
4. **Clip** centré sur `bbox_ts` via `export_clip_mp4(center_ts=...)`
5. **UI** : bbox overlay sur **Vue d'ensemble** uniquement

### Lacunes probables (à investiguer / corriger)

| # | Hypothèse | Piste |
|---|-----------|-------|
| L1 | **`attach_evidence_async`** — capture différée ; ring buffer peut avoir expiré la frame si `bbox_ts` vieux de >12 s | Capture **synchrone** sur le thread inference pour `speeding`, ou agrandir `RING_SECONDS` |
| L2 | **`pick_best_bbox_with_ts`** dans pipeline (live) remplace bbox zone_speed par historique / frame courante | Pour `speeding`, **faire confiance** à `evt["bbox"]` + `evt["bbox_ts"]` issus de `_best_bbox` |
| L3 | **`frame_ts=frame_wall_ts`** passé à async = frame **émission**, pas frame **bbox** | Passer `frame_ts=evt["bbox_ts"]` |
| L4 | Ring buffer JPEG **lossy** — véhicule flou / décalé vs frame BGR inference | Stocker BGR dans buffer pour preuves (coût mémoire) ou JPEG qualité 95 |
| L5 | **`bbox_region_has_content` non appliqué en live** | Avant upload live : si ROI vide → retry frames voisines dans buffer ; sinon `evidence_status=partial` **sans** faux positif « complete » |
| L6 | **Inférence async** : `frame_wall_ts` au moment process ≠ timestamp ring frame la plus proche | Unifier : pousser dans ring buffer avec **même ts** que `frame_wall_ts` pipeline (aujourd’hui read loop utilise `time.time()` indépendamment) |
| L7 | **Preuves segment historiques** en DB avec `capture_source=segment` | `capture_retroactive` tente re-read MP4 **supprimé** → partial/failed permanent |
| L8 | **Upload réussi mais snapshot incomplet** côté backend | Tracer `InternalEvidenceUpload` + `evidence_snapshot` JSON |
| L9 | **Limite vitesse 1 km/h** (test Phase A) | Remettre 30 km/h zone + règle après validation — fausse cadence d’alertes |

### Fichiers clés live

```
ai-engine/src/citevision_ai/ingest/rtsp_worker.py       # read vs infer decoupling + buffer_fn
ai-engine/src/citevision_ai/pipeline.py                 # L721-777 bbox enrichment, L866 attach_evidence_async
ai-engine/src/citevision_ai/analytics/zone_speed.py    # _best_bbox, _finalize_crossing, bbox_ts
ai-engine/src/citevision_ai/evidence/service.py         # _resolve_capture_frame, _capture_and_attach
ai-engine/src/citevision_ai/evidence/buffer.py          # FrameRingBuffer, export_clip_mp4
ai-engine/src/citevision_ai/evidence/capture.py          # crops, draw_bbox, bbox_region_has_content
ai-engine/src/citevision_ai/evidence/gate.py             # match_policy + dedup
ai-engine/src/citevision_ai/evidence/uploader.py         # POST internal upload
ai-engine/src/citevision_ai/evidence/config.py          # RING_SECONDS=12, RING_FPS=12, TOLERANCE=0.15s
frontend/src/components/evidence/EvidenceViewer.tsx     # affichage scene/subject/plate
backend/internal/evidence/service.go                    # MinIO + URLs API
```

---

## 7. Stockage — preuves ratées existantes

### Où vivent les preuves

- **MinIO** : `orgs/{org_id}/cameras/{camera_id}/events/{event_id}/` — `scene.jpg`, `subject.jpg`, `plate.jpg`, `clip.mp4`
- **Postgres** : `events.evidence_snapshot` (JSON package + metadata), `alerts.evidence_snapshot`
- **Métadonnées** utiles : `capture_source` (`segment` vs absent=live), `segment_bbox_frame_index`, `bbox_ts`, `capture_frame_ts`, `evidence_status`, `missing_roles`

### Scripts audit / purge

| Script | Usage |
|--------|-------|
| `scripts/_diag_event_evidence.py` | Derniers events + présence clip/images |
| `scripts/_list_speed_evidence.py` | Liste preuves speeding |
| `scripts/_disk_evidence_counts.py` | Comptages MinIO |
| `scripts/verify-evidence-quality.sh` | Qualité alerte fixture (bbox, durée clip) |
| `scripts/validate_speed_evidence_chain.py` | Unit tests + smoke |
| `scripts/_purge_evidence.py` | Purge (prudence) |

### Requête SQL type (derniers speeding cam 108)

```sql
SELECT occurred_at,
       evidence_snapshot->'package'->'metadata'->>'capture_source' AS src,
       evidence_snapshot->'package'->'metadata'->>'segment_bbox_frame_index' AS bidx,
       evidence_snapshot->'package'->'metadata'->>'bbox_ts' AS bbox_ts,
       evidence_snapshot->'package'->'metadata'->>'evidence_status' AS status,
       evidence_snapshot->'package'->'metadata'->>'missing_roles' AS missing,
       jsonb_array_length(COALESCE(evidence_snapshot->'package'->'images', '[]'::jsonb)) AS n_imgs,
       (evidence_snapshot->'package'->'clip'->>'duration_sec') AS clip_dur
FROM events
WHERE camera_id = '37c7d7fa-12dc-450c-8c4b-ab63ed43a819'
  AND event_type = 'speeding'
ORDER BY occurred_at DESC
LIMIT 20;
```

### Collectes ratées — patterns attendus

| Pattern metadata | Interprétation |
|------------------|----------------|
| `capture_source=segment` + event récent post-rollback | Preuve segment ; MP4 source **supprimé** — images incohérentes |
| `evidence_status=partial` + `missing_roles=["plate"]` | Crop plaque impossible (souvent bbox/route) |
| `evidence_status=complete` mais sujet visuellement vide | **Faux positif qualité** — manque garde-fou `bbox_region_has_content` en live |
| Clip `duration_sec` < 0.5 ou asset < 1 Ko | Export ffmpeg raté ou buffer trop court |
| `bbox_ts` NULL | Pipeline n’a pas propagé timestamp source |

**Action recommandée :** script d’audit visuel batch (télécharger N dernières `subject.jpg` + Laplacian variance) + marquer events `evidence_audit=failed` sans supprimer l’historique.

---

## 8. Plan de résolution recommandé (sans cam 108)

### Phase 1 — Reproduction deterministe (obligatoire)

- [ ] **P1.1** Créer `ai-engine/tests/fixtures/speed_pass.mp4` (ou utiliser vidéo démo existante sous `data/videos/demo/`) avec véhicule traversant zone vitesse.
- [ ] **P1.2** Test d’intégration : `FileVideoWorker` + pipeline + zone_speed + capture → assert `bbox_region_has_content(subject crop)`.
- [ ] **P1.3** Test unitaire : `_resolve_capture_frame` quand `bbox_ts` décalé de 200 ms vs `frame_ts` → doit retourner frame buffer @ bbox_ts (déjà partiellement dans `test_evidence_capture.py`).

### Phase 2 — Correctifs live (priorité)

- [ ] **P2.1** Pour `event_type=speeding` : **ne pas** remplacer bbox/ts via `pick_best_bbox_with_ts` si `evt` contient déjà bbox valide de zone_speed.
- [ ] **P2.2** Passer `frame_ts=evt.get("bbox_ts")` à `attach_evidence_async` (pas `frame_wall_ts` émission).
- [ ] **P2.3** Appliquer `bbox_region_has_content` en live ; si échec, scanner ±N frames dans ring buffer ; si toujours échec → `partial` explicite (ne pas mentir « complete »).
- [ ] **P2.4** Option : capture **synchrone** (`attach_evidence` sync) pour `_EVIDENCE_MANDATORY` types incl. `speeding`.
- [ ] **P2.5** Aligner timestamps ring buffer : option « push avec ts explicite » depuis read loop (`frame_capture_ts`) partagé avec pipeline via queue metadata.

### Phase 3 — Validation sans RTSP 108

- [ ] **P3.1** `FileVideoWorker` sur MP4 démo avec zone DB existante (résoudre org/cam IDs via API).
- [ ] **P3.2** Autre caméra RTSP du parc si disponible — sinon skip RTSP live dans checklist.
- [ ] **P3.3** `scripts/validate_speed_evidence_chain.py` vert en WSL.
- [ ] **P3.4** Audit 10 derniers events speeding : **0** sujet vide (critère Laplacian / détection contour dans bbox).

### Phase 4 — Stockage & UI

- [ ] **P4.1** Rétro-capture : pour events `partial` sans package, `capture_retroactive` via ring buffer (live) — pas segment.
- [ ] **P4.2** Badge UI `partial` / `failed` visible (déjà partiellement dans `EvidenceViewer.tsx`).
- [ ] **P4.3** Documenter events segment historiques non réparables.

### Phase 5 — Phase A globale (hors scope immédiat mais contexte)

- [ ] Remettre limite zone **30 km/h** (était 1 km/h pour tests).
- [ ] Valider 5/5 règles démo avec **même** pipeline preuve live.
- [ ] Ne pas réactiver segment mode.

---

## 9. Checklist de validation finale (à cocher par l’agent)

### A. Environnement

- [ ] **A.1** Un seul processus `uvicorn citevision_ai` sur port 8001 (`pgrep -af uvicorn`).
- [ ] **A.2** `GET /health` → `status=ok`, `yolo_cuda=true`, `ffmpeg_available=true`.
- [ ] **A.3** `GET /cameras` → cam 108 (si démarrée) **sans** `mode: segment_cycle` ; présence `frames_read`, `queue_depth` (RTSP live).
- [ ] **A.4** `settings.parsed_segment_mode_camera_ids()` → `frozenset()` vide.

### B. Tests automatisés (WSL)

```bash
cd ~/citevision-v2/ai-engine
source ~/.citevision-v2/ai-engine-venv/bin/activate
python -m pytest \
  tests/test_evidence_capture.py \
  tests/test_zone_speed_evidence.py \
  tests/test_evidence_buffer.py \
  tests/test_segment_mode.py \
  -q
```

- [ ] **B.1** Tous les tests ci-dessus passent.
- [ ] **B.2** `python ~/citevision-v2/scripts/validate_speed_evidence_chain.py` → exit 0.

### C. Preuve live sur vidéo fichier (sans cam 108)

- [ ] **C.1** Démarrer `FileVideoWorker` / caméra fichier démo avec zone `speed_measurement` active.
- [ ] **C.2** Au moins 1 event `speeding` généré.
- [ ] **C.3** `evidence_snapshot.package.metadata.capture_source` ≠ `segment` (live / absent).
- [ ] **C.4** `scene.jpg` : bbox contient véhicule (audit visuel ou Laplacian > seuil dans ROI bbox).
- [ ] **C.5** `subject.jpg` : véhicule visible remplissant le crop (pas route vide).
- [ ] **C.6** `clip.mp4` : ffprobe ≥ 24 frames, duration ≥ 2 s, size > 50 Ko.
- [ ] **C.7** `plate.jpg` : partial accepté si OCR impossible, mais **pas** bande noir 90 %+ (missing_roles=`["plate"]` OK).

### D. Chaîne stockage

- [ ] **D.1** Objet MinIO présent pour chaque asset référencé dans snapshot.
- [ ] **D.2** URL API `/api/v1/orgs/{org}/evidence/...` retourne 200 pour scene/subject/clip.
- [ ] **D.3** Alerte DB liée avec `evidence_status=complete` seulement si C.4–C.6 OK.
- [ ] **D.4** Mail Mailhog reçu si règle mail configurée (optionnel demo).

### E. Non-régression segment (code dormant)

- [ ] **E.1** Avec `segment_mode_camera_ids=""`, aucun code path n’appelle `capture_from_segment` en runtime.
- [ ] **E.2** Aucun MP4 temp `/tmp/cv_seg_*` créé en steady state.

### F. Audit historique raté

- [ ] **F.1** Script audit exécuté sur 20 derniers speeding — rapport `% partial / empty subject`.
- [ ] **F.2** Les nouveaux events post-fix ont taux d’échec **strictement inférieur** aux events segment (`capture_source=segment`).

---

## 10. Commandes utiles

```bash
# Statut caméras AI
curl -s http://127.0.0.1:8001/cameras | python3 -m json.tool

# Resync spatial + restart workers live
python3 ~/citevision-v2/scripts/restore_live_mode_108.py

# Diag events récents
python3 ~/citevision-v2/scripts/_diag_event_evidence.py

# Qualité preuve alerte
bash ~/citevision-v2/scripts/verify-evidence-quality.sh

# ffprobe clip
ffprobe -v error -count_frames -select_streams v:0 \
  -show_entries stream=nb_read_frames,duration \
  -of csv=p=0 /path/to/clip.mp4

# Tests zone_speed bbox in-zone only
python -m pytest tests/test_zone_speed_evidence.py -v
```

---

## 11. Tests unitaires existants (référence rapide)

| Test | Fichier | Ce qu’il garantit |
|------|---------|-------------------|
| `test_pick_best_bbox_with_ts_returns_source_frame_timestamp` | `test_evidence_capture.py` | bbox_ts = ts du candidat gagnant |
| `test_resolve_capture_frame_falls_back_to_ring_buffer_by_bbox_ts_when_stale` | idem | Pas frame émission si bbox plus ancien |
| `test_draw_bbox_on_scene_only_not_subject` | idem | Bbox UI/scene seulement |
| `test_best_bbox_not_updated_outside_zone` | `test_zone_speed_evidence.py` | Fix bbox hors zone |
| `test_best_bbox_updated_inside_zone` | idem | Fix bbox dans zone |
| `test_segment_pts_from_bbox_ts` | `test_segment_mode.py` | Conversion horloge segment (legacy) |

**Manque critique à ajouter :** test intégration live « speeding → upload → subject non vide » sans RTSP.

---

## 12. Politique preuve par défaut

```python
# ai-engine/src/citevision_ai/evidence/gate.py — default_evidence_policy()
images = [
  {"role": "scene", "label": "Vue d'ensemble", "crop": "full"},           # + bbox dessinée si draw_bbox
  {"role": "subject", "label": "Cible détectée", "crop": "bbox", ...},     # zoom sans bbox
  {"role": "plate", "label": "Plaque", "crop": "plate_rear", ...},        # bande arrière bbox véhicule
]
clip_seconds = 6
```

Frontend : `EvidenceViewer.tsx` — overlay bbox sur **scene** ; subject sans overlay.

---

## 13. Pièges connus (lire avant de coder)

1. **Sync WSL oubliée** → code Windows correct, runtime WSL ancien (symptôme : fix « invisible »).
2. **Double uvicorn** → port 8001 sert ancien binaire ; validate_segment passait en local mais prod ratée.
3. **Segment + live mélangés** → events DB avec `capture_source=segment` alors que mode live ; retro impossible.
4. **Async evidence** → race entre MQTT event et upload ; frontend peut afficher `pending` puis partial.
5. **IDs hardcodés** interdits en prod — résoudre via API ; OK en scripts test avec env overrides.
6. **Ne pas réintroduire** scripts `_fix_zone_*` ou seeds géométrie sans accord.
7. **Cam 108 inaccessible** — ne pas bloquer le chantier ; utiliser file video + tests synthétiques.

---

## 14. Definition of Done (DoD) pour clore le chantier

Le chantier est clos lorsque **tous** les points suivants sont vrais :

1. Un event `speeding` produit sur **vidéo fichier** (sans RTSP 108) a `evidence_status=complete` avec scene+subject+clip **visuellement corrects** (véhicule dans bbox et crop).
2. Checklist section 9 **100 % cochée** avec preuves (captures ffprobe, screenshots UI, extrait SQL).
3. Tests automatisés section B verts en CI/WSL.
4. Rapport audit section F : nouveaux events ≥ 80 % sujets valides (seuil Laplacian), ancients segment exclus du calcul.
5. Aucune régression : feux, comptage, téléphone, ceinture — même pipeline preuve live (pas segment).
6. Document court `docs/EVidence-LIVE-ALIGNMENT.md` (1 page) décrivant la solution retenue — **optionnel**, sur demande utilisateur.

---

## 15. Contact & historique conversation

- Transcript agent précédent : `agent-transcripts/86875d06-d408-4e2a-8aec-92f77016b6cc/86875d06-d408-4e2a-8aec-92f77016b6cc.jsonl`
- Plan segment (ne pas modifier) : `mode_segments_10s_cam108_*.plan.md` (Cursor plans)
- Dernière action humaine : rollback live + demande passation Opus faute d’accès cam 108

---

*Fin du document de passation — bon courage.*
