CREATE TYPE alert_status AS ENUM ('open', 'acknowledged', 'resolved', 'suppressed');
CREATE TYPE incident_status AS ENUM ('open', 'investigating', 'resolved', 'closed');

CREATE TABLE alerts (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id          UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    site_id         UUID REFERENCES sites(id) ON DELETE SET NULL,
    rule_id         UUID REFERENCES rules(id) ON DELETE SET NULL,
    event_id        UUID REFERENCES events(id) ON DELETE SET NULL,
    title           TEXT NOT NULL,
    message         TEXT,
    severity        event_severity NOT NULL DEFAULT 'medium',
    status          alert_status NOT NULL DEFAULT 'open',
    metadata        JSONB NOT NULL DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE incidents (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id          UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    site_id         UUID REFERENCES sites(id) ON DELETE SET NULL,
    title           TEXT NOT NULL,
    description     TEXT,
    status          incident_status NOT NULL DEFAULT 'open',
    severity        event_severity NOT NULL DEFAULT 'high',
    assigned_to     UUID REFERENCES users(id) ON DELETE SET NULL,
    metadata        JSONB NOT NULL DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    resolved_at     TIMESTAMPTZ
);

CREATE INDEX idx_alerts_org_status ON alerts (org_id, status);
CREATE INDEX idx_incidents_org ON incidents (org_id, status);
