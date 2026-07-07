DROP INDEX IF EXISTS idx_line_counters_org_cam_line_class;

ALTER TABLE rule_counters DROP COLUMN IF EXISTS last_line_id;
ALTER TABLE rule_counters DROP COLUMN IF EXISTS last_zone_id;
ALTER TABLE rule_counters DROP COLUMN IF EXISTS last_class;
ALTER TABLE rule_counters DROP COLUMN IF EXISTS last_event_type;

ALTER TABLE line_counters DROP COLUMN IF EXISTS class_filter;

CREATE UNIQUE INDEX IF NOT EXISTS line_counters_org_id_camera_id_line_id_key
    ON line_counters (org_id, camera_id, line_id);
