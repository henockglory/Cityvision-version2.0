SELECT
  e.id::text,
  e.occurred_at::text,
  e.camera_id::text,
  e.evidence_snapshot->'package'->'metadata'->>'capture_source' AS src,
  e.evidence_snapshot->'package'->'metadata'->>'evidence_status' AS status,
  e.evidence_snapshot->'package'->'metadata'->>'bbox_quality_ok' AS quality_ok,
  e.evidence_snapshot->'package'->'metadata'->>'bbox_ts' AS bbox_ts
FROM events e
WHERE e.event_type = 'speeding'
  AND e.occurred_at > NOW() - INTERVAL '10 minutes'
ORDER BY e.occurred_at DESC
LIMIT 20;
