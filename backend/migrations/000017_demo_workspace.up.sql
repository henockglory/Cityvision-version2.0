CREATE TABLE IF NOT EXISTS org_demo_settings (
    org_id UUID PRIMARY KEY REFERENCES organizations(id) ON DELETE CASCADE,
    context_label TEXT NOT NULL DEFAULT '',
    title TEXT NOT NULL DEFAULT '',
    subtitle TEXT NOT NULL DEFAULT '',
    active_video_id UUID,
    active_camera_id UUID REFERENCES cameras(id) ON DELETE SET NULL,
    source_mode TEXT NOT NULL DEFAULT 'video',
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS org_demo_videos (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    name TEXT NOT NULL DEFAULT 'Vidéo de test',
    status TEXT NOT NULL DEFAULT 'uploading',
    progress INT NOT NULL DEFAULT 0,
    minio_raw_key TEXT,
    minio_stream_key TEXT,
    go2rtc_src TEXT,
    local_stream_path TEXT,
    size_bytes BIGINT NOT NULL DEFAULT 0,
    duration_sec DOUBLE PRECISION,
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_org_demo_videos_org ON org_demo_videos(org_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_events_demo ON events(org_id, event_type, ingested_at DESC)
    WHERE (payload->>'demo') = 'true';

ALTER TABLE org_demo_settings
    ADD CONSTRAINT org_demo_settings_active_video_fk
    FOREIGN KEY (active_video_id) REFERENCES org_demo_videos(id) ON DELETE SET NULL;
