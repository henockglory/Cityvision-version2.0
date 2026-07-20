SELECT
  e.event_type,
  e.id::text,
  e.occurred_at::text,
  e.evidence_snapshot->'package'->'metadata'->>'capture_source' AS src,
  e.evidence_snapshot->'package'->'metadata'->>'evidence_status' AS status,
  e.evidence_snapshot->'package'->'metadata'->>'bbox_quality_ok' AS quality_ok,
  jsonb_array_length(COALESCE(e.evidence_snapshot->'package'->'images', '[]'::jsonb)) AS n_images,
  (e.evidence_snapshot->'package'->'clip') IS NOT NULL AS has_clip
FROM events e
WHERE e.event_type IN ('red_light_violation', 'speeding', 'phone_use_violation', 'seatbelt_violation')
  AND e.occurred_at > NOW() - INTERVAL '40 minutes'
ORDER BY e.occurred_at DESC
LIMIT 15;
