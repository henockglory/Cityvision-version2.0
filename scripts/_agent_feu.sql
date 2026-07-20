\pset border 2
SELECT z.name,
       z.behavior_config->'config'->>'stable_frames' AS stable_frames,
       z.polygon
FROM zones z
WHERE z.camera_id='8ed20433-57d5-4999-a6ab-0bea028b23a3'
ORDER BY z.name;
