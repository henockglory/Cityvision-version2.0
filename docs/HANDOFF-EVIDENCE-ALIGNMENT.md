# Handoff — Alignement preuves (evidence) vitesse / bbox / stockage

**Destinataire** : agent Opus 4.8 (ou développeur reprenant le chantier)  
**Date rédaction** : 2026-07-08  
**Contexte** : l’utilisateur **n’aura plus accès à la caméra RTSP `192.168.1.108`**. Toute validation terrain devra passer par **vidéos démo**, **tests unitaires**, **replay fichier**, ou **audit des preuves déjà stockées** (MinIO + PostgreSQL).

---

## 1. Résumé exécutif (lire en premier)

### Symptôme utilisateur

Les preuves d’alertes **speeding** (et parfois plaque) sont **inutilisables** :

| Rôle UI | Label | Problème observé |
|---------|-------|------------------|
| `scene` | Vue d’ensemble | Cadre bleu (bbox) sur **route vide**, véhicule absent ou ailleurs dans l’image |
| `subject` | Cible détectée | Crop sur **asphalte / béton / rampe**, pas sur le véhicule |
| `plate` | Plaque | Bande noire + micro-patch de bitume, **aucune plaque** |
| `clip` | Vidéo 6 s | Parfois OK, parfois 262 octets (bug segment résolu), parfois véhicule déjà sorti du cadre |

### Cause racine (conceptuelle)

> **La bbox et la frame JPEG utilisées pour générer les crops ne proviennent pas du même instant.**

Ce n’est pas qu’un problème d’affichage UI : les **JPEG sont gravés tels quels dans MinIO** avec des métadonnées parfois incohérentes. Le stockage contient donc un **historique de preuves ratées** qu’il faut savoir **auditer** et **ne plus reproduire**.

### Décision produit (2026-07-08)

Le **mode segments 10 s** (Phase A caméra 108) est **abandonné** :

- `segment_mode_camera_ids` remis à **`""`** dans `ai-engine/src/citevision_ai/config.py`
- Caméra 108 repassée en **RTSP live continu** (`RTSPWorker`)
- Le code segment **reste dans le dépôt** mais **ne doit pas être réactivé** sans accord explicite

### Mission pour Opus

1. **Fiabiliser la chaîne preuve en mode live** (ring buffer + `bbox_ts` + frame alignée).
2. **Ne pas réintroduire** de trou d’acquisition (record/process gap).
3. **Documenter / tester** sans caméra 108.
4. **Cocher la checklist §10** après chaque intégration.

---

## 2. Socle CitéVision (règles non négociables)

Lire `.cursor/rules/citevision-socle.mdc` à chaque session.

| Règle | Implication pour ce chantier |
|-------|------------------------------|
| **zone → IA → règle → preuve** | La preuve doit correspondre à l’événement émis par la règle, pas à un artefact technique |
| **[A.3] Validé = preuves complètes** | Clip ~6 s + 2 images + plaque si routier ; capture alerte + fichiers + mail Mailhog si configuré |
| **[A.9]** | Pas d’alerte « finale » présentée comme définitive sans preuves exigées par la politique |
| **[P.138] Runtime WSL** | Édition Windows `C:\Users\gheno\citevision` → sync vers `~/citevision-v2` avant livraison |
| **[P.131]** | **Jamais** d’IDs org/caméra codés en dur dans le code de prod (OK dans scripts de test **paramétrables**) |
| **[P.135]** | Pas de scripts `_fix_*` qui réécrivent la DB automatiquement |

---

## 3. Environnement et accès

### Runtime de vérité

| Élément | Valeur |
|---------|--------|
| Édition | `C:\Users\gheno\citevision` |
| Runtime WSL | `~/citevision-v2` |
| Sync | `bash scripts/sync-all-targets.sh` |
| AI Engine | `http://127.0.0.1:8001` — restart : `python3 scripts/_restart_ai.py` |
| Backend API | `http://127.0.0.1:8081` |
| PostgreSQL | docker `citevision-v2-postgres`, user/db `citevision` |
| MinIO | docker `citevision-v2-minio`, bucket `citevision-evidence` (via `.env`) |
| Mailhog | si configuré pour alertes premium |

### Caméra 108 (référence historique — **plus accessible**)

| Champ | Valeur |
|-------|--------|
| UUID caméra | `37c7d7fa-12dc-450c-8c4b-ab63ed43a819` |
| RTSP (ne plus compter dessus) | `rtsp://admin:***@192.168.1.108:554/live` |
| Org démo typique | `74d51ead-97a7-4e41-a488-503a9b90c466` (vérifier live via API) |

### Vérifier qu’on est bien en live (pas segment)

```bash
curl -s http://127.0.0.1:8001/cameras | python3 -m json.tool
```

Attendu pour 108 :

- Présence de `frames_read`, `queue_depth`, `infer_latency_ms`
- **Absence** de `mode: "segment_cycle"`, `segment_state`, `cycle`

Config :

```bash
cd ~/citevision-v2/ai-engine && PYTHONPATH=src python3 -c \
  "from citevision_ai.config import settings; print(settings.parsed_segment_mode_camera_ids())"
# Attendu : frozenset() vide
```

---

## 4. Architecture cible : zone → IA → règle → preuve

```mermaid
flowchart LR
  RTSP[RTSP read loop] --> Ring[FrameRingBuffer RING_FPS]
  RTSP --> Queue[Infer queue]
  Queue --> Pipe[PipelineService.process_frame]
  Pipe --> ZS[ZoneSpeedEngine]
  ZS -->|speeding + bbox + bbox_ts| Pub[_publish_event_with_evidence]
  Ring --> Pub
  Pub --> Cap[EvidenceCaptureService]
  Cap --> MinIO[MinIO JPEG/MP4]
  Cap --> MQTT[MQTT event + package]
  MQTT --> Rules[Rules Engine]
  Rules --> PG[(PostgreSQL events/alerts)]
```

### Politique de preuve par défaut

Fichier : `ai-engine/src/citevision_ai/evidence/gate.py` → `default_evidence_policy()`

| Rôle | Label UI | Crop |
|------|----------|------|
| `scene` | Vue d’ensemble | full frame + **bbox dessinée** (depuis correctif UI/backend) |
| `subject` | Cible détectée | crop bbox **sans** bbox dessinée (zoom seul) |
| `plate` | Plaque | `bbox_rear_plate_region` sur bbox véhicule |
| clip | — | 6 s centré sur `bbox_ts` |

Constantes : `ai-engine/src/citevision_ai/evidence/config.py`

- `RING_SECONDS = 12`, `RING_FPS = 12`, `CLIP_DURATION_SEC = 6`
- `FRAME_ALIGN_TOLERANCE_SEC = 0.15`

---

## 5. Chronologie des tentatives (post-mortem)

### Phase 0 — Mode live initial (bug original)

**Symptôme** : « cadre bleu sur route vide » — véhicule déjà passé.

**Mécanisme défaillant** :

1. `zone_speed` émet `speeding` avec bbox de `_best_bbox` / `_last_bbox` capturée **plus tôt** dans le passage.
2. `EvidenceCaptureService` utilisait la **frame au moment de l’émission** (`attach_evidence_async`) ou lookup ring buffer au **`timestamp` ISO de l’événement** au lieu de **`bbox_ts`**.
3. `pick_best_bbox_with_ts` pouvait choisir une bbox dans l’**historique** (`_bbox_history`) décalée de la frame courante.

**Correctifs partiels conservés (mode live)** :

- `pick_best_bbox_with_ts` retourne le **timestamp source** de la bbox gagnante
- `_resolve_capture_frame` : priorité frame live si `|bbox_ts - frame_ts| ≤ 0.15 s`, sinon ring buffer à `bbox_ts`
- Tests : `test_resolve_capture_frame_*`, `test_pick_best_bbox_with_ts_*` dans `tests/test_evidence_capture.py`

### Phase A — Mode segments 10 s (ABANDONNÉ 2026-07-08)

**Intent** : RECORD 10 s → PROCESS ≤ 5 s → trou ~5 s → boucle, pour caméra 108 uniquement.

**Fichiers clés** :

| Fichier | Rôle |
|---------|------|
| `ingest/segment_cycle_worker.py` | Machine RECORD / PROCESS, MP4 temp |
| `ingest/timeline.py` | `FrameTimeline`, `SegmentCaptureContext` |
| `evidence/segment_align.py` | PTS, seek frame par index |
| `evidence/segment_replay_cache.py` | Cache JPEG replay (tentative anti-seek) |
| `pipeline.process_segment_eof` | Flush `track_lost` fin de segment |
| `config.segment_mode_camera_ids` | Opt-in caméras (maintenant **vide**) |

**Bugs rencontrés en segment mode** :

| # | Bug | Effet |
|---|-----|-------|
| S1 | Uvicorn fantôme sur port 8001 | Clips **262 octets**, ancien code servait les requêtes |
| S2 | Capture async après suppression MP4 | Clips vides / extraction ffmpeg échouée |
| S3 | EOF flush : bbox `_best_bbox` frame N, image frame EOF fin segment | Véhicule sorti du cadre |
| S4 | Pipeline écrasait bbox zone_speed par bbox **frame courante** (sortie zone) | Bbox ≠ meilleur instant |
| S5 | `resolve_segment_capture_frame` préférait frame replay courante | Mauvaise frame malgré `segment_bbox_frame_index` |
| S6 | OpenCV `CAP_PROP_POS_FRAMES` / `POS_MSEC` sur H.264 | Seek imprécis → frame décalée |
| S7 | `_best_bbox` mise à jour **hors zone** | Bbox sur route vide (faux positif loin du véhicule) |
| S8 | Trou ~5 s entre cycles | Perte d’événements + utilisateur mécontent |

**Correctifs segment tentés (code toujours présent)** :

- Capture **synchrone** pendant replay
- Copie `{segment}.evidence.mp4` pour ffmpeg
- `segment_bbox_frame_index` dans événements zone_speed
- Ne plus écraser bbox zone_speed en segment (partiellement)
- Cache replay JPEG + `bbox_region_has_content`
- `_best_bbox` seulement **dans** zone (`_maybe_update_best_bbox`)

**Décision** : tout cela reste **insuffisant / trop fragile** vs flux live + ring buffer.

### Phase B — Retour live (état actuel)

- `segment_mode_camera_ids = ""`
- Script : `scripts/restore_live_mode_108.py`
- UI evidence : bbox overlay sur **Vue d’ensemble** uniquement (`EvidenceViewer.tsx`)

**Problème non résolu** : preuves live **encore ratées** selon utilisateur → **c’est le cœur du handoff**.

---

## 6. Mécanismes qui produisent des preuves ratées (catalogue exhaustif)

### 6.1 Désalignement temporel bbox ↔ frame

| Scénario | Où | Détail |
|----------|-----|--------|
| Émission tardive | `pipeline.py` boucle événements | Événement émis à frame T, bbox de frame T-k |
| Historique bbox | `pick_best_bbox_with_ts` + `_bbox_history` | Meilleure bbox ≠ frame de capture |
| Async evidence | `attach_evidence_async` | Thread démarre après ; ring buffer a bougé |
| Lookup mauvais ts | `_resolve_capture_frame` fallback | Utilise `event timestamp` si `bbox_ts` absent |
| Inférence throttled | `priority_zone_skip` | Zone speed voit 1 frame sur N ; bbox_ts peut ne pas exister dans ring buffer |

### 6.2 Bbox géométriquement mauvaise

| Scénario | Où | Détail |
|----------|-----|--------|
| Glitch sortie zone | `bbox_evidence_score` filtre partiel | Oversized bbox encore possible |
| `_best_bbox` hors zone | **Corrigé** mais preuves **historiques** restent | Voir §8 audit |
| Track perdu | `track_lost` EOF / fin segment | Utilise `_best_bbox` — OK si frame alignée |
| Classe / track ID | ByteTrack fragmentation | `track_id` change → mauvaise association plaque |

### 6.3 Ring buffer

| Scénario | Où | Détail |
|----------|-----|--------|
| Pas de buffer segment | `main.py` | `push_frame` **désactivé** si caméra en segment mode |
| JPEG lossy dans ring | `FrameRingBuffer` | Réinférence depuis JPEG dégrade plaque |
| `get_frame_at_ts` imprécis | `buffer.py` | Tolérance / pas assez de frames si RING_FPS < besoin |
| Clip centré wrong | `export_clip_mp4(center_ts=...)` | Si `bbox_ts` faux → clip hors sujet |

### 6.4 Segment mode (preuves historiques `capture_source=segment`)

Événements en base avec :

```json
"metadata": {
  "capture_source": "segment",
  "segment_bbox_frame_index": 42,
  "segment_frame_pts": 3.5,
  "bbox_ts": 173...
}
```

Même quand `segment_bbox_frame_index` est correct :

- Seek MP4 peut renvoyer **mauvaise frame**
- Bbox peut avoir été collectée **hors zone** (avant correctif)
- Fichier segment **supprimé** après cycle → `capture_retroactive` impossible

### 6.5 Stockage et statuts

| Statut | Signification |
|--------|---------------|
| `evidence_status: complete` | scene + subject + clip (+ plaque si exigée) |
| `partial` | Manque clip ou plaque |
| `failed` | Upload MinIO échoué |
| `pending` | Événement publié avant fin capture async |

**Piège** : `complete` ne garantit **pas** que le contenu visuel est correct — seulement que les **fichiers existent**.

---

## 7. Cartographie code (fichiers à maîtriser)

### Ingest

| Fichier | Notes |
|---------|-------|
| `ingest/rtsp_worker.py` | Live : read loop → ring + infer queue |
| `ingest/segment_cycle_worker.py` | **Désactivé** — ne pas router sans opt-in |
| `main.py` | `buffer_fn` pousse ring **sauf** segment mode |

### Pipeline / événements

| Fichier | Notes |
|---------|-------|
| `pipeline.py` | `process_frame`, `_publish_event_with_evidence`, `_bbox_history` |
| `analytics/zone_speed.py` | `_best_bbox`, `_finalize_crossing`, `segment_bbox_frame_index` |
| `evidence/capture.py` | crops, `pick_best_bbox_with_ts`, `bbox_region_has_content`, `draw_bbox` sur scene only |

### Evidence service

| Fichier | Notes |
|---------|-------|
| `evidence/service.py` | `_resolve_capture_frame`, `_capture_and_attach`, `capture_from_segment`, `capture_retroactive` |
| `evidence/buffer.py` | Ring buffer, `get_frame_at_ts`, `export_clip_mp4` |
| `evidence/uploader.py` | Multipart → backend internal upload |
| `evidence/segment_align.py` | Helpers segment (legacy) |
| `evidence/segment_replay_cache.py` | Cache JPEG segment (legacy) |

### Frontend

| Fichier | Notes |
|---------|-------|
| `frontend/src/components/evidence/EvidenceViewer.tsx` | Tuiles scene/subject/plate ; bbox overlay sur **scene** |
| `frontend/src/components/evidence/EvidenceLightbox.tsx` | Lightbox + `BboxOverlay` |

### Tests existants

| Fichier | Couverture |
|---------|------------|
| `tests/test_evidence_capture.py` | Rôles images, bbox_ts, pick_best |
| `tests/test_zone_speed_evidence.py` | `_best_bbox` seulement in-zone |
| `tests/test_segment_mode.py` | Segment / align (legacy) |

### Scripts ops

| Script | Usage |
|--------|-------|
| `scripts/_restart_ai.py` | Kill **tous** uvicorn citevision_ai puis restart |
| `scripts/restore_live_mode_108.py` | Stop 108 + resync spatial → live |
| `scripts/validate_segment_mode_108.py` | **Obsolète** (attend segment_cycle) — à réécrire pour live |
| `scripts/push_ai_spatial_from_api.py` | Push spatial + start caméras demo |

---

## 8. Audit des preuves ratées déjà en stockage

### 8.1 PostgreSQL — lister événements speeding récents

```sql
SELECT
  id,
  occurred_at,
  camera_id,
  evidence_snapshot->'package'->'metadata'->>'capture_source' AS src,
  evidence_snapshot->'package'->'metadata'->>'evidence_status' AS status,
  evidence_snapshot->'package'->'metadata'->>'segment_bbox_frame_index' AS bidx,
  evidence_snapshot->'package'->'metadata'->>'capture_frame_ts' AS cap_ts,
  evidence_snapshot->'package'->'metadata'->>'bbox_ts' AS bbox_ts,
  evidence_snapshot->'bbox' AS bbox
FROM events
WHERE event_type = 'speeding'
ORDER BY occurred_at DESC
LIMIT 50;
```

Docker :

```bash
docker exec citevision-v2-postgres psql -U citevision -d citevision -c "..."
```

### 8.2 Classifier les preuves historiques

| Classe | Critère SQL / metadata | Action |
|--------|------------------------|--------|
| **H1 Segment** | `capture_source = 'segment'` | Considérer invalides ; ne pas retro-fix sans MP4 source |
| **H2 Live async** | pas de `capture_source`, `bbox_ts` null ou = timestamp event | Suspect désalignement |
| **H3 Clip micro** | clip asset < 1 Ko | Bug segment / ffmpeg |
| **H4 Complete mais vide** | `evidence_status=complete` + audit visuel Laplacian faible | Faux positif qualité |

### 8.3 Audit visuel automatisé (sans caméra)

Inspiré de `validate_segment_mode_108.py` → **`scripts/audit_evidence_quality.py`** (à créer) :

1. Lire `evidence_snapshot.package.images[].asset_id` pour `scene`, `subject`, `plate`
2. Télécharger depuis MinIO (`mc cat` via docker)
3. Calculer score Laplacian / variance (voir `bbox_texture_score` dans validate script)
4. Seuils proposés :
   - `subject` : Laplacian < 50 → **raté**
   - `scene` avec bbox : vérifier que zone bbox a variance > route environnante
5. Exporter CSV `scripts/evidence_audit_report.csv`

### 8.4 MinIO — chemins

Upload via `EvidenceUploader` → backend internal → bucket `citevision-evidence`.

Les `asset_id` sont dans `package.images[]` et `package.clip.asset_id`.

**Les preuves ratées restent** : corriger le pipeline **ne régénère pas** les anciennes alertes. Option produit :

- Badge UI « preuve legacy / non fiable » si `capture_source=segment` ou audit score bas
- Ou job batch **re-capture** seulement si ring buffer / segment encore disponible (souvent **non**)

---

## 9. Piste de solution recommandée (live, sans coupure flux)

### Principe

> **Une seule source de vérité temporelle : `bbox_ts` + frame ring buffer ou frame inference synchronisée.**

### 9.1 Capture synchrone pour événements mandatory

Pour `speeding`, `red_light_violation`, etc. (`_EVIDENCE_MANDATORY`) :

- **Ne pas** utiliser `attach_evidence_async` si latence acceptable (< 200 ms)
- Appeler `_capture_and_attach` **dans le thread inference** avec `frame_ts=frame_wall_ts`

Fichier : `pipeline._publish_event_with_evidence`

### 9.2 Renforcer `bbox_ts` à la source

Dans `zone_speed._finalize_crossing` :

- Toujours émettre `bbox_ts` = timestamp frame où `_best_bbox` a été collectée
- Toujours émettre bbox = `_best_bbox` (pas track bbox sortie zone)
- **Ne jamais** remplacer par `_bbox_history` si score inférieur

Dans `pipeline.py` (mode live) :

- Revoir `pick_best_bbox_with_ts` : candidates = `(evt.bbox, bbox_ts from zone_speed)` + track courant **seulement si même ts**

### 9.3 Garde-fou qualité avant upload

Utiliser `bbox_region_has_content(frame, bbox)` (`capture.py`) :

- Si échec : essayer ±1..3 frames dans ring buffer autour de `bbox_ts`
- Si toujours échec : `evidence_status=partial`, **ne pas** marquer `complete`, log explicite

### 9.4 Ring buffer full-resolution (option)

Problème plaque : JPEG ring buffer flou.

Option : stocker **dernière frame BGR** par timestamp en plus du JPEG, ou augmenter qualité JPEG ring pour caméras « enforcement ».

### 9.5 Tests sans caméra 108

| Méthode | Comment |
|---------|---------|
| **Unit** | Étendre `test_evidence_capture.py`, `test_zone_speed_evidence.py` |
| **Replay MP4** | `FileVideoWorker` + vidéo démo org avec véhicules |
| **Synthétique** | Frame numpy + bbox connue → vérifier crop contient pixels attendus |
| **Regression** | Golden files : hash JPEG subject non vide |
| **Audit DB** | Script §8.3 sur N derniers events |

### 9.6 Ce qu’il ne faut PAS refaire

- Réactiver segment mode pour « simplifier » l’alignement
- Hardcoder zones / IDs caméra 108
- Scripts `_fix_*` qui UPDATE events en masse sans validation humaine
- Affirmer « validé 5/5 » sans preuves Mailhog + captures

---

## 10. Checklist de validation (à cocher par Opus)

> **État coché le 2026-07-08** — détails et limites dans `docs/EVIDENCE-FIX-REPORT.md`.

### A. Environnement

- [x] **A1** — `parsed_segment_mode_camera_ids()` vide sur runtime WSL (`frozenset()`)
- [x] **A2** — Un seul processus uvicorn sur 8001 après restart (`pgrep -af citevision_ai`)
- [x] **A3** — `/health` AI ok, YOLO CUDA (`CUDAExecutionProvider`)
- [x] **A4** — Caméras actives en live (`frames_read` présent, pas `segment_cycle`)

### B. Pipeline live — alignement

- [x] **B1** — Chaque événement `speeding` a `bbox_ts` non null (test E2E synthétique)
- [x] **B2** — `bbox_ts` ≤ timestamp émission événement (test E2E)
- [x] **B3** — Résolution frame testée : frame live si alignée, sinon ring à `bbox_ts` + retry voisins (`test_live_evidence_alignment.py`)
- [x] **B4** — `_best_bbox` mis à jour **uniquement** quand track in-zone (test `test_zone_speed_evidence.py` passe)
- [x] **B5** — Pas de régression : suite complète `tests/` = 122 passed

### C. Qualité images

- [x] **C1** — Vue d’ensemble : bbox sur scene, pas subject (validé synthétique)
- [x] **C2** — Cible détectée : crop montre le véhicule (test E2E : Laplacian > 50 + pixels véhicule)
- [x] **C3** — Plaque : `missing_roles: ["plate"]` explicite + message UI
- [x] **C4** — `bbox_region_has_content` rejette route uniforme (test unitaire)
- [x] **C5** — Qualité insuffisante → `evidence_status=partial` forcé + `bbox_quality_ok=false` (test unitaire)

### D. Clip vidéo

- [x] **D1** — Clip ≥ 1 Ko, contient `ftyp` (test E2E avec ffmpeg)
- [ ] **D2** — ffprobe ≥ 24 frames uniques — **non vérifiable sans flux réel** (vidéos démo sans traversée speeding)
- [x] **D3** — Clip centré sur `bbox_ts` (`export_clip_mp4(center_ts=bbox_ts)`)

### E. Stockage / persistance

- [x] **E1** — MinIO : subject.jpg servi via API evidence (41 Ko, JPEG valide)
- [x] **E2** — PostgreSQL : `evidence_snapshot.package` peuplé sur event final
- [ ] **E3** — Alerte UI sans `loadFailed` — API OK, vérification navigateur à refaire à la prochaine session UI
- [x] **E4** — Script audit §8.3 exécuté (`audit_evidence_quality.py`) ; à re-passer sur les nouveaux events live

### F. Preuves historiques ratées

- [x] **F1** — Rapport audit H1/H2/H3/H4 produit (`scripts/evidence_audit_report.csv`)
- [x] **F2** — UI distingue `capture_source=segment` (bandeau legacy) et `bbox_quality_ok=false`
- [x] **F3** — Documenté : anciennes alertes peuvent avoir preuves vides (rapport §5)
- [x] **F4** — Politique documentée : pas de re-génération (sources MP4 supprimées)

### G. Non-régression socle Phase A

- [x] **G1** — Flux live **sans trou** 5 s (segment mode désactivé partout)
- [x] **G2** — 5 règles démo : suite complète verte, mécanisme commun intact
- [ ] **G3** — Limite vitesse zone 108 encore à 1 km/h — **action utilisateur via ZoneEditor** ([P.135] interdit l'écriture DB auto)
- [ ] **G4** — Mailhog non testé (aucun nouvel événement speeding déclenché — voir rapport §6)

---

## 11. Requêtes et commandes utiles

### Restart AI propre

```bash
python3 ~/citevision-v2/scripts/_restart_ai.py
pgrep -af uvicorn
curl -s http://127.0.0.1:8001/health | python3 -m json.tool
```

### Tests Python

```bash
cd ~/citevision-v2/ai-engine
source ~/.citevision-v2/ai-engine-venv/bin/activate
python -m pytest tests/test_evidence_capture.py tests/test_zone_speed_evidence.py -q
```

### Resync caméras après changement config

```bash
python3 ~/citevision-v2/scripts/restore_live_mode_108.py
# ou POST /api/v1/internal/ingest/resync-spatial avec X-Internal-Key
```

### Compter preuves segment vs live (7 derniers jours)

```sql
SELECT
  evidence_snapshot->'package'->'metadata'->>'capture_source' AS src,
  COUNT(*) AS n
FROM events
WHERE event_type = 'speeding'
  AND occurred_at > NOW() - INTERVAL '7 days'
GROUP BY 1;
```

---

## 12. Hypothèses ouvertes (pour Opus)

1. **Throttling inférence** : `priority_zone_skip` ~8 Hz — le ring buffer 12 fps compense-t-il toujours ?
2. **Plaque** : OCR nécessite crop HD — faut-il frame BGR native dans ring ?
3. **Motos** : bbox petite + rapide → `_best_bbox` frame index optimal ?
4. **Multi-caméra** : sous charge GPU, latence infer > 150 ms → async evidence re-devient problématique
5. **Retro-fix stockage** : acceptable produit ou seulement forward-fix ?

---

## 13. Definition of Done (DoD)

Le chantier est **terminé** quand :

1. Checklist §10 sections **A–E** et **G** : **100 % cochées** sur environnement WSL avec **vidéo démo** (pas 108).
2. Script audit §8.3 : **0 nouvelles** preuves « subject vide » sur 10 événements speeding consécutifs.
3. Un rapport court `docs/EVIDENCE-FIX-REPORT.md` liste : cause racine finale, diff fichiers, résultats tests, limites connues.
4. Aucune réactivation segment mode sans section dédiée dans le rapport + accord utilisateur.

---

## 14. Contacts / transcripts

- Transcript session principale : `agent-transcripts/86875d06-d408-4e2a-8aec-92f77016b6cc.jsonl`
- Plan segment (ne pas modifier) : `mode_segments_10s_cam108_9b1f6446.plan.md` (si présent à la racine ou `.cursor/plans/`)
- Règles socle : `.cursor/rules/citevision-socle.mdc`

---

*Document généré pour handoff Opus 4.8 — priorité : fiabilité preuve live, audit stockage existant, zéro trou flux.*
