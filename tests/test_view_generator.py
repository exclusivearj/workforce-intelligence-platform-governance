"""Tests for the masking view generator."""

from __future__ import annotations

from src.codegen.view_generator import generate_all_views, generate_masked_view


def test_salary_excluded_from_view(config):
    tbl = config.tables["analytics.dim_employees"]
    sql = generate_masked_view("analytics.dim_employees", tbl)
    # salary is restricted -> excluded from SELECT (only mentioned in a comment).
    assert "salary: EXCLUDED" in sql
    assert "NULL AS salary" not in sql


def test_full_name_masked(config):
    tbl = config.tables["analytics.dim_employees"]
    sql = generate_masked_view("analytics.dim_employees", tbl)
    assert "'***' AS full_name" in sql


def test_public_column_included_as_is(config):
    tbl = config.tables["analytics.dim_employees"]
    sql = generate_masked_view("analytics.dim_employees", tbl)
    assert "employee_id" in sql
    assert "GRANT SELECT ON analytics.v_employees_safe TO analyst_reader;" in sql


def test_generate_all_views_only_for_sensitive_tables(config):
    sql = generate_all_views(config)
    # dim_employees + fct_attrition_monthly + llm.feedback have confidential/restricted.
    assert "v_employees_safe" in sql
    assert "v_attrition_safe" in sql
    # headcount has no confidential/restricted columns -> no view.
    assert "v_fct_headcount_daily_safe" not in sql
