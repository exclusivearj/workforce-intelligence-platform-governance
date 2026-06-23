.PHONY: help install setup bootstrap-roles generate-ddl apply-ddl apply-security-labels test lint clean

# psql connection string: prefer DATABASE_URL, else assemble from POSTGRES_* using the
# same defaults as src/utils/db.py and docker-compose.yml. Resolved inside the shell so
# exported env (or a sourced .env) is honored. ON_ERROR_STOP=1 makes failed statements
# fail the target instead of being silently swallowed.
DSN  = $${DATABASE_URL:-postgresql://$${POSTGRES_USER:-postgres}:$${POSTGRES_PASSWORD:-changeme}@$${POSTGRES_HOST:-localhost}:$${POSTGRES_PORT:-5432}/$${POSTGRES_DB:-workforce}}
PSQL = psql "$(DSN)" -v ON_ERROR_STOP=1

help:
	@echo ""
	@echo "governance — sensitive data governance layer"
	@echo "────────────────────────────────────────────────────────────────"
	@echo "  make install               Install the package + dev tooling"
	@echo "  make setup                 install -> bootstrap-roles -> generate-ddl -> apply-ddl"
	@echo ""
	@echo "  make bootstrap-roles       Create governance roles (hr_partner_role, legal_role)"
	@echo "  make generate-ddl          Codegen SQL artifacts into generated/ (no DB needed)"
	@echo "  make apply-ddl             Apply audit + access control + masking views to Postgres"
	@echo "  make apply-security-labels Apply PII SECURITY LABELs (requires the 'anon' extension)"
	@echo ""
	@echo "  make test                  Run the test suite with coverage (>=80%)"
	@echo "  make lint                  ruff check src/ tests/"
	@echo "  make clean                 Remove caches + generated SQL"
	@echo ""
	@echo "Prerequisites for apply-* targets: Postgres is up and the ingestion module has"
	@echo "been set up first (creates the analytics.* / llm.* tables and the base roles)."
	@echo ""

install:
	pip install -e ".[dev]"

setup: install bootstrap-roles generate-ddl apply-ddl
	@echo "Governance layer applied."

bootstrap-roles:
	@echo "Creating governance roles (hr_partner_role, legal_role) if absent..."
	$(PSQL) -f sql/bootstrap_roles.sql

generate-ddl:
	@echo "Generating DDL from classification config..."
	python -m src.codegen.cli
	@echo "DDL written to generated/"

apply-ddl:
	@echo "Applying audit + access control + masking DDL..."
	$(PSQL) -f generated/audit_setup.sql
	$(PSQL) -f generated/access_control.sql
	$(PSQL) -f generated/masking_views.sql

# SECURITY LABELs depend on the PostgreSQL Anonymizer extension (CREATE EXTENSION anon;),
# which is not part of the shared Postgres image — kept separate so `apply-ddl` stays green
# on a stock database. Run this only once `anon` is installed.
apply-security-labels:
	@echo "Applying SECURITY LABELs (requires the PostgreSQL Anonymizer 'anon' extension)..."
	$(PSQL) -f generated/security_labels.sql

test:
	pytest tests/ -v --cov=src --cov-report=term-missing --cov-fail-under=80

lint:
	ruff check src/ tests/

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	rm -rf .coverage htmlcov generated/*.sql
