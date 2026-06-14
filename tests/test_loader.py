"""Tests for the classification config loader + validation."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from src.classifier.loader import DataClassificationConfig, load_config


def test_valid_config_loads(config):
    assert isinstance(config, DataClassificationConfig)
    assert "analytics.dim_employees" in config.tables
    salary = config.tables["analytics.dim_employees"].columns["salary"]
    assert salary.sensitivity == "restricted"


def test_invalid_sensitivity_raises(tmp_path: Path):
    bad = tmp_path / "bad.yml"
    bad.write_text(
        textwrap.dedent(
            """
            version: "1.0"
            tables:
              analytics.t:
                columns:
                  c: { sensitivity: top_secret, pii: false }
            """
        )
    )
    with pytest.raises(ValueError, match="invalid sensitivity"):
        load_config(bad)


def test_confidential_without_mask_raises(tmp_path: Path):
    bad = tmp_path / "bad.yml"
    bad.write_text(
        textwrap.dedent(
            """
            version: "1.0"
            tables:
              analytics.t:
                columns:
                  c: { sensitivity: confidential, pii: true }
            """
        )
    )
    with pytest.raises(ValueError, match="mask_with"):
        load_config(bad)


def test_allowed_roles_lookup(config):
    roles = config.allowed_roles("restricted")
    assert "hr_partner_role" in roles
    assert "analyst_reader" not in roles
