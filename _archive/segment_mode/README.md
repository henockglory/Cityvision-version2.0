# Segment mode (archived — Sprint 4)

Abandoned RECORD→PROCESS segment ingest. Live path is **RTSP + Frigate evidence**.

| File | Notes |
|------|--------|
| `segment_cycle_worker.py` | Full historical worker |
| Active stub | `ai-engine/.../ingest/segment_cycle_worker.py` raises on construct |

Helpers still in the package but gated by empty `SEGMENT_MODE_CAMERA_IDS`:

- `evidence/segment_align.py`
- `evidence/segment_replay_cache.py`
- `pipeline` / `evidence.service` segment branches

Do not re-enable without an explicit product decision.
