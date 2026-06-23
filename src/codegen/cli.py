"""Generate all governance SQL artifacts into the generated/ directory.

Run with: ``python -m src.codegen.cli``.
Writes: audit_setup.sql, access_control.sql, security_labels.sql, masking_views.sql.
"""

from __future__ import annotations

from pathlib import Path

from src.audit.trigger_generator import generate_audit_ddl, generate_registry_inserts
from src.classifier.loader import load_config
from src.codegen.ddl_generator import generate_all_ddl, generate_security_labels_script
from src.codegen.view_generator import generate_all_views

OUTPUT_DIR = Path("generated")


def main(output_dir: Path = OUTPUT_DIR) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    config = load_config()

    artifacts = {
        "audit_setup.sql": generate_audit_ddl() + "\n" + generate_registry_inserts(config),
        "access_control.sql": generate_all_ddl(config),
        "security_labels.sql": generate_security_labels_script(config),
        "masking_views.sql": generate_all_views(config),
    }
    for name, sql in artifacts.items():
        (output_dir / name).write_text(sql)
    return {name: str(output_dir / name) for name in artifacts}


if __name__ == "__main__":
    written = main()
    for name, path in written.items():
        print(f"wrote {path}")
