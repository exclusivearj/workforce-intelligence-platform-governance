"""Shared fixtures for the governance test suite."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.classifier.loader import load_config

CONFIG_PATH = Path(__file__).resolve().parents[1] / "policies" / "data_classification.yml"


@pytest.fixture
def config():
    return load_config(CONFIG_PATH)


class FakeCursor:
    def __init__(self, fetchall_queue=None):
        self.executed: list[tuple] = []
        self._fetchall = list(fetchall_queue or [])

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, params=None):
        self.executed.append((sql, params))

    def fetchall(self):
        return self._fetchall.pop(0) if self._fetchall else []


class FakeConn:
    def __init__(self, cursor=None):
        self._cursor = cursor or FakeCursor()
        self.committed = False

    def cursor(self):
        return self._cursor

    def commit(self):
        self.committed = True
