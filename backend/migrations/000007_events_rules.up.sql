CREATE TYPE event_severity AS ENUM ('info', 'low', 'medium', 'high', 'critical');

CREATE TABLE events (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id          UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    site_id         UUID REFERENCES sites(id) ON DELETE SET NULL,
    camera_id       UUID REFERENCES cameras(id) ON DELETE SET NULL,
    event_type      TEXT NOT NULL,
    severity        event_severity NOT NULL DEFAULT 'info',
    payload         JSONB NOT NULL DEFAULT '{}',
    occurred_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ingested_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE rules (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id      UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    site_id     UUID REFERENCES sites(id) ON DELETE SET NULL,
    name        TEXT NOT NULL,
    description TEXT,
    definition  JSONB NOT NULL,
    is_enabled  BOOLEAN NOT NULL DEFAULT TRUE,
    priority    INT NOT NULL DEFAULT 0,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_events_org_time ON events (org_id, occurred_at DESC);
CREATE INDEX idx_events_type ON events (event_type);
CREATE INDEX idx_rules_org ON rules (org_id);
CREATE INDEX idx_rules_org_enabled ON rules (org_id, is_enabled) WHERE is_enabled = TRUE;
