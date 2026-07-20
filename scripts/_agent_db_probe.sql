\pset border 2
\echo '=== event_severity enum values ==='
SELECT e.enumlabel
FROM pg_type t JOIN pg_enum e ON e.enumtypid = t.oid
WHERE t.typname = 'event_severity' ORDER BY e.enumsortorder;

\echo '=== distinct recent event types + severities (last 500) ==='
SELECT event_type, severity, count(*) FROM (
  SELECT event_type, severity FROM events ORDER BY created_at DESC LIMIT 500
) s GROUP BY event_type, severity ORDER BY event_type;
