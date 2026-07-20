\pset border 2
\x on
\echo '=== latest Excès de vitesse alert ==='
SELECT a.title, a.message, a.severity::text AS sev, a.created_at,
       a.metadata->>'speed_kmh' AS md_speed,
       a.metadata->>'distance_m' AS md_dist,
       jsonb_object_keys(a.evidence_snapshot) AS ev_keys
FROM alerts a LEFT JOIN rules r ON r.id=a.rule_id
WHERE r.name='Démo · Excès de vitesse'
ORDER BY a.created_at DESC LIMIT 1;

\echo '=== latest Feu rouge alert ==='
SELECT a.title, a.message, a.severity::text AS sev, a.created_at,
       jsonb_object_keys(a.evidence_snapshot) AS ev_keys
FROM alerts a LEFT JOIN rules r ON r.id=a.rule_id
WHERE r.name='Démo · Feu rouge'
ORDER BY a.created_at DESC LIMIT 1;
