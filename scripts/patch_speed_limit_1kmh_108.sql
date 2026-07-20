-- Force speed limit 1 km/h for camera 108 test (user-requested).
UPDATE zones
SET behavior_config = jsonb_set(
  COALESCE(behavior_config, '{}'::jsonb),
  '{config,speed_limit_kmh}',
  '1'::jsonb,
  true
),
updated_at = NOW()
WHERE camera_id = '37c7d7fa-12dc-450c-8c4b-ab63ed43a819'
  AND name = 'Zone_distance_parcourue_108';

UPDATE rules
SET definition = jsonb_set(
  definition,
  '{bindings,speed_kmh}',
  '1'::jsonb,
  true
),
updated_at = NOW()
WHERE org_id = '74d51ead-97a7-4e41-a488-503a9b90c466'
  AND is_enabled = TRUE
  AND (
    definition->'condition'->>'value' = 'speeding'
    OR name ILIKE '%vitesse%'
  );

SELECT 'zone' AS kind, name, behavior_config->'config'->>'speed_limit_kmh' AS limit_kmh
FROM zones
WHERE camera_id = '37c7d7fa-12dc-450c-8c4b-ab63ed43a819' AND name = 'Zone_distance_parcourue_108';

SELECT 'rule' AS kind, name, is_enabled::text, definition->'bindings'->>'speed_kmh' AS speed_kmh
FROM rules
WHERE org_id = '74d51ead-97a7-4e41-a488-503a9b90c466' AND name ILIKE '%vitesse%';
