.PHONY: setup generate-ddl apply-ddl test lint clean

setup: generate-ddl apply-ddl
	@echo "Governance layer applied."

generate-ddl:
	pip install -e ".[dev]"
	@echo "Generating DDL from classification config..."
	python -m src.codegen.cli
	@echo "DDL written to generated/"

apply-ddl:
	@echo "Applying audit + access control + masking DDL..."
	psql "$$DATABASE_URL" -f generated/audit_setup.sql
	psql "$$DATABASE_URL" -f generated/access_control.sql
	psql "$$DATABASE_URL" -f generated/masking_views.sql

test:
	pytest tests/ -v --cov=src --cov-report=term-missing --cov-fail-under=80

lint:
	ruff check src/ tests/

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	rm -rf .coverage htmlcov generated/*.sql
