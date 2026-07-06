-- Rich, extensible AI behavior configuration per zone.
-- behavior_config holds: { "behavior": "<id>", "config": { ... } }
-- where <id> is one of the entries in shared/zone-behaviors.json.
-- zone_kind is kept for backward compatibility; behavior supersedes it when set.
ALTER TABLE zones ADD COLUMN IF NOT EXISTS behavior_config JSONB NOT NULL DEFAULT '{}'::jsonb;

-- Backfill behavior_config from legacy zone_kind so existing zones keep working.
UPDATE zones
SET behavior_config = jsonb_build_object('behavior', zone_kind)
WHERE (behavior_config = '{}'::jsonb OR behavior_config IS NULL)
  AND zone_kind <> '';
