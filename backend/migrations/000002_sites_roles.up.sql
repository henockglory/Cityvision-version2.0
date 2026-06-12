CREATE TYPE user_role AS ENUM (
    'super_admin',
    'org_admin',
    'operator',
    'analyst',
    'supervisor',
    'viewer',
    'technician'
);

CREATE TABLE sites (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id      UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    name        TEXT NOT NULL,
    slug        TEXT NOT NULL,
    timezone    TEXT NOT NULL DEFAULT 'UTC',
    address     TEXT,
    is_active   BOOLEAN NOT NULL DEFAULT TRUE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (org_id, slug)
);

CREATE TABLE org_memberships (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id      UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    user_id     UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role        user_role NOT NULL DEFAULT 'viewer',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (org_id, user_id)
);

CREATE TABLE site_assignments (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    site_id     UUID NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
    user_id     UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role        user_role NOT NULL DEFAULT 'viewer',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (site_id, user_id)
);

CREATE INDEX idx_sites_org ON sites (org_id);
CREATE INDEX idx_org_memberships_user ON org_memberships (user_id);
