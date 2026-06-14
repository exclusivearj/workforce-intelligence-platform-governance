# Data access matrix — workforce-intelligence-platform

Last updated: 2024-01-01 | Owner: Data Platform Team

This document is the human-readable companion to `data_classification.yml`. It is
written for HR Partners, Legal, and Privacy reviewers to sign off on, and is
intentionally maintained by hand (not generated) so that stakeholder approval is
explicit.

## Roles

| Role | Description | Examples |
|---|---|---|
| `analyst_reader` | Read access to public + internal columns | Data Analysts, BI |
| `dbt_transformer` | Transform access for pipeline automation | Airflow service account |
| `hr_partner_role` | Access to confidential + restricted columns | HR Business Partners |
| `legal_role` | Access to restricted columns for compliance | Legal, Privacy team |
| `ingestion_writer` | Write access to the `raw` schema only | Ingestion service account |

## Column access by sensitivity

| Sensitivity | analyst_reader | dbt_transformer | hr_partner_role | legal_role |
|---|---|---|---|---|
| public | yes | yes | yes | yes |
| internal | yes | yes | yes | yes |
| confidential | masked view only | yes | yes | yes |
| restricted | excluded | excluded | yes (audited) | yes (audited) |

## Sensitivity definitions

- **public** — freely shareable; no restrictions (e.g. `employee_id`, `is_active`).
- **internal** — all authenticated employees; not for external sharing (e.g. `department`, `level`).
- **confidential** — role-restricted, masked in views and never sent to an LLM
  context window (e.g. `full_name`, `email`, `manager_id`).
- **restricted** — HR Partners and Legal only; every access is audited
  (e.g. `salary`, `performance_rating`).

## LLM context window policy

Only `public` and `internal` columns may appear in LLM context windows. The
`llm.safe_employee_context` view enforces this at the database level: it excludes
salary and performance_rating entirely and hashes `manager_id`. Any query that
bypasses this view to read confidential/restricted columns is flagged by the
governance audit scanner.

## Audit log retention

`governance.access_audit_log` rows are retained for 2 years. The weekly
`governance_audit` Airflow DAG scans `pg_stat_statements` for unexpected access
patterns and posts a report to the data-platform Slack channel.

## How to add a new sensitive column

1. Add the column under the relevant table in `policies/data_classification.yml`
   with its `sensitivity`, `pii` flag, and (for confidential columns) a `mask_with`
   expression.
2. Run `make generate-ddl` to regenerate the SQL artifacts in `generated/`.
3. Review the generated diff, then run `make apply-ddl` to apply it.
4. Update this matrix if a new role or sensitivity rule is introduced.
