-- Purge ponctuelle des alertes pour une organisation (démo / tests).
-- Politique produit : aucun DELETE /alerts en API — cette purge est réservée aux opérateurs.
-- Usage: psql $DATABASE_URL -v org_id='YOUR-ORG-UUID' -f scripts/purge-alerts-demo.sql

DELETE FROM alerts WHERE org_id = :'org_id'::uuid;
