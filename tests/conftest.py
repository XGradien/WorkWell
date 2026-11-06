"""Shared fixtures: every test gets its own throwaway store/config/app."""

from __future__ import annotations

import pytest

from workwell.app import create_app
from workwell.config import Config
from workwell.manager import Manager
from workwell.store import Store


@pytest.fixture
def store(tmp_path) -> Store:
    return Store(str(tmp_path / "test.db"))


@pytest.fixture
def cfg(tmp_path) -> Config:
    return Config.with_overrides(
        {
            "storage": {"path": str(tmp_path / "test.db")},
            "simulation": {"interval": 0.05},
            "channels": {
                "greenery": {"interval": 0.1},
                "noise": {"interval": 0.1},
                "air": {"interval": 0.1},
                "mood": {"interval": 0.1},
                "presence": {"interval": 0.1},
            },
        }
    )


@pytest.fixture
def manager(store, cfg) -> Manager:
    return Manager(store, cfg)


@pytest.fixture
def client(cfg):
    """Full app under test: lifespan wires store/manager/engine from cfg."""
    from fastapi.testclient import TestClient

    app = create_app(cfg)
    with TestClient(app) as c:
        yield c
