ALTER TABLE alerts
    DROP COLUMN IF EXISTS evidence_snapshot,
    DROP COLUMN IF EXISTS archive_comment,
    DROP COLUMN IF EXISTS archived_by,
    DROP COLUMN IF EXISTS archived_at;
