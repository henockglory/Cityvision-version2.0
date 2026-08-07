# Frigate sync — honesty bounds (Frigate-primary + Gemini)

## Roles (post-refonte 1a / 2b)

| Plane | Owns |
|-------|------|
| **Frigate** | Object detect/track in synced zones; snapshots/clips; **estimated speed** when zone has 4 points + `distances` (m) |
| **Gemini VLM** | Cabin judgment (seatbelt / phone), face presence, plate OCR — on Frigate crops only when bridges ON |
| **CiteVision rules-engine** | Conditions → evidence gate → alerts / notifications (never bypassed) |
| **CiteVision local** | Red-light HSV (+ YOLO tracks); legacy `zone_speed` only when `FRIGATE_SPEED_BRIDGE=0` |

## Synced to Frigate YAML

- Camera polygons → `cv_zone_{uuid}` coordinates
- Record / snapshots / LPR flags from evidence aggregate
- For `speed_measurement` zones with **exactly 4 vertices** + `edge_distances_m`: Frigate `distances`
- **`speed_limit_kmh`** (UI legal limit) is synced into Frigate zone `speed_threshold` as a **filter** (objects below limit are less likely to score in-zone). Explicit `frigate_speed_threshold` still overrides when set.
- CiteVision bridge still **compares** Frigate `average_estimated_speed` to `speed_limit_kmh` and emits `speeding` **only on zone exit** (`FRIGATE_SPEED_EMIT_MODE=exit`).
- Optional `track_objects` in zone `behavior_config.config` (e.g. `["car","motorcycle","bus","person"]`) is unioned into camera `objects.track`
- `objects.track` may include `person` when cabin/face zones need it

## Not synced as métier judgment

- Frigate does **not** create UI alerts. It estimates km/h; CiteVision bridge decides the `speeding` event; rules-engine owns alert persistence.
- Red-light HSV ROIs / traffic-light color rules stay CiteVision-only.
- Alert emission stays rules-engine only (Frigate MQTT never creates UI alerts).

## Kill-switches (AI engine)

| Env | Effect |
|-----|--------|
| `FRIGATE_VLM_BRIDGE=1` | Frigate zone events → snapshot crop → Gemini (seatbelt/phone/face). Cuts YOLO cabin crop path. |
| `FRIGATE_SPEED_BRIDGE=1` | Frigate `average_estimated_speed` vs limit → `speeding`. Disables local `zone_speed` on those cams. |
| `FRIGATE_SPEED_EMIT_MODE=exit` | Emit speeding only after vehicle leaves the speed zone (default for validation). |
| `VLM_CABIN_DUMP_DIR` / `VLM_CABIN_RUN` | Persist every cabin Gemini crop+prompt+verdict (YES and NO) under `validation-evidence/vlm-cabin-<run>/`. |
| `GEMINI_ENABLED` + `GEMINI_API_KEY` | Required for VLM / plate OCR Gemini path |

## Evidence

- Road + Frigate-triggered cabin/identity: prefer Frigate track capture when `frigate_event_id` is present.
- Fail-closed (R.2): no fabricated plate/subject; incomplete → `evidence_status=missing` with reason.
- Ring/live remains fallback only when policy allows and Frigate path is absent.

## Catalog honesty

Cabin / face / plate / Frigate-speed templates stay **`partial` / `requires_external`** until `validate_rule` artefacts exist. No `full`/`real` claim without DoD.
