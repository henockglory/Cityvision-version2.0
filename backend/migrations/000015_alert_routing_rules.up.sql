CREATE TABLE IF NOT EXISTS alert_routing_rules (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id      UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    name        TEXT NOT NULL,
    enabled     BOOLEAN NOT NULL DEFAULT TRUE,
    priority    INT NOT NULL DEFAULT 100,
    match       JSONB NOT NULL DEFAULT '{}',
    channels    JSONB NOT NULL DEFAULT '{}',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_alert_routing_rules_org ON alert_routing_rules (org_id);
CREATE INDEX idx_alert_routing_rules_org_priority ON alert_routing_rules (org_id, priority ASC);
