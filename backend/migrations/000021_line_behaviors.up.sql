-- Rich, extensible AI behavior configuration per line (mirrors zones.behavior_config).
-- behavior_config holds: { "behavior": "<id>", "config": { "class_filter": "...", ... } }
-- Lets a counting line own its class_filter / direction as the single source of truth ([C.27]/[C.30]).
ALTER TABLE lines ADD COLUMN IF NOT EXISTS behavior_config JSONB NOT NULL DEFAULT '{}'::jsonb;

-- Backfill: existing lines are counting lines. Keep any configured direction.
UPDATE lines
SET behavior_config = jsonb_build_object(
        'behavior', 'line_cross',
        'config', jsonb_build_object(
            'class_filter', 'any',
            'direction', COALESCE(direction, 'both')
        )
    )
WHERE behavior_config = '{}'::jsonb OR behavior_config IS NULL;
