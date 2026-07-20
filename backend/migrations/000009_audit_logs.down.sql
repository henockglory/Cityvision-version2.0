DROP TRIGGER IF EXISTS audit_logs_no_update ON audit_logs;
DROP FUNCTION IF EXISTS prevent_audit_logs_mutation();
DROP TABLE IF EXISTS audit_logs;
