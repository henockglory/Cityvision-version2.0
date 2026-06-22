ALTER TABLE events
    ADD COLUMN IF NOT EXISTS evidence_snapshot JSONB NOT NULL DEFAULT '{}';

CREATE INDEX IF NOT EXISTS idx_events_evidence_nonempty
    ON events ((evidence_snapshot != '{}'::jsonb))
    WHERE evidence_snapshot != '{}'::jsonb;
