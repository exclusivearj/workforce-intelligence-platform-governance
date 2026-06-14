"""Tests for the GRANT/REVOKE + SECURITY LABEL DDL generator."""

from __future__ import annotations

import sqlparse

from src.codegen.ddl_generator import (
    generate_all_ddl,
    generate_grant_statements,
    generate_security_labels,
)


def test_grants_for_analyst_reader(config):
    sql = generate_grant_statements(config)
    assert "GRANT SELECT ON analytics.fct_headcount_daily TO analyst_reader;" in sql


def test_restricted_columns_revoked(config):
    sql = generate_grant_statements(config)
    # dim_employees has restricted columns (salary), so base roles are revoked.
    assert "REVOKE SELECT ON analytics.dim_employees FROM analyst_reader;" in sql
    assert "GRANT SELECT ON analytics.dim_employees TO hr_partner_role;" in sql


def test_security_labels_for_pii(config):
    sql = generate_security_labels(config)
    assert "SECURITY LABEL FOR anon ON COLUMN analytics.dim_employees.salary" in sql
    assert "MASKED WITH VALUE" in sql


def test_generated_sql_parses(config):
    sql = generate_all_ddl(config)
    statements = [s for s in sqlparse.parse(sql) if s.token_first(skip_cm=True)]
    assert len(statements) > 0
    assert "Config version: 1.0" in sql
