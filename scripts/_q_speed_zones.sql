SELECT id, name, zone_kind, camera_id, behavior_config
FROM zones
WHERE zone_kind ILIKE '%speed%' OR behavior_config::text ILIKE '%speed%';
