"""governance_audit — weekly scan of restricted-column access patterns."""

from __future__ import annotations

from datetime import datetime

from airflow.decorators import dag, task


@dag(
    dag_id="governance_audit",
    schedule="0 3 * * 0",  # weekly, Sunday 03:00
    start_date=datetime(2024, 1, 1),
    catchup=False,
    tags=["governance", "people-analytics"],
)
def governance_audit_dag():
    @task
    def scan_audit_log() -> list:
        from src.audit.scanner import scan_for_restricted_access
        from src.classifier.loader import load_config
        from src.utils.db import get_connection

        conn = get_connection()
        try:
            findings = scan_for_restricted_access(conn, load_config())
        finally:
            conn.close()
        return [f.__dict__ for f in findings]

    @task
    def flag_unexpected_access(findings: list) -> dict:
        critical = [f for f in findings if f["severity"] == "critical"]
        warnings = [f for f in findings if f["severity"] == "warning"]
        return {
            "total_findings": len(findings),
            "critical_count": len(critical),
            "warning_count": len(warnings),
        }

    @task
    def send_weekly_report(summary: dict, findings: list) -> None:
        from src.audit.alerts import send_slack_alert

        lines = [
            "# Weekly governance audit report",
            f"- Total findings: {summary['total_findings']}",
            f"- Critical: {summary['critical_count']}",
            f"- Warnings: {summary['warning_count']}",
        ]
        for f in findings[:10]:
            lines.append(
                f"  - [{f['severity']}] {f['executing_role']} -> "
                f"{f['table_fqn']}.{f['column_name']}"
            )
        send_slack_alert("\n".join(lines))

    findings = scan_audit_log()
    summary = flag_unexpected_access(findings)
    send_weekly_report(summary, findings)


governance_audit_dag()
