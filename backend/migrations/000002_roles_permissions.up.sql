CREATE TABLE roles (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    code        TEXT NOT NULL UNIQUE,
    name        TEXT NOT NULL,
    description TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE permissions (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    code        TEXT NOT NULL UNIQUE,
    description TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE role_permissions (
    role_id         UUID NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
    permission_id   UUID NOT NULL REFERENCES permissions(id) ON DELETE CASCADE,
    PRIMARY KEY (role_id, permission_id)
);

INSERT INTO roles (code, name, description) VALUES
    ('super_admin', 'Super Administrateur', 'Accès global, configuration système'),
    ('org_admin', 'Administrateur organisation', 'Gestion complète du tenant'),
    ('operator', 'Opérateur', 'Surveillance live, acquittement alertes'),
    ('analyst', 'Analyste', 'Recherche, replay, rapports'),
    ('supervisor', 'Superviseur', 'Validation alertes, gestion équipe'),
    ('viewer', 'Lecteur seul', 'Consultation lecture seule'),
    ('technician', 'Profil technique', 'Santé système, caméras, logs');

INSERT INTO permissions (code, description) VALUES
    ('cameras:read', 'View cameras'),
    ('cameras:write', 'Manage cameras'),
    ('cameras:ptz', 'Control PTZ'),
    ('zones:read', 'View zones'),
    ('zones:write', 'Manage zones'),
    ('rules:read', 'View rules'),
    ('rules:write', 'Manage rules'),
    ('rules:simulate', 'Simulate rules'),
    ('alerts:read', 'View alerts'),
    ('alerts:ack', 'Acknowledge alerts'),
    ('alerts:export', 'Export alerts'),
    ('events:read', 'View events'),
    ('events:search', 'Search events'),
    ('users:read', 'View users'),
    ('users:write', 'Manage users'),
    ('audit:read', 'View audit logs'),
    ('system:health', 'System health'),
    ('system:config', 'System configuration');

INSERT INTO role_permissions (role_id, permission_id)
SELECT r.id, p.id FROM roles r CROSS JOIN permissions p WHERE r.code = 'super_admin';

INSERT INTO role_permissions (role_id, permission_id)
SELECT r.id, p.id FROM roles r, permissions p
WHERE r.code = 'org_admin' AND p.code IN (
    'cameras:read','cameras:write','cameras:ptz','zones:read','zones:write',
    'rules:read','rules:write','rules:simulate','alerts:read','alerts:ack','alerts:export',
    'events:read','events:search','users:read','users:write','audit:read','system:health'
);

INSERT INTO role_permissions (role_id, permission_id)
SELECT r.id, p.id FROM roles r, permissions p
WHERE r.code = 'operator' AND p.code IN (
    'cameras:read','cameras:ptz','zones:read','rules:read','alerts:read','alerts:ack',
    'events:read','system:health'
);

INSERT INTO role_permissions (role_id, permission_id)
SELECT r.id, p.id FROM roles r, permissions p
WHERE r.code = 'analyst' AND p.code IN (
    'cameras:read','zones:read','rules:read','alerts:read','alerts:export',
    'events:read','events:search','audit:read'
);

INSERT INTO role_permissions (role_id, permission_id)
SELECT r.id, p.id FROM roles r, permissions p
WHERE r.code = 'supervisor' AND p.code IN (
    'cameras:read','cameras:ptz','zones:read','rules:read','alerts:read','alerts:ack','alerts:export',
    'events:read','events:search','users:read','system:health'
);

INSERT INTO role_permissions (role_id, permission_id)
SELECT r.id, p.id FROM roles r, permissions p
WHERE r.code = 'viewer' AND p.code IN (
    'cameras:read','zones:read','events:read','alerts:read','system:health'
);

INSERT INTO role_permissions (role_id, permission_id)
SELECT r.id, p.id FROM roles r, permissions p
WHERE r.code = 'technician' AND p.code IN (
    'cameras:read','cameras:write','system:health','audit:read'
);
