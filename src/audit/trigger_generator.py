"""Generate the governance audit-log table + scanning infrastructure DDL.

Design note: Postgres has no native column-level SELECT trigger. Rather than fake
one with a brittle row-level hack, this module generates (a) the audit-log table
and (b) a helper to enable pg_stat_statements. Actual detection of restricted-column
access is done by the pg_stat_statements scanner (src/audit/scanner.py). The
trade-off is documented in the README.
"""

from __future__ import annotations

AUDIT_LOG_DDL = """
CREATE SCHEMA IF NOT EXISTS governance;

CREATE TABLE IF NOT EXISTS governance.access_audit_log (
    id              BIGSERIAL PRIMARY KEY,
    detected_at     TIMESTAMPTZ DEFAULT NOW(),
    executing_role  VARCHAR(100) NOT NULL,
    table_fqn       VARCHAR(200) NOT NULL,
    column_name     VARCHAR(100) NOT NULL,
    query_sample    TEXT,
    severity        VARCHAR(20) NOT NULL DEFAULT 'info'
);

CREATE TABLE IF NOT EXISTS governance.classification_registry (
    id              BIGSERIAL PRIMARY KEY,
    table_fqn       VARCHAR(200) NOT NULL,
    column_name     VARCHAR(100) NOT NULL,
    sensitivity     VARCHAR(20) NOT NULL,
    pii             BOOLEAN NOT NULL DEFAULT FALSE,
    registered_at   TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (table_fqn, column_name)
);
""".strip()

ENABLE_PG_STAT_STATEMENTS = (
    "CREATE EXTENSION IF NOT EXISTS pg_stat_statements;"
)


def generate_audit_ddl() -> str:
    """Return DDL for the audit log + classification registry tables."""
    return AUDIT_LOG_DDL + "\n"


def generate_registry_inserts(config) -> str:
    """Populate classification_registry from the config (idempotent upserts)."""
    lines: list[str] = []
    for table, tbl in config.tables.items():
        for col, cfg in tbl.columns.items():
            lines.append(
                "INSERT INTO governance.classification_registry "
                "(table_fqn, column_name, sensitivity, pii) VALUES "
                f"('{table}', '{col}', '{cfg.sensitivity}', {str(cfg.pii).upper()}) "
                "ON CONFLICT (table_fqn, column_name) DO UPDATE "
                "SET sensitivity = EXCLUDED.sensitivity, pii = EXCLUDED.pii;"
            )
    return "\n".join(lines) + "\n"
