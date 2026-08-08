# Fill install boot gaps — living checklist

Source of truth for install/boot honesty (R.1 native WSL `~/citevision-v2`).
Do **not** claim face catalogue `real` / DoD 5/5 until `validate_rule` artefacts exist (A.4).

## Done

| Item | Notes |
|------|--------|
| Lanceurs / watchdog PS1 | `;` not `&&`; refuse `/mnt` runtime; ASCII messages |
| `Resolve-CiteVisionWslRoot.ps1` | `$env:CITEVISION_WSL_ROOT` or `$HOME/citevision-v2`; probe `scripts/start-linux.sh` |
| Start/Stop/Heal / start-windows / stop-windows / watchdog / install-startup | Rewired to resolver (no `/home/gheno` hardcode) |
| NSSM `install-service.ps1` | AppParameters use **native** WSL root (never `ConvertTo-WslPath` → `/mnt/c/...`) |
| `bootstrap.ps1` | Sync via `sync-to-wsl.sh` when runtime missing; writes `.wsl_runtime_ready`; ASCII |
| Heal go2rtc | `scripts/lib/start-full-stack.sh` + `scripts/health_check_all.sh` |
| InsightFace models | `ensure-ai-stack` / `install-ai-models` |
| Face enroll product path | UI Settings → photo enroll → InsightFace + Frigate Face Library |
| Compiler `face_recognition` | Enabled when `NeedsFaceRecognition` / watchlist |
| Gemini client runtime | Key restore from `~/.citevision_gemini_key.tmp` via `ensure_demo_validation_env` |
| Frigate sync permanent | Defaults `FRIGATE_ENABLED` + `FRIGATE_CONFIG_SYNC` true; no policy exclusions |
| Demo upload → Frigate | `demo.Service.SetFrigateRebuild` after virtual cam ready |
| `scripts/check-ps1-ps51-safe.sh` | Guard first-party PS 5.1 (`&&`, non-ASCII, `/mnt` runtime) |
| Vendor `*.ps1` | Marked FROZEN — not on CiteVision v2 install path |

## Remaining (ops / human)

| Item | Notes |
|------|--------|
| Gemini key on target machine | Place key in `~/.citevision_gemini_key.tmp` or `.env` (never git) |
| Face enroll smoke | Post-install: Settings → watchlist photo; optional non-blocking |
| `STRICT_INSTALL_HEALTH=1` | Optional CI: upgrades gemini/face WARN → FAIL in `health_check_all` |
| `validate_rule` face | Catalogue stays `partial` until DoD artefact |

## Post-install checklist

1. Runtime = native WSL `~/citevision-v2` (not `/mnt/c/...`).
2. `bash scripts/health_check_all.sh` (optionally `STRICT_INSTALL_HEALTH=1`).
3. Frigate flags on in `.env` (`FRIGATE_ENABLED=1`, `FRIGATE_CONFIG_SYNC=1`).
4. Gemini keyfile present if cabin/face VLM required.
5. InsightFace models installed (`face_loaded` on AI `/health`).
6. Face enroll via **UI Settings** (not scripts).
7. Docker Desktop **forbidden** — native WSL dockerd only.

## Smoke evidence (this chantier)

- `go test ./internal/frigate/ ./internal/demo/` + `go build ./cmd/api` OK
- `scripts/check-ps1-ps51-safe.sh` OK (first-party)
- Frigate `config.yml` contains multiple `cv_*` cameras (no policy exclusions)
- Health: ghost `face.py` absent; face_recognition optional while watchlist empty
- Demo upload → Frigate: wired via `demo.Service.SetFrigateRebuild` (unit-tested); PatchSettings still syncs

