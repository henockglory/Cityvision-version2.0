CREATE TABLE IF NOT EXISTS plate_patterns (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id       UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    name         TEXT NOT NULL,
    mode         TEXT NOT NULL DEFAULT 'custom' CHECK (mode IN ('standard', 'custom')),
    composition  JSONB NOT NULL DEFAULT '[]',
    regex        TEXT NOT NULL DEFAULT '',
    is_default   BOOLEAN NOT NULL DEFAULT FALSE,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_plate_patterns_org ON plate_patterns (org_id);
CREATE UNIQUE INDEX idx_plate_patterns_org_name ON plate_patterns (org_id, name);

-- At most one default per org.
CREATE UNIQUE INDEX idx_plate_patterns_org_default
  ON plate_patterns (org_id)
  WHERE is_default = TRUE;
