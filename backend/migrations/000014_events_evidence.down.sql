ALTER TABLE events DROP COLUMN IF EXISTS evidence_snapshot;
DROP INDEX IF EXISTS idx_events_evidence_nonempty;
