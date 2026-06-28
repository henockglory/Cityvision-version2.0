ALTER TABLE org_demo_settings
    ADD COLUMN IF NOT EXISTS nav_label TEXT NOT NULL DEFAULT 'Démo Kinshasa';

UPDATE org_demo_settings SET nav_label = 'Démo Kinshasa' WHERE nav_label = '' OR nav_label IS NULL;
