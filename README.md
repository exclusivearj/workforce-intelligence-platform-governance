# governance — sensitive data governance layer

Part 3 of 4 in the [workforce-intelligence-platform](../README.md).

YAML-driven, code-generated data governance: sensitivity classification,
column masking, access control DDL, and audit scanning for all People Analytics data.

---

## Architecture

```
 policies/data_classification.yml
         │
         ▼
  src/classifier/loader.py        ← validates config with Pydantic
         │
         ├──────────────────────────────────────────────────┐
         ▼                                                   ▼
  src/codegen/ddl_generator.py              src/codegen/view_generator.py
  GRANT / REVOKE / SECURITY LABEL           CREATE OR REPLACE VIEW
         │                                           │
         └────────────────┬──────────────────────────┘
                          ▼
               Applied to Postgres (analytics.*, llm.*)
                          │
                          ▼
             src/audit/scanner.py
             scans pg_stat_statements weekly
                          │
                          ▼
              governance.access_audit_log
                          │
                          ▼
          Airflow DAG: governance_audit (Sunday 3am)
```

---

## Tech stack

| Concern | Technology |
|---|---|
| Config format | YAML (Pydantic-validated) |
| DDL codegen | Python |
| Audit scanning | pg_stat_statements + Python |
| Orchestration | Apache Airflow 2.9 |
| Testing | pytest |

---

## Setup

```bash
cd governance
pip install -e ".[dev]"
make setup         # loads config, generates DDL, applies to Postgres
```

---

## How to add a new sensitive column

1. Edit `policies/data_classification.yml` — add the column under its table with
   the appropriate `sensitivity` level, `pii` flag, and `mask_with` expression
2. Run `make generate-ddl` — this regenerates the SQL scripts
3. Review the generated SQL in `generated/` before applying
4. Run `make apply-ddl` — applies the new grants and views to Postgres
5. Run `make test` to verify the new column is handled correctly

---

## Design decisions

**Code-generated governance over manual SQL.** Classification is defined once in YAML
and propagates automatically to grants, views, and audit config. When a column is reclassified
from `internal` to `restricted`, one YAML edit and one `make apply-ddl` updates everything.
Manual SQL maintenance diverges over time and requires reviewing every file on every change.

**pg_stat_statements scanner over column-level triggers.** Postgres does not support
column-level SELECT triggers natively. The honest, production-realistic approach is a
scheduled scanner against `pg_stat_statements` that checks query text for restricted column
names and flags unexpected roles. This is how `pg_audit` works in principle. The trade-off —
scanning query text is fuzzy, not guaranteed — is documented in the access matrix.

**Human-written access matrix.** The `data_access_matrix.md` is authored by the data platform
team and reviewed by Legal and HR. It cannot be generated because it encodes policy decisions
(who should have what access, why) not just technical facts. A generated document signals
that no human reviewed the policy — a red flag for compliance teams.
