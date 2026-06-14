"""Tests for audit DDL generation and the codegen CLI."""

from __future__ import annotations

from src.audit.trigger_generator import generate_audit_ddl, generate_registry_inserts
from src.codegen import cli


def test_audit_ddl_has_tables():
    sql = generate_audit_ddl()
    assert "governance.access_audit_log" in sql
    assert "governance.classification_registry" in sql


def test_registry_inserts_cover_columns(config):
    sql = generate_registry_inserts(config)
    assert "analytics.dim_employees" in sql
    assert "salary" in sql
    assert "ON CONFLICT" in sql


def test_cli_writes_all_artifacts(tmp_path, monkeypatch):
    # Run from repo root so load_config finds the default policy path.
    import pathlib

    repo_root = pathlib.Path(__file__).resolve().parents[1]
    monkeypatch.chdir(repo_root)

    out = cli.main(output_dir=tmp_path)
    assert set(out.keys()) == {"audit_setup.sql", "access_control.sql", "masking_views.sql"}
    for path in out.values():
        assert pathlib.Path(path).read_text().strip()
