ALTER TYPE alert_status ADD VALUE IF NOT EXISTS 'archived';

ALTER TABLE alerts
    ADD COLUMN IF NOT EXISTS archived_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS archived_by UUID REFERENCES users(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS archive_comment TEXT,
    ADD COLUMN IF NOT EXISTS evidence_snapshot JSONB NOT NULL DEFAULT '{}';

CREATE INDEX IF NOT EXISTS idx_alerts_org_archived ON alerts (org_id, archived_at DESC);
