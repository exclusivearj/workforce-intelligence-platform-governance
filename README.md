![workforce-intelligence-platform-governance banner](assets/03-governance-banner.png)

# workforce-intelligence-platform-governance — sensitive data governance layer

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

### Prerequisites

This module applies governance DDL on top of the shared data layer, so it expects:

1. **Postgres is running** — `make infra-up` from the platform root.
2. **Ingestion has been set up** — `make ingestion-setup` creates the base login roles
   (`analyst_reader`, `dbt_transformer`, `ingestion_writer`), and `make ingestion-dbt`
   builds the `analytics.*` / `llm.*` tables that the grants and views reference.

The DB connection is read from `DATABASE_URL`, falling back to `POSTGRES_HOST` /
`POSTGRES_PORT` / `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` (the same env the
ingestion module uses). Export them — or source the platform-root `.env` — before applying.

### Apply

```bash
cd 3-governance
make setup    # install -> bootstrap-roles -> generate-ddl -> apply-ddl
```

`make setup` runs four steps:

| Step | What it does |
|---|---|
| `install` | `pip install -e ".[dev]"` |
| `bootstrap-roles` | Creates the governance-owned roles `hr_partner_role` + `legal_role` (idempotent). The base roles come from ingestion; these two are introduced by the access policy, so governance owns them. |
| `generate-ddl` | Reads `policies/data_classification.yml` and writes SQL artifacts to `generated/` (no DB needed). |
| `apply-ddl` | Applies `audit_setup.sql`, `access_control.sql`, and `masking_views.sql` with `ON_ERROR_STOP=1`, so a failed statement fails the target instead of being silently swallowed. |

Run `make help` for the full target list.

### Column-level SECURITY LABELs (optional)

`generate-ddl` also writes `generated/security_labels.sql`, which tags PII columns for the
[PostgreSQL Anonymizer](https://postgresql-anonymizer.readthedocs.io/) (`anon`) extension.
That extension is **not** part of the shared `pgvector/pgvector:pg16` image, so the labels
are kept out of `apply-ddl` (which must stay green on a stock database). To apply them:

```bash
# once, on a Postgres image that ships the anon extension:
psql "$DATABASE_URL" -c "CREATE EXTENSION anon;"
make apply-security-labels
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

**SECURITY LABELs are an optional, separate artifact.** The `anon` SECURITY LABELs depend on
the PostgreSQL Anonymizer extension, which the shared Postgres image does not ship. Folding
them into the core access-control script would make `apply-ddl` fail on a stock database, so
they are generated into their own `security_labels.sql` and applied on demand. The functional
masking — column-level grants plus the masked views — does not depend on `anon`.

---

## Known limitations

- **SECURITY LABELs require PostgreSQL Anonymizer.** Generated into `security_labels.sql` and
  applied via `make apply-security-labels`, not as part of `make setup`, because the shared
  `pgvector/pgvector:pg16` image does not include `anon`.
- **The audit scanner relies on `pg_stat_statements`.** Postgres only collects query history
  when the library is in `shared_preload_libraries`. The shared `docker-compose.yml` now
  preloads it (`command: postgres -c shared_preload_libraries=pg_stat_statements`), and
  `apply-ddl` runs `CREATE EXTENSION pg_stat_statements` to register the view. If you point the
  module at a different Postgres, set the same startup flag there or the weekly
  `governance_audit` DAG will have no statement history to scan.
