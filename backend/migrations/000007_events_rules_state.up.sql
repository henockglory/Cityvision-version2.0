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

CREATE TABLE state_snapshots (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id      UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    site_id     UUID REFERENCES sites(id) ON DELETE SET NULL,
    entity_type TEXT NOT NULL,
    entity_id   TEXT NOT NULL,
    state       JSONB NOT NULL DEFAULT '{}',
    version     BIGINT NOT NULL DEFAULT 1,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (org_id, entity_type, entity_id)
);

CREATE TABLE correlation_rules (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id      UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    name        TEXT NOT NULL,
    definition  JSONB NOT NULL DEFAULT '{}',
    is_enabled  BOOLEAN NOT NULL DEFAULT FALSE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_events_org_time ON events (org_id, occurred_at DESC);
CREATE INDEX idx_events_type ON events (event_type);
CREATE INDEX idx_rules_org ON rules (org_id);
