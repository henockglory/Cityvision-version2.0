# AUDIT-INTEGRATION-CATALOGUE — 20260807T072926Z

Generated: `2026-08-07T07:40:01.349041+00:00`
Audit dir: `validation-evidence/audit-integration/20260807T072926Z/`

## Verdict global: **PARTIAL**

This is an **integration audit**, not a refonte. No catalog badge was promoted. No claim of 53/53 `real`.

### Gate A0 (non-régression 4 règles)

- Code anti-degrade: **PASS** (protected events absent from geometry skip: True)
- Stack at A0 start: **RED** → overall A0 **PARTIAL_STACK_DOWN**
- Live `validate_rule` of the 4 was **not** re-executed while Frigate/AI were down at audit start.
- Existing artefacts: formal DoD PASS found primarily for `red_light`; speed/cabin rely on `1hit-*` galleries.

### Honesty gap (CLAIM_AHEAD_OF_ARTIFACT)

- Contract `dod_verified`/`real` count: **4** → `['tpl-seatbelt', 'tpl-speeding-premium', 'tpl-red-light', 'tpl-phone-driving']`
- Templates with claim ahead of formal validate_rule PASS: **3**

### Phase summaries

| Phase | Verdict |
|---|---|
| A0 baseline | `PARTIAL_STACK_DOWN` |
| A1 contract/UI | `PASS` |
| A2 XOR/wiring/units | `WIRED` (pytest exit 0) |
| A3 archetypes | `WIRED_STATIC` |
| A4 DoD matrix | `PARTIAL` — {'total': 53, 'pass': 1, 'partial': 52, 'fail': 0, 'claim_ahead': 3} |
| A5 live RTSP | `PARTIAL` |

### Refonte todo → audit status

| Refonte todo | Phase | Audit status | Notes |
|---|---|---|---|
| `p0-contract-schema` | A1 | **PASS** | Contract schema loaded; docs present |
| `p0-matrix-fill` | A1 | **PASS** | 53 templates |
| `p0-ui-badges` | A1 | **PASS** | UI requires dod_verified+real |
| `p0-contract-tests` | A1 | **PASS** | go test ./internal/rules/ |
| `p1-geometry-flag-xor` | A2 | **WIRED** | geometry_enabled + skip set |
| `p1-bridge-enter-exit` | A3 | **WIRED** |  |
| `p1-bridge-dwell` | A3 | **WIRED** |  |
| `p1-bridge-absence-counts` | A3 | **WIRED** |  |
| `p1-lines-policy` | A3 | **WIRED** | line_cross not stolen |
| `p1-evidence-geom` | A4 | **PARTIAL** | wired; live evidence chain not re-run this session |
| `p1-validate-geom` | A3 | **PARTIAL** | scaffold PARTIAL only — no live PASS gallery |
| `p1-intrusion-bindings` | A3 | **PARTIAL** | catalog bindings present; live not exercised |
| `p2-face-xor-crop` | A2 | **WIRED** | face XOR + match_jpeg |
| `p2-face-pipeline` | A3 | **WIRED** |  |
| `p2-face-audit-evidence` | A3 | **PARTIAL** | dump path exists; no live face gallery PASS |
| `p2-face-validate` | A3 | **PARTIAL** | scaffold face-detected PARTIAL |
| `p3-plate-single-factory` | A2/A3 | **WIRED** | XOR wired |
| `p3-plate-list-rules` | A2 | **WIRED** |  |
| `p3-plate-validate` | A3 | **PARTIAL** | scaffold plate-detected PARTIAL |
| `p4-speed-variants` | A3 | **WIRED** |  |
| `p4-parking-pedestrian` | A3 | **WIRED** | pedestrian method present |
| `p4-proximity-multiperson` | A3 | **WIRED** |  |
| `p4-validate-road-sec` | A2 | **PARTIAL** | unit slow/geometry OK; live gallery not run |
| `p5-abandoned-objects` | A3 | **WIRED** |  |
| `p5-quality-local` | A3 | **WIRED** |  |
| `p6-composites` | A3 | **DOCUMENTED_PARTIAL** | docs only — atoms DoD incomplete |
| `p7-validate-matrix` | A4 | **PARTIAL** | matrix summary {'total': 53, 'pass': 1, 'partial': 52, 'fail': 0, 'claim_ahead': 3} |
| `p7-live-rtsp-checklist` | A5 | **PARTIAL** | frigate=200 ai=None |
| `p7-catalog-honesty` | A1 | **PARTIAL** | claim_ahead=3 — 3 of 4 dod_verified lack formal validate_rule PASS |

### Gamechanger invariants (spot-check)

| Secret | Result |
|---|---|
| XOR geometry/speed/face/plate | **OK** (A2 `WIRED`) |
| Frigate box/speed ownership | **OK** wired (methods present) |
| Gemini crop-only for cabin/face | **OK** path present; live not re-audited |
| Fail-closed R.2 signals in evidence code | **{'missing_status_mentioned': True, 'no_fabricate_comment_or_logic': True}** |
| DoD = gallery+UI not MQTT | **PARTIAL** — only 1 formal validate_rule PASS on disk |
| No parasitic geometry steal of speed/cabin/red | **OK** (A0) |

### What was NOT done (by design)

- No zone hardcoding / DB geometry writes
- No badge `partial→real` promotion
- No claim « catalogue entièrement validé »
- No full live 1-hit campaign for geometry/face/plate (stack AI down; scaffolds only)

### Recommended next steps (outside this audit)

1. Bring AI engine up; re-run `validate_rule` for speeding/seatbelt/phone to close CLAIM_AHEAD gaps or demote contract `dod_verified` until PASS exists.
2. With demo zones already in UI, run isolated live smokes for perimeter/presence/plate under `FORCE_LIVE_DOD=1`.
3. Only then consider badge promotion — never from this audit alone.

### Artefacts

- `validation-evidence/audit-integration/20260807T072926Z/A0-baseline.json`
- `.../A1-contract-ui.json`
- `.../A2-xor-wiring.json`
- `.../A3-archetypes.json`
- `.../A4-matrix-audit.json` / `matrix-audit.json`
- `.../A5-live-rtsp.json`
- `docs/AUDIT-INTEGRATION-CATALOGUE-20260807T072926Z.md`
