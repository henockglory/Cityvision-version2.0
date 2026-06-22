CREATE TABLE IF NOT EXISTS surveillance_lists (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id      UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    name        TEXT NOT NULL,
    list_type   TEXT NOT NULL CHECK (list_type IN ('face_watchlist', 'plate_block', 'plate_allow')),
    entries     JSONB NOT NULL DEFAULT '[]',
    is_active   BOOLEAN NOT NULL DEFAULT TRUE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_surveillance_lists_org ON surveillance_lists (org_id);
CREATE UNIQUE INDEX idx_surveillance_lists_org_name ON surveillance_lists (org_id, name);
