CREATE TABLE IF NOT EXISTS rule_counters (
    org_id    UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    rule_id   UUID NOT NULL REFERENCES rules(id) ON DELETE CASCADE,
    count     BIGINT NOT NULL DEFAULT 0,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (org_id, rule_id)
);

CREATE INDEX IF NOT EXISTS idx_rule_counters_org ON rule_counters(org_id);
