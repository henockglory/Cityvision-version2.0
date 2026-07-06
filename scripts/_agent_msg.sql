\pset border 2
\x on
SELECT r.name AS rule, a.message, a.created_at
FROM alerts a JOIN rules r ON r.id=a.rule_id
WHERE r.name LIKE 'Démo%' AND a.created_at > now() - interval '6 minutes'
ORDER BY a.created_at DESC LIMIT 6;
