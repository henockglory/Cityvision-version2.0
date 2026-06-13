CREATE TABLE zones (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id      UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    site_id     UUID NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
    camera_id   UUID REFERENCES cameras(id) ON DELETE SET NULL,
    name        TEXT NOT NULL,
    polygon     JSONB NOT NULL,
    color       TEXT NOT NULL DEFAULT '#FF5733',
    is_active   BOOLEAN NOT NULL DEFAULT TRUE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE lines (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id      UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    site_id     UUID NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
    camera_id   UUID REFERENCES cameras(id) ON DELETE SET NULL,
    name        TEXT NOT NULL,
    start_point JSONB NOT NULL,
    end_point   JSONB NOT NULL,
    direction   TEXT,
    is_active   BOOLEAN NOT NULL DEFAULT TRUE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_zones_site ON zones (site_id);
CREATE INDEX idx_lines_site ON lines (site_id);
