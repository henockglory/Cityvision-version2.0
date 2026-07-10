# Frigate integration — CitéVision v2

## Invariant

**zone → IA → règle → preuve** — Frigate is a **media plane** only. Business logic stays in CitéVision DB, rules-engine, and ai-engine analytics.

## ID conventions

| Entity | CitéVision | Frigate |
|--------|------------|---------|
| Camera | UUID | `cv_{uuid}` |
| Zone | UUID | `cv_zone_{uuid}` |

## Camera metadata (JSON)

After sync:

```json
{
  "frigate_camera_id": "cv_d2eb7076-...",
  "frigate_synced_at": "2026-07-09T15:00:00Z",
  "frigate_error": null
}
```

## Feature flags

| Variable | Default | Purpose |
|----------|---------|---------|
| `FRIGATE_ENABLED` | `0` | Master switch |
| `FRIGATE_CONFIG_SYNC` | `0` | DB → generated config |
| `FRIGATE_LIVE` | `0` | Frigate player on `/live` |
| `FRIGATE_EVIDENCE` | `0` | Evidence via Frigate recordings |
| `FRIGATE_EVENTS` | `0` | MQTT adapter (debug only) |
| `FRIGATE_URL` | `http://127.0.0.1:5000` | API base |
| `EVIDENCE_BACKEND` | `ring_buffer` | `ring_buffer` \| `frigate` \| `hybrid` |

## Evidence contract

Input: `EvidencePolicy` from `rule.definition.evidence` (matched by `EvidenceCaptureGate`).

Output: `EvidencePackage` per [shared/schemas/evidence.json](../shared/schemas/evidence.json).

Plate slot (`role=plate`): crop from Frigate snapshot + **PaddleOCR** (ai-engine). Frigate LPR is **live zoom only**.

## Config compiler

Single writer: `backend/internal/frigate` → `infra/frigate-config/config.yml`.

Never edit Frigate YAML by hand in production.

## Baseline (cam 108)

Run before/after integration:

```bash
python3 scripts/audit_evidence_quality.py --limit 20
python3 scripts/frigate_baseline.py
```
