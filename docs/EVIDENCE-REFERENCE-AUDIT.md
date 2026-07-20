# Evidence Reference Audit — citevision_videoverbalisation → citevision-v2

Référence locale (lecture seule) : `vendor/citevision_videoverbalisation/mono/`.

## Principe ancienne app

Une **unité temporelle Frigate** par infraction : `SingleTrackWorker` (1 worker / `track_id` MQTT) télécharge clip + snapshot + thumbnail du **même** `frigate_event_id`, extrait des frames clip (ffmpeg Q=2), OCR multi-frames via `ocr_service` Fast-ALPR, puis persiste preuves **avant** alerte.

CitéVision v2 **conserve `zone_speed` ai-engine** pour la règle ; seule la **composition preuve** est reprise.

## Fonctions cibles (mono/citevision.py)

| Ancienne fonction / classe | Rôle | Port v2 |
|---|---|---|
| `VehicleTrackerManager` | Spawn workers MQTT Frigate | *Non porté* — détection = zone_speed |
| `SingleTrackWorker` | Orchestration preuve par piste | `frigate_track_evidence.FrigateTrackEvidence.capture()` |
| `_wait_for_event_media` | Attend `has_snapshot` + `has_clip` | `FrigateTrackEvidence._wait_for_event_media()` |
| `_download_event_clip_only` | GET `/api/events/{id}/clip.mp4` + retries | `_download_event_clip()` |
| `_download_event_snapshots` | snapshot.jpg + thumbnail.jpg | `_build_images()` |
| `_extract_frames` / clip burst | ffmpeg `-q:v` CLIP_FRAME_JPEG_Q | `_extract_clip_frames()` |
| `_recognize_plate_via_local` | HTTP Fast-ALPR | `ocr_client.recognize_plate_jpeg()` |
| `_recognize_plate_from_paths` | Multi-candidats + PLATE_STOP_CONF | `_ocr_plate()` |

## Correspondance variables d'environnement

| Ancien (`mono/citevision.env.example`) | Nouveau (citevision-v2) |
|---|---|
| `CITEVISION_FRIGATE_URL` | `FRIGATE_URL` |
| `CITEVISION_SNAPSHOT_RETRIES` | `FRIGATE_SNAPSHOT_RETRIES` (défaut 8) |
| `CITEVISION_SNAPSHOT_RETRY_DELAY` | `FRIGATE_SNAPSHOT_RETRY_DELAY` |
| `CITEVISION_SNAPSHOT_QUALITY` | `FRIGATE_SNAPSHOT_QUALITY` |
| `CITEVISION_SNAPSHOT_USE_CLEAN` | essai `snapshot-clean.webp` avant jpg |
| `CITEVISION_CLIP_RETRIES` | `FRIGATE_CLIP_RETRIES` |
| `CITEVISION_CLIP_RETRY_DELAY` | `FRIGATE_CLIP_RETRY_DELAY` |
| `CITEVISION_CLIP_WAIT_IF_MISSING` | `FRIGATE_CLIP_WAIT_IF_MISSING` |
| `CITEVISION_CLIP_MIN_BYTES` | `FRIGATE_CLIP_MIN_BYTES` |
| `CITEVISION_CLIP_WINDOW_PAD_BEFORE/AFTER` | `FRIGATE_CLIP_PAD_BEFORE/AFTER` |
| `CITEVISION_EVENT_MEDIA_WAIT_SEC` | `FRIGATE_EVENT_MEDIA_WAIT_SEC` |
| `CITEVISION_EVENT_MEDIA_POLL_SEC` | `FRIGATE_EVENT_MEDIA_POLL_SEC` |
| `CITEVISION_CLIP_FRAME_JPEG_Q` | `FRIGATE_CLIP_FRAME_JPEG_Q` |
| `CITEVISION_EVIDENCE_IMAGE_COUNT` | `FRIGATE_EVIDENCE_FRAME_COUNT` |
| `CITEVISION_OCR_URL` | `OCR_URL` ou `CITEVISION_OCR_URL` |
| `CITEVISION_OCR_TIMEOUT` | `OCR_TIMEOUT` |
| `CITEVISION_PLATE_MAX_FRAMES` | `PLATE_MAX_FRAMES` |
| `CITEVISION_PLATE_STOP_CONF` | `PLATE_STOP_CONF` |
| `EVIDENCE_BACKEND` | `ring_buffer` \| `frigate` \| `hybrid` |
| `FRIGATE_ENABLED` + `FRIGATE_EVIDENCE` | requis pour mode `frigate` |

## Modules v2 implémentés

| Fichier | Description |
|---|---|
| `ai-engine/.../frigate_track_evidence.py` | Corrélation event Frigate (temps + IoU + label), download retries, frames clip |
| `ai-engine/.../ocr_client.py` | Client HTTP Fast-ALPR |
| `ai-engine/.../frigate_backend.py` | Wrapper mince → `FrigateTrackEvidence` |
| `ai-engine/.../service.py` | Mode `frigate` = track evidence uniquement ; upload sync avant MQTT |
| `ai-engine/.../pipeline.py` | `attach_evidence(async_upload=False)` quand `EVIDENCE_BACKEND=frigate` |
| `infra/ocr_service/` | Service Docker Fast-ALPR (port 8181) |
| `rules-engine/.../executor.go` | `hasEvidencePackage` exige `bbox_quality_ok=true` |

## Métadonnées preuve enrichies

```json
{
  "capture_source": "frigate_track",
  "bbox_source": "frigate_mqtt",
  "frigate_event_id": "...",
  "frigate_bbox_embedded": true,
  "align_delta_ms": 120,
  "evidence_frame_count": 6,
  "plate_ocr_source": "fast_alpr",
  "bbox_quality_ok": true,
  "evidence_status": "complete"
}
```

## Scripts d'audit

| Ancien (`mono/scripts/`) | Nouveau v2 |
|---|---|
| `audit-evidences.sh` | `scripts/audit-evidences.sh` (wrapper Postgres/MinIO) |
| `inspect-clip-quality.sh` | intégré dans `scripts/audit_evidence_quality.py` (H3 clip) |
| `ocr-bench-quick.sh` | `scripts/ocr-bench-quick.sh` (bench OCR service) |

Classes `audit_evidence_quality.py` :

- **H1** : `capture_source=segment` (legacy)
- **H2** : pas de `bbox_ts` (async désaligné)
- **H3** : clip < 1 Ko
- **H4** : subject texture Laplacian < 50
- **H5** : `bbox_quality_ok=false` ou `capture_source=frigate_track` sans `frigate_event_id`

Validation terrain : `scripts/validate_evidence_cam108.py --camera-id <uuid>` (IDs résolus via API/DB, pas de hardcode zones).

## Règle d'or (alignement bbox)

Ne **jamais** dessiner une bbox YOLO sur un snapshot Frigate d'un autre instant. La bbox affichée = bbox MQTT Frigate de l'event corrélé (`frigate_bbox_embedded=true`).

## Sécurité

Le PAT GitHub utilisé pour le clone initial doit être **révoqué** ; utiliser `GH_TOKEN` en variable locale pour les mises à jour du vendor.
