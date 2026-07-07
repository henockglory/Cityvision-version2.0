-- Patch speeding rules for live traffic (dedup + evidence + ingest bindings).
-- Does NOT modify zone geometry.

UPDATE rules
SET definition = jsonb_set(
  jsonb_set(
    jsonb_set(
      jsonb_set(
        jsonb_set(
          definition,
          '{dedup_key_fields}',
          '["camera_id", "zone_id", "track_id"]'::jsonb,
          true
        ),
        '{evidence}',
        '{
          "enabled": true,
          "clip_seconds": 6,
          "draw_bbox": true,
          "images": [
            {"role": "scene", "label": "Vue d''ensemble", "crop": "full"},
            {"role": "subject", "label": "Cible détectée", "crop": "bbox", "padding_pct": 12, "zoom": 1.0},
            {"role": "plate", "label": "Plaque", "crop": "plate_rear", "padding_pct": 6, "zoom": 1.8}
          ]
        }'::jsonb,
        true
      ),
      '{bindings,live_traffic}',
      'true'::jsonb,
      true
    ),
    '{bindings,cooldown_sec}',
    '2'::jsonb,
    true
  ),
  '{bindings,spatial_dedup_sec}',
  '4'::jsonb,
  true
),
updated_at = NOW()
WHERE definition->'bindings'->>'template_id' IN ('tpl-speeding-premium', 'tpl-speed-threshold')
   OR definition->'condition'->>'value' = 'speeding';
