"""Shared fixtures: an isolated data dir, synchronous jobs, offline LLM, and fixture perception."""

import pytest
from fastapi.testclient import TestClient

from config import get_settings
from main import create_app


@pytest.fixture
def settings_env(tmp_path, monkeypatch):
    monkeypatch.setenv("VEYRA_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("VEYRA_SYNC_JOBS", "1")
    monkeypatch.setenv("VEYRA_REPLAY_SPEED", "0")
    monkeypatch.setenv("VEYRA_LLM_MODE", "offline")
    monkeypatch.setenv("VEYRA_PERCEPTION_MODE", "fixture")
    get_settings.cache_clear()
    yield get_settings()
    get_settings.cache_clear()


@pytest.fixture
def app(settings_env):
    return create_app()


@pytest.fixture
def client(app):
    with TestClient(app) as test_client:
        yield test_client
