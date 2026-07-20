ALTER TABLE organizations
    DROP COLUMN IF EXISTS smtp_config,
    DROP COLUMN IF EXISTS security_prefs,
    DROP COLUMN IF EXISTS notification_prefs,
    DROP COLUMN IF EXISTS logo_url,
    DROP COLUMN IF EXISTS timezone;

ALTER TABLE users DROP COLUMN IF EXISTS locale;
