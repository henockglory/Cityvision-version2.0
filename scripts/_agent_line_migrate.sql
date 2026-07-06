\pset border 2
-- [C.27] apply migration idempotently
ALTER TABLE lines ADD COLUMN IF NOT EXISTS behavior_config JSONB NOT NULL DEFAULT '{}'::jsonb;
UPDATE lines
SET behavior_config = jsonb_build_object(
        'behavior', 'line_cross',
        'config', jsonb_build_object('class_filter', 'any', 'direction', COALESCE(direction, 'both'))
    )
WHERE behavior_config = '{}'::jsonb OR behavior_config IS NULL;

\echo '=== lines present ==='
SELECT name, direction, behavior_config FROM lines;
