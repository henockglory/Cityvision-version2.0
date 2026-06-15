ALTER TABLE organizations
    ADD COLUMN IF NOT EXISTS timezone TEXT NOT NULL DEFAULT 'Africa/Kinshasa',
    ADD COLUMN IF NOT EXISTS logo_url TEXT,
    ADD COLUMN IF NOT EXISTS notification_prefs JSONB NOT NULL DEFAULT '{}',
    ADD COLUMN IF NOT EXISTS security_prefs JSONB NOT NULL DEFAULT '{"min_password_length":12,"require_2fa_admins":false,"session_timeout_minutes":480}',
    ADD COLUMN IF NOT EXISTS smtp_config JSONB NOT NULL DEFAULT '{}';

ALTER TABLE users
    ADD COLUMN IF NOT EXISTS locale TEXT NOT NULL DEFAULT 'fr';
