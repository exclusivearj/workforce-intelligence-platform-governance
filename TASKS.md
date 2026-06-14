# TASKS.md — governance/

> Read `../TASKS.md` first for platform-wide rules.
> Requires `ingestion/` schemas to exist before running this module.

---

## What this project builds

A YAML-driven, code-generated sensitive data governance layer:

1. A `data_classification.yml` config that tags every column in every table with a sensitivity level
2. A Python DDL codegen script that reads the config and generates Postgres `GRANT`, `REVOKE`,
   `SECURITY LABEL`, and column-masking `CREATE VIEW` statements
3. An audit trigger on all `restricted` column access that writes to `governance.access_audit_log`
4. A `data_access_matrix.md` that documents who can see what
5. A weekly Airflow DAG that scans the audit log and flags unexpected access patterns

This directly addresses the Airbnb JD requirement:
> "Prior work experience with sensitive data, including sensitivity classification, access controls,
> and audit logging; familiarity with data governance requirements for employee or sensitive data."
> "Assess data readiness for AI use cases, working with EX teams, Legal, and BizTech."

---

## Directory structure

```
governance/
├── TASKS.md                              ← this file
├── README.md
├── Makefile
├── pyproject.toml
├── src/
│   ├── __init__.py
│   ├── classifier/
│   │   ├── __init__.py
│   │   └── loader.py                     ← load + validate data_classification.yml
│   ├── codegen/
│   │   ├── __init__.py
│   │   ├── ddl_generator.py              ← generate SQL from classification config
│   │   └── view_generator.py             ← generate masking CREATE VIEW statements
│   └── audit/
│       ├── __init__.py
│       ├── trigger_generator.py          ← generate audit trigger DDL
│       └── scanner.py                    ← scan audit log for anomalies
├── airflow/
│   └── dags/
│       └── governance_audit_dag.py
├── policies/
│   ├── data_classification.yml           ← THE key artifact — classify every column
│   └── data_access_matrix.md            ← human-readable access matrix
├── tests/
│   ├── conftest.py
│   ├── test_loader.py
│   ├── test_ddl_generator.py
│   ├── test_view_generator.py
│   └── test_scanner.py
└── .github/
    └── workflows/
        └── governance-ci.yml
```

---

## Implementation tasks

### Task 3.0 — Data classification config (`policies/data_classification.yml`)

This is the most important deliverable of this project. Classify every column that appears
in the `analytics` and `llm` schemas. Use four sensitivity levels:

- `public` — can be shared freely; no restrictions
- `internal` — accessible to all authenticated employees; not for external sharing
- `confidential` — restricted to named roles; must not appear in LLM context without masking
- `restricted` — HR partners and Legal only; triggers audit log on every access

```yaml
version: "1.0"
last_updated: "2024-01-01"
owner: "data-platform-team"

sensitivity_levels:
  public:
    description: "Freely shareable. No access restrictions."
    allowed_roles: ["analyst_reader", "dbt_transformer", "ingestion_writer"]
  internal:
    description: "Internal use only. All authenticated users."
    allowed_roles: ["analyst_reader", "dbt_transformer"]
  confidential:
    description: "Role-restricted. Masked in LLM context. Logged on access."
    allowed_roles: ["dbt_transformer"]
    llm_safe: false
    mask_in_views: true
  restricted:
    description: "HR Partner and Legal only. Audit trigger on every SELECT."
    allowed_roles: ["hr_partner_role", "legal_role"]
    audit_trigger: true
    llm_safe: false
    mask_in_views: true

tables:
  analytics.dim_employees:
    columns:
      employee_id:       { sensitivity: public,       pii: false }
      full_name:         { sensitivity: confidential, pii: true,  mask_with: "'***'" }
      email:             { sensitivity: confidential, pii: true,  mask_with: "'***@***.com'" }
      department:        { sensitivity: internal,     pii: false }
      job_title:         { sensitivity: internal,     pii: false }
      level:             { sensitivity: internal,     pii: false }
      hire_date:         { sensitivity: internal,     pii: false }
      termination_date:  { sensitivity: internal,     pii: false }
      is_active:         { sensitivity: public,       pii: false }
      employment_type:   { sensitivity: internal,     pii: false }
      manager_id:        { sensitivity: confidential, pii: false, mask_with: "MD5(manager_id::text)" }
      location:          { sensitivity: internal,     pii: false }
      salary:            { sensitivity: restricted,   pii: true,  mask_with: "NULL" }
      performance_rating:{ sensitivity: restricted,   pii: true,  mask_with: "NULL" }
      created_at:        { sensitivity: public,       pii: false }
      updated_at:        { sensitivity: public,       pii: false }

  analytics.fct_headcount_daily:
    columns:
      date:              { sensitivity: public,       pii: false }
      department:        { sensitivity: internal,     pii: false }
      level:             { sensitivity: internal,     pii: false }
      headcount:         { sensitivity: internal,     pii: false }
      employment_type:   { sensitivity: internal,     pii: false }

  analytics.fct_attrition_monthly:
    columns:
      year_month:                    { sensitivity: public,    pii: false }
      department:                    { sensitivity: internal,  pii: false }
      voluntary_terminations:        { sensitivity: internal,  pii: false }
      involuntary_terminations:      { sensitivity: confidential, pii: false }
      attrition_rate_pct:            { sensitivity: internal,  pii: false }
      rolling_12m_attrition_rate_pct:{ sensitivity: internal,  pii: false }

  analytics.rpt_recruiting_funnel:
    columns:
      job_id:                  { sensitivity: internal,  pii: false }
      job_title:               { sensitivity: internal,  pii: false }
      department:              { sensitivity: internal,  pii: false }
      applied_count:           { sensitivity: internal,  pii: false }
      hired_count:             { sensitivity: internal,  pii: false }
      application_to_hire_days_avg: { sensitivity: internal, pii: false }
      offer_acceptance_rate_pct:    { sensitivity: internal, pii: false }

  llm.eval_results:
    columns:
      id:                { sensitivity: internal,  pii: false }
      question:          { sensitivity: internal,  pii: false }
      ground_truth:      { sensitivity: internal,  pii: false }
      generated_answer:  { sensitivity: internal,  pii: false }
      faithfulness:      { sensitivity: internal,  pii: false }
      answer_relevancy:  { sensitivity: internal,  pii: false }

  llm.feedback:
    columns:
      id:               { sensitivity: internal,  pii: false }
      analyst_role:     { sensitivity: internal,  pii: false }
      rating:           { sensitivity: internal,  pii: false }
      correction_text:  { sensitivity: confidential, pii: false }
```

---

### Task 3.1 — Classification loader (`src/classifier/loader.py`)

```python
from pydantic import BaseModel, field_validator

class ColumnClassification(BaseModel):
    sensitivity: str   # 'public' | 'internal' | 'confidential' | 'restricted'
    pii: bool
    mask_with: str | None = None

class TableClassification(BaseModel):
    columns: dict[str, ColumnClassification]

class DataClassificationConfig(BaseModel):
    version: str
    tables: dict[str, TableClassification]

    @field_validator("tables")
    def validate_sensitivity_levels(cls, v):
        valid = {"public", "internal", "confidential", "restricted"}
        for table, tbl in v.items():
            for col, col_cfg in tbl.columns.items():
                if col_cfg.sensitivity not in valid:
                    raise ValueError(f"{table}.{col}: invalid sensitivity '{col_cfg.sensitivity}'")
        return v

def load_config(path: str = "policies/data_classification.yml") -> DataClassificationConfig:
    """Load and validate the classification config. Raise on schema errors."""
```

---

### Task 3.2 — DDL generator (`src/codegen/ddl_generator.py`)

```python
def generate_grant_statements(config: DataClassificationConfig) -> str:
    """
    For each table + column, generate GRANT SELECT on the table to allowed roles.
    For restricted columns: generate REVOKE on the base table, then GRANT via the
    masked view only.
    Return a single SQL string with all GRANT/REVOKE statements.
    """

def generate_security_labels(config: DataClassificationConfig) -> str:
    """
    For each column with pii=True, generate:
    SECURITY LABEL FOR anon ON COLUMN {table}.{col} IS 'MASKED WITH VALUE {mask_with}';
    Return a single SQL string.
    """

def generate_all_ddl(config: DataClassificationConfig) -> str:
    """
    Combine grant_statements + security_labels into a single executable SQL script.
    Add a header comment with generation timestamp and config version.
    """
```

---

### Task 3.3 — Masking view generator (`src/codegen/view_generator.py`)

```python
def generate_masked_view(
    table_fqn: str,
    table_config: TableClassification,
    view_schema: str = "analytics",
    caller_role: str = "analyst_reader",
) -> str:
    """
    Generate a CREATE OR REPLACE VIEW statement for the given table.
    For each column:
    - sensitivity=public/internal: include as-is
    - sensitivity=confidential: include with mask_with expression
    - sensitivity=restricted: exclude entirely (column not in view)

    Example output:
    CREATE OR REPLACE VIEW analytics.v_employees_safe AS
    SELECT
        employee_id,
        department,
        job_title,
        level,
        -- full_name: MASKED (confidential, PII)
        '***' AS full_name,
        -- salary: EXCLUDED (restricted)
        -- performance_rating: EXCLUDED (restricted)
        is_active,
        hire_date
    FROM analytics.dim_employees;
    GRANT SELECT ON analytics.v_employees_safe TO analyst_reader;
    """
```

---

### Task 3.4 — Audit trigger generator (`src/audit/trigger_generator.py`)

```python
def generate_audit_trigger(table_fqn: str, restricted_columns: list[str]) -> str:
    """
    Generate a Postgres trigger that fires on SELECT of any restricted column.

    Pattern:
    CREATE OR REPLACE FUNCTION governance.log_restricted_access()
    RETURNS event_trigger AS $$
    BEGIN
        INSERT INTO governance.access_audit_log(...)
        VALUES (current_user, now(), '{table_fqn}', '{col}', current_query());
    END;
    $$ LANGUAGE plpgsql SECURITY DEFINER;

    Note: Postgres does not support column-level SELECT triggers natively.
    Implement this as a ROW-level AFTER SELECT trigger using a trigger function
    that checks pg_stat_activity for the query text and logs when restricted
    column names appear in the query string.

    Alternative (simpler, production-realistic): Use pg_audit extension or
    implement a scheduled job that scans pg_stat_statements for queries touching
    restricted columns. Document the trade-off in README.
    """
```

**Important design note**: True column-level SELECT auditing in Postgres requires either
`pg_audit` extension or application-layer enforcement. The implementation here should use
a `pg_stat_statements`-based scanner (Task 3.5) rather than a trigger, and document this
trade-off explicitly. This is a more honest and production-realistic approach.

---

### Task 3.5 — Audit log scanner (`src/audit/scanner.py`)

```python
def scan_for_restricted_access(
    conn,
    config: DataClassificationConfig,
    lookback_hours: int = 168,   # 1 week
) -> list[AuditFinding]:
    """
    Query pg_stat_statements for queries containing restricted column names.
    For each match:
    - Check if the executing role is in the allowed_roles list
    - If not: create an AuditFinding(table, column, role, query_sample, severity)
    Write findings to governance.access_audit_log.
    Return list of findings.
    """

@dataclass
class AuditFinding:
    table_fqn: str
    column_name: str
    executing_role: str
    query_sample: str         # first 200 chars of the query
    severity: str             # 'info' | 'warning' | 'critical'
    detected_at: datetime
```

---

### Task 3.6 — Data access matrix (`policies/data_access_matrix.md`)

Write this document manually (not generated). It should read like an internal policy doc
that an HR Partner or Legal reviewer would sign off on.

```markdown
# Data access matrix — workforce-intelligence-platform

Last updated: 2024-01-01 | Owner: Data Platform Team

## Roles

| Role | Description | Examples |
|---|---|---|
| analyst_reader | Read access to public + internal columns | Data Analysts, Biz Intelligence |
| dbt_transformer | Transform access for pipeline automation | Airflow service account |
| hr_partner_role | Access to confidential + restricted columns | HR Business Partners |
| legal_role | Access to restricted columns for compliance | Legal, Privacy team |
| ingestion_writer | Write access to raw schema only | Ingestion pipeline service account |

## Column access by sensitivity

| Sensitivity | analyst_reader | dbt_transformer | hr_partner_role | legal_role |
|---|---|---|---|---|
| public | ✓ | ✓ | ✓ | ✓ |
| internal | ✓ | ✓ | ✓ | ✓ |
| confidential | masked view only | ✓ | ✓ | ✓ |
| restricted | excluded | excluded | ✓ (audited) | ✓ (audited) |

## LLM context window policy

Only columns with sensitivity=public or sensitivity=internal may appear in LLM context windows.
The llm.safe_employee_context view enforces this at the database level.
Any query bypassing this view to access confidential/restricted columns is flagged by the
governance audit scanner.

## Audit log retention

Access audit log rows are retained for 2 years. Weekly governance DAG scans for
unexpected access patterns and generates a report.
```

---

### Task 3.7 — Airflow DAG (`airflow/dags/governance_audit_dag.py`)

```python
@dag(
    dag_id="governance_audit",
    schedule="0 3 * * 0",   # weekly Sunday 3am
    tags=["governance", "people-analytics"],
)
def governance_audit_dag():
    @task
    def scan_audit_log() -> list:
        """Run scanner.scan_for_restricted_access(). Return findings list."""

    @task
    def flag_unexpected_access(findings: list) -> dict:
        """
        Filter findings where severity == 'critical'.
        Return summary: total_findings, critical_count, warning_count.
        """

    @task
    def send_weekly_report(summary: dict, findings: list) -> None:
        """
        Format findings into a Markdown report.
        Send to SLACK_WEBHOOK_URL (or log if not configured).
        """

    findings = scan_audit_log()
    summary = flag_unexpected_access(findings)
    send_weekly_report(summary, findings)
```

---

### Task 3.8 — Tests

**`tests/test_loader.py`**:
- Assert valid YAML loads without error
- Assert invalid sensitivity level raises `ValueError`
- Assert missing `mask_with` on `confidential` column raises `ValueError`

**`tests/test_ddl_generator.py`**:
- Assert generated SQL contains `GRANT SELECT` for `analyst_reader` on public tables
- Assert generated SQL contains `REVOKE` on restricted columns
- Assert output is valid SQL (parse with `sqlfluff` or `sqlparse`)

**`tests/test_view_generator.py`**:
- Assert `salary` is NOT in generated view SELECT list
- Assert `full_name` is replaced with `'***' AS full_name` in generated view
- Assert `employee_id` (public) is included as-is

**`tests/test_scanner.py`**:
- Mock `pg_stat_statements` query response
- Assert finding created when `analyst_reader` queries `salary` column
- Assert no finding when `hr_partner_role` queries `salary` column

---

### Task 3.9 — README.md

Include:
1. Purpose statement
2. ASCII architecture showing: YAML config → codegen → Postgres DDL → audit scanner → Airflow
3. "Why code-generated governance?" section — explain why YAML + codegen beats manual SQL
4. Step-by-step setup instructions
5. How to add a new sensitive column (the workflow: edit YAML → run codegen → apply DDL)
6. Design decisions:
   - Why `pg_stat_statements` scanner over column-level triggers (honesty about Postgres limits)
   - Why the access matrix is written as a human document, not generated (stakeholder sign-off)

---

## Acceptance criteria

- [ ] `data_classification.yml` covers every column in `analytics.*` and `llm.*`
- [ ] `make setup` generates and applies all DDL without errors
- [ ] `analytics.v_employees_safe` view exists with salary excluded
- [ ] `make test` passes with ≥ 80% coverage
- [ ] `data_access_matrix.md` is complete and readable by a non-engineer
- [ ] Airflow DAG `governance_audit` visible in UI and manually triggerable
- [ ] README "how to add a new sensitive column" walkthrough is accurate
