CREATE TABLE audit_log (
    id              BIGSERIAL PRIMARY KEY,
    org_id          UUID REFERENCES organizations(id) ON DELETE SET NULL,
    user_id         UUID REFERENCES users(id) ON DELETE SET NULL,
    action          TEXT NOT NULL,
    resource_type   TEXT NOT NULL,
    resource_id     TEXT,
    ip_address      INET,
    user_agent      TEXT,
    payload         JSONB NOT NULL DEFAULT '{}',
    prev_hash       TEXT NOT NULL DEFAULT '',
    entry_hash      TEXT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_audit_log_org ON audit_log (org_id, created_at DESC);
CREATE INDEX idx_audit_log_user ON audit_log (user_id, created_at DESC);
