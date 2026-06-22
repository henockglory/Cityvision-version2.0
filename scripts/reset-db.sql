TRUNCATE TABLE
  audit_logs,
  refresh_tokens,
  alerts,
  incidents,
  events,
  rules,
  cameras,
  zones,
  lines,
  org_memberships,
  sites,
  users,
  organizations
RESTART IDENTITY CASCADE;

UPDATE system_config
SET value = '{"initialized": false}', updated_at = NOW()
WHERE key = 'initialized';
