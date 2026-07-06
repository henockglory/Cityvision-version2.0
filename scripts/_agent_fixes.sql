\pset border 2
\echo '=== [B.16] Speed limit 8 -> 30 km/h (rule + zone coherent) ==='
UPDATE rules
SET definition = jsonb_set(definition, '{bindings,speed_kmh}', '30'),
    updated_at = NOW()
WHERE name = 'Démo · Excès de vitesse';

UPDATE zones
SET behavior_config = jsonb_set(behavior_config, '{config,speed_limit_kmh}', '30'),
    updated_at = NOW()
WHERE name = 'Zone_distance_parcourue';

\echo '=== [B.24] Restore mono-camera (default = ceinture/téléphone cam) ==='
UPDATE org_demo_settings
SET source_mode = 'camera',
    active_camera_id = 'f691ef55-6791-495b-a35e-be215e7ac109',
    updated_at = NOW()
WHERE org_id = '74d51ead-97a7-4e41-a488-503a9b90c466';

\echo '=== verify ==='
SELECT name, definition->'bindings'->>'speed_kmh' AS rule_limit FROM rules WHERE name='Démo · Excès de vitesse';
SELECT name, behavior_config->'config'->>'speed_limit_kmh' AS zone_limit FROM zones WHERE name='Zone_distance_parcourue';
SELECT source_mode, active_camera_id FROM org_demo_settings;
