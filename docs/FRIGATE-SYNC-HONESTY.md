# Frigate sync — honesty bounds (Frigate-primary + Gemini)

## Universal orchestration contract

Machine-readable source: [`shared/rule-orchestration-contract.json`](../shared/rule-orchestration-contract.json).

Every rule template declares:

| Field | Meaning |
|-------|---------|
| `signal_owner` | Who produces the track/signal: `frigate` \| `citevision_local` \| `hybrid` |
| `judgment_owner` | Who decides the métier event: `geometry` \| `frigate_speed` \| `gemini` \| `insightface` \| `identity_fusion` \| `ocr_fusion` \| `rules_composite` |
| `vlm_role` | Gemini usage: `none` \| `yes_no` \| `clear_face_gate` \| `multimodal_same_person_vote` \| `ocr` \| `anti_fp_optional` |
| `emit_moment` | When to emit: enter/exit/duration/end_time/vlm/embed |
| `xor_disables` | Local paths that must stay OFF when the bridge owns the signal |
| `evidence_policy` | Clip + image roles + fail_closed |
| `dod_alias` | `validate_rule.sh` alias |
| `catalog_badge` | `real` only if `dod_verified` (gallery + UI artefact) |

Scopes **national / enterprise / domestic** are UI navigation only ([catalog-navigation.json](../shared/catalog-navigation.json)).

## Roles (post 4-rule validation)

| Plane | Owns |
|-------|------|
| **Frigate** | Object detect/track in synced zones; snapshots/clips; `data.box`; `average_estimated_speed` when zone has 4 points + `distances` (m); enter/exit zone membership |
| **Gemini VLM** | Semantic judgment on **Frigate crops only**: cabin yes/no, clear-face gate, plate OCR — never geometry/speed |
| **InsightFace** | Biometric match on Frigate person crop (after clear-face gate). Gemini text watchlist is **not** production `real` |
| **CiteVision bridge** | Emit timing, dedupe, legal thresholds, XOR vs local engines |
| **CiteVision rules-engine** | Conditions → evidence gate → alerts / notifications (never bypassed) |
| **CiteVision local** | Red-light HSV; quality blur/darkness; legacy paths only when corresponding bridge flag is OFF |

## Gamechanger invariants (do not regress)

1. **XOR ownership** — one signal, one factory (no parallel local+Frigate emits).
2. **Compile zones honestly** — UI/DB → `compiler.go` → Frigate YAML (`cv_zone_{uuid}`).
3. **Do not judge too early** — speed @ zone exit + `average_estimated_speed`; evidence waits `end_time` when clip required.
4. **Métier threshold ≠ Frigate filter** — `speed_threshold` stays a low motion filter (default 1); legal limit compared in bridge.
5. **Visual identity = `data.box`** — subject/face/plate crops from Frigate event box aligned to snapshot.
6. **Fail-closed (R.2)** — never fabricate plate/subject/face; use `missing` / `unreadable`.
7. **Rules-engine evidence gate** — suppress alert if package incomplete when policy requires proof.
8. **DoD = gallery + UI** — not MQTT counters (A.3 / R.3).
9. **No parasitic local rules** on specialized zones (cabin/speed).

## Synced to Frigate YAML

- **All** `is_active=true` cameras (no host denylist, no `frigate_exclude`, no virtual skip). Compile failure → `frigate_error` on that camera only.
- Demo virtual camera: rebuilt when upload processing reaches `ready` (and on activate / stream repair), not only on PatchSettings.
- Camera polygons → `cv_zone_{uuid}` coordinates
- Record / snapshots / LPR flags from evidence aggregate
- For `speed_measurement` zones with **exactly 4 vertices** + `edge_distances_m`: Frigate `distances`
- `speed_threshold` written as a **low filter** (default `1`, override via `frigate_speed_threshold`) — **not** the legal limit
- CiteVision bridge compares Frigate `average_estimated_speed` to `speed_limit_kmh` and emits `speeding` **only on zone exit** (`FRIGATE_SPEED_EMIT_MODE=exit`)
- Optional `track_objects` in zone `behavior_config.config` unioned into camera `objects.track`
- `objects.track` includes `person` when cabin/face/presence/perimeter behaviors need it
- `face_recognition.enabled` when org has face watchlist entries / matching rules (`NeedsFaceRecognition`)

## Kill-switches (AI engine)

| Env | Effect |
|-----|--------|
| `FRIGATE_VLM_BRIDGE=1` | Frigate zone events → snapshot crop → Gemini (seatbelt/phone/face gate). Cuts YOLO cabin crop path. |
| `FRIGATE_SPEED_BRIDGE=1` | Frigate `average_estimated_speed` vs limit → `speeding`. Disables local `zone_speed` / CalibrationEngine speed emits. |
| `FRIGATE_GEOMETRY_BRIDGE=1` | Frigate MQTT owns enter/exit/dwell/perimeter/loitering/parking emits. Disables matching local spatial emits. |
| `FRIGATE_SPEED_EMIT_MODE=exit` | Emit speeding only after vehicle leaves the speed zone. |
| `VLM_CABIN_DUMP_DIR` / `VLM_CABIN_RUN` | Persist every cabin Gemini crop+prompt+verdict (YES and NO). |
| `VLM_FACE_DUMP_DIR` | Persist face gate + embedding match artefacts. |
| `GEMINI_ENABLED` + `GEMINI_API_KEY` | Required for VLM / plate OCR Gemini path |

## Evidence

- Prefer Frigate track capture when `frigate_event_id` is present.
- Fail-closed (R.2): no fabricated plate/subject/face; incomplete → `evidence_status=missing` with reason.
- Ring/live remains fallback only when policy allows and Frigate path is absent.

## Catalog honesty

- `catalog_badge=real` **only** when `dod_verified=true` in the orchestration contract (artefact `validate_rule` + gallery).
- Templates without DoD stay `partial` / `requires_external` even if matrix historically said `real`.
- No `full`/`real` claim without DoD (A.4).

## Line crossing policy

- `line_cross*` stays **CiteVision local** (`EventGenerator`) when Frigate lines are not compiled as first-class Frigate zones.
- `FRIGATE_GEOMETRY_BRIDGE` owns zone enter/exit/dwell/perimeter/loitering/parking/counts — it does **not** steal `line_cross`.
- Observation / counting evidence policy: clip often `enabled:false` (`evidence_optional` in `validate_rule`); counters remain valid without a 6 s subject clip.
- If a line is later compiled into Frigate, document XOR explicitly before disabling the local emitter.

## Face / plate XOR

- Face: Frigate person crop → triple vote (Frigate Face Library / InsightFace / Gemini multimodal) with priority Frigate > InsightFace > Gemini. Full-frame InsightFace/Gemini disabled when bridge ON. Enrollment photos sync to Frigate Face Library; compiler enables `face_recognition` when face watchlist/rules exist.
- Plate: single OCR factory on Frigate crops (`plate_ocr` + speeding fusion). Local frame Paddle/Gemini disabled. `plate_blocked` / `plate_allowed` / `plate_unknown` / `plate_repeat` = list/TTL match on `plate_detected` (no re-OCR).

## Composites

- `theft-composite`, `identity-correlation`, `traffic-pipeline`, observation N/OR = **rules-engine sequences** on DoD atoms — see `docs/COMPOSITES-ORCHESTRATION.md`.
