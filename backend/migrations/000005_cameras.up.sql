CREATE TYPE camera_vendor AS ENUM ('dahua', 'hikvision', 'generic');
CREATE TYPE camera_status AS ENUM ('online', 'offline', 'unknown', 'error');

CREATE TABLE cameras (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id              UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    site_id             UUID NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
    name                TEXT NOT NULL,
    vendor              camera_vendor NOT NULL DEFAULT 'generic',
    host                INET NOT NULL,
    port                INT NOT NULL DEFAULT 554,
    channel             INT NOT NULL DEFAULT 1,
    username            TEXT,
    password_encrypted  BYTEA,
    rtsp_path           TEXT,
    stream_profile      TEXT NOT NULL DEFAULT 'main',
    status              camera_status NOT NULL DEFAULT 'unknown',
    metadata            JSONB NOT NULL DEFAULT '{}',
    is_active           BOOLEAN NOT NULL DEFAULT TRUE,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_cameras_org ON cameras (org_id);
CREATE INDEX idx_cameras_site ON cameras (site_id);
