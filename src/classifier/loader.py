"""Load and validate the data_classification.yml policy file."""

from __future__ import annotations

import os
from pathlib import Path

import yaml
from pydantic import BaseModel, model_validator

VALID_SENSITIVITIES = {"public", "internal", "confidential", "restricted"}
DEFAULT_CONFIG_PATH = "policies/data_classification.yml"


class ColumnClassification(BaseModel):
    sensitivity: str
    pii: bool = False
    mask_with: str | None = None

    @model_validator(mode="after")
    def _validate(self) -> "ColumnClassification":
        if self.sensitivity not in VALID_SENSITIVITIES:
            raise ValueError(f"invalid sensitivity '{self.sensitivity}'")
        # Confidential columns are kept in masked views, so they MUST declare how
        # to mask. Restricted columns are excluded entirely, so mask_with is optional.
        if self.sensitivity == "confidential" and not self.mask_with:
            raise ValueError("confidential column requires a 'mask_with' expression")
        return self


class TableClassification(BaseModel):
    columns: dict[str, ColumnClassification]


class DataClassificationConfig(BaseModel):
    version: str
    tables: dict[str, TableClassification]
    sensitivity_levels: dict[str, dict] = {}
    last_updated: str | None = None
    owner: str | None = None

    def allowed_roles(self, sensitivity: str) -> list[str]:
        level = self.sensitivity_levels.get(sensitivity, {})
        return list(level.get("allowed_roles", []))

    def columns_by_sensitivity(self, table: str, sensitivity: str) -> list[str]:
        tbl = self.tables.get(table)
        if not tbl:
            return []
        return [c for c, cfg in tbl.columns.items() if cfg.sensitivity == sensitivity]


def load_config(path: str | os.PathLike = DEFAULT_CONFIG_PATH) -> DataClassificationConfig:
    """Load and validate the classification config. Raises on schema errors."""
    raw = yaml.safe_load(Path(path).read_text())
    return DataClassificationConfig(**raw)
