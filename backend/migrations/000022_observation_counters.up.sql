-- Observation counters: per-class line tallies + rule counter display metadata.

ALTER TABLE line_counters ADD COLUMN IF NOT EXISTS class_filter TEXT NOT NULL DEFAULT '';

-- Replace unique constraint to include class_filter (global '' + per-class rows).
ALTER TABLE line_counters DROP CONSTRAINT IF EXISTS line_counters_org_id_camera_id_line_id_key;
CREATE UNIQUE INDEX IF NOT EXISTS idx_line_counters_org_cam_line_class
    ON line_counters (org_id, camera_id, line_id, class_filter);

ALTER TABLE rule_counters ADD COLUMN IF NOT EXISTS last_event_type TEXT NOT NULL DEFAULT '';
ALTER TABLE rule_counters ADD COLUMN IF NOT EXISTS last_class TEXT NOT NULL DEFAULT '';
ALTER TABLE rule_counters ADD COLUMN IF NOT EXISTS last_zone_id TEXT NOT NULL DEFAULT '';
ALTER TABLE rule_counters ADD COLUMN IF NOT EXISTS last_line_id TEXT NOT NULL DEFAULT '';
