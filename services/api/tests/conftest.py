"""Shared fixtures: every test gets an isolated data dir and database, synchronous jobs, offline LLM, and fixture
perception. `client` enters the app lifespan, so the database is created and seeded."""

import pytest
from fastapi.testclient import TestClient

from config import get_settings
from domain import clock
from main import create_app
from persistence.db import reset_engine


@pytest.fixture(autouse=True)
def settings_env(tmp_path, monkeypatch):
    monkeypatch.setenv("VEYRA_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("VEYRA_SYNC_JOBS", "1")
    monkeypatch.setenv("VEYRA_REPLAY_SPEED", "0")
    monkeypatch.setenv("VEYRA_LLM_MODE", "offline")
    # The fake model clients in the suite speak the Anthropic SDK's shape; test_llm_openai covers OpenAI.
    monkeypatch.setenv("VEYRA_LLM_PROVIDER", "anthropic")
    monkeypatch.delenv("VEYRA_LLM_MODEL", raising=False)
    monkeypatch.setenv("VEYRA_PERCEPTION_MODE", "fixture")
    get_settings.cache_clear()
    yield get_settings()
    reset_engine()
    get_settings.cache_clear()
    clock.reset()


@pytest.fixture
def app(settings_env):
    return create_app()


@pytest.fixture
def client(app):
    with TestClient(app) as test_client:
        yield test_client
