ALTER TABLE org_demo_settings DROP CONSTRAINT IF EXISTS org_demo_settings_active_video_fk;
DROP INDEX IF EXISTS idx_events_demo;
DROP INDEX IF EXISTS idx_org_demo_videos_org;
DROP TABLE IF EXISTS org_demo_videos;
DROP TABLE IF EXISTS org_demo_settings;
