\pset border 2
SELECT now() AS db_now;
\echo '=== demo alerts by rule (last 60 min) ==='
SELECT COALESCE(r.name, a.title) AS rule,
       count(*) AS n,
       count(*) FILTER (WHERE a.evidence_snapshot IS NOT NULL AND a.evidence_snapshot::text <> 'null' AND a.evidence_snapshot::text <> '{}') AS with_evidence,
       max(a.severity::text) AS sev,
       max(a.created_at) AS latest
FROM alerts a
LEFT JOIN rules r ON r.id = a.rule_id
WHERE a.created_at > now() - interval '60 minutes'
GROUP BY 1 ORDER BY n DESC;
