"""Scan pg_stat_statements for queries touching restricted/confidential columns.

For each match, check whether the executing role is permitted. Unpermitted access
produces an AuditFinding which is written to governance.access_audit_log.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from src.classifier.loader import DataClassificationConfig

_AUDITED_SENSITIVITIES = {"confidential", "restricted"}


@dataclass
class AuditFinding:
    table_fqn: str
    column_name: str
    executing_role: str
    query_sample: str
    severity: str
    detected_at: datetime


def _audited_columns(config: DataClassificationConfig) -> list[tuple[str, str, str, list[str]]]:
    """Return (table, column, sensitivity, allowed_roles) for audited columns."""
    out = []
    for table, tbl in config.tables.items():
        for col, cfg in tbl.columns.items():
            if cfg.sensitivity in _AUDITED_SENSITIVITIES:
                out.append((table, col, cfg.sensitivity, config.allowed_roles(cfg.sensitivity)))
    return out


def _severity_for(sensitivity: str) -> str:
    return "critical" if sensitivity == "restricted" else "warning"


def scan_for_restricted_access(
    conn,
    config: DataClassificationConfig,
    lookback_hours: int = 168,
) -> list[AuditFinding]:
    """Find audited-column access by unauthorized roles and persist findings."""
    audited = _audited_columns(config)
    findings: list[AuditFinding] = []

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT r.rolname AS role, s.query
            FROM pg_stat_statements s
            JOIN pg_roles r ON r.oid = s.userid
            """
        )
        statements = cur.fetchall()

    for role, query in statements:
        lowered = (query or "").lower()
        for table, column, sensitivity, allowed_roles in audited:
            if column.lower() in lowered and role not in allowed_roles:
                findings.append(
                    AuditFinding(
                        table_fqn=table,
                        column_name=column,
                        executing_role=role,
                        query_sample=(query or "")[:200],
                        severity=_severity_for(sensitivity),
                        detected_at=datetime.utcnow(),
                    )
                )

    _write_findings(conn, findings)
    return findings


def _write_findings(conn, findings: list[AuditFinding]) -> None:
    if not findings:
        return
    with conn.cursor() as cur:
        for f in findings:
            cur.execute(
                """
                INSERT INTO governance.access_audit_log
                    (executing_role, table_fqn, column_name, query_sample, severity)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (f.executing_role, f.table_fqn, f.column_name, f.query_sample, f.severity),
            )
    conn.commit()
