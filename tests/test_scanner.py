"""Tests for the pg_stat_statements audit scanner."""

from __future__ import annotations

from tests.conftest import FakeConn, FakeCursor

from src.audit.scanner import scan_for_restricted_access


def test_finding_when_analyst_reads_salary(config):
    cur = FakeCursor(
        fetchall_queue=[[("analyst_reader", "SELECT salary FROM analytics.dim_employees")]]
    )
    conn = FakeConn(cur)
    findings = scan_for_restricted_access(conn, config)
    salary_findings = [f for f in findings if f.column_name == "salary"]
    assert salary_findings
    assert salary_findings[0].severity == "critical"
    assert conn.committed


def test_no_finding_when_hr_partner_reads_salary(config):
    cur = FakeCursor(
        fetchall_queue=[[("hr_partner_role", "SELECT salary FROM analytics.dim_employees")]]
    )
    findings = scan_for_restricted_access(FakeConn(cur), config)
    assert not [f for f in findings if f.column_name == "salary"]


def test_confidential_access_is_warning(config):
    cur = FakeCursor(
        fetchall_queue=[[("analyst_reader", "SELECT full_name FROM analytics.dim_employees")]]
    )
    findings = scan_for_restricted_access(FakeConn(cur), config)
    name_findings = [f for f in findings if f.column_name == "full_name"]
    assert name_findings and name_findings[0].severity == "warning"


def test_no_findings_persists_nothing(config):
    cur = FakeCursor(fetchall_queue=[[("analyst_reader", "SELECT department FROM analytics.dim_employees")]])
    conn = FakeConn(cur)
    findings = scan_for_restricted_access(conn, config)
    assert findings == []
