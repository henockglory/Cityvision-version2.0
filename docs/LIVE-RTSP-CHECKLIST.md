# Live RTSP checklist (Frigate-primary)

Runtime truth: WSL `~/citevision-v2`. Docker Desktop forbidden.

## Boot

- Start: `bash scripts/lib/start-full-stack.sh` (via `scripts/start-linux.sh` or `launcher/Start-CiteVision.ps1`). Refuses `/mnt/c` roots.
- Env: `ensure_demo_validation_env` upserts `FRIGATE_VLM_BRIDGE`, `FRIGATE_SPEED_BRIDGE`, `FRIGATE_GEOMETRY_BRIDGE=1`, `FRIGATE_SPEED_EMIT_MODE=exit`.
- Health: `bash scripts/health_check_all.sh` auto-heals Frigate (compose `--profile frigate`), AI uvicorn if count=0, and bridge flags (upsert `.env` + one AI restart). Missing geometry+speed after heal → **FAIL**.

## Preflight

1. `bash scripts/health_check_all.sh` — green.
2. go2rtc streams healthy for the camera RTSP source.
3. Frigate `/api/stats` — camera FPS > 0, detectors OK.
4. Backend zone sync → Frigate config has `cv_zone_<uuid>` for ZoneEditor polygons (no hardcoded geometry).
5. Camera `objects.track` includes required labels (`person`, vehicles) from zone behaviors / `track_objects`.
6. Rules enabled (`is_enabled`) for the demo/org camera — no silent pause (A.8).
7. Rules-engine sync count > 0 for the org.

## Bridge flags (AI `/health`)

| Key | Expect (Frigate-primary) |
|-----|--------------------------|
| `frigate_vlm_bridge` | true when cabin/face/plate Gemini path used |
| `frigate_speed_bridge` | true |
| `frigate_geometry_bridge` | true |
| `frigate_bridge_geometry_emitted` | increases on enter/dwell traffic |
| `frigate_bridge_speed_emitted` | increases on speed exits over limit |
| `gemini_configured` | true if VLM required |
| face/OCR providers | GPU preferred (A.5) |

## Evidence / mail

- Policy: scene + subject + clip 6 s (+ plate if road); fail-closed missing reasons (R.2).
- Mailhog (`:8025`) receives premium mail when channel configured.
- DoD: `bash scripts/validate_rule.sh <alias>` + UI capture `:5174` — not MQTT logs alone (A.3 / R.3).

## Bridge health_check hook

`scripts/health_check_all.sh` upserts bridges then **FAIL**s if AI `/health` still lacks `frigate_geometry_bridge` or `frigate_speed_bridge` after one restart (Frigate-primary).
