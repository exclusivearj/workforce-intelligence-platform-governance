-- Governance-owned database roles.
--
-- The ingestion module (1-ingestion/src/utils/db.py :: bootstrap_roles) creates the
-- platform login roles: ingestion_writer, dbt_transformer, analyst_reader.
-- The two roles below are introduced by the governance access policy
-- (policies/data_classification.yml -> sensitivity_levels.*.allowed_roles) and are
-- not created anywhere else, so the generated GRANTs in access_control.sql would
-- fail with "role does not exist" without them.
--
-- They are created as NOLOGIN group roles: real HR Partner / Legal users are granted
-- membership (GRANT hr_partner_role TO <user>) rather than logging in directly.
-- Idempotent — safe to re-run.

DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'hr_partner_role') THEN
        CREATE ROLE hr_partner_role;
    END IF;
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'legal_role') THEN
        CREATE ROLE legal_role;
    END IF;
END
$$;
