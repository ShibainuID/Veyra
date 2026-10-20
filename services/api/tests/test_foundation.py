import re
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pytest

from adapters.llm import resolve_llm_mode
from adapters.perception import probe_capabilities
from config import get_settings
from domain import clock
from domain.ids import new_id


def test_settings_defaults(monkeypatch):
    for name in ("VEYRA_DATA_DIR", "VEYRA_DATABASE_URL", "VEYRA_SYNC_JOBS", "VEYRA_REPLAY_SPEED",
                 "VEYRA_PERCEPTION_MODE", "VEYRA_LLM_MODE", "VEYRA_DEMO_MODE", "VEYRA_MEDIA_SECRET",
                 "VEYRA_SERVICE_TOKEN", "VEYRA_LLM_MODEL", "VEYRA_LLM_PROVIDER"):
        monkeypatch.delenv(name, raising=False)
    get_settings.cache_clear()
    settings = get_settings()
    api_dir = Path(__file__).resolve().parents[1]

    assert settings.data_dir == api_dir / ".data"
    assert settings.database_url == f"sqlite:///{(api_dir / '.data' / 'veyra.db').as_posix()}"
    assert settings.media_dir == api_dir / ".data" / "media"
    assert settings.repo_root == api_dir.parents[1]
    assert settings.fixtures_dir == api_dir.parents[1] / "demo" / "fixtures"
    assert settings.scenarios_dir == api_dir.parents[1] / "demo" / "scenarios"
    assert settings.sync_jobs is False
    assert settings.replay_speed == 10.0
    assert settings.perception_mode == "auto"
    assert settings.llm_mode == "auto"
    assert settings.demo_mode is True
    assert re.fullmatch(r"[0-9a-f]{64}", settings.media_secret)
    assert settings.service_token == "demo-worker-token"
    assert settings.llm_provider == "openai"
    assert settings.llm_model == "gpt-6-luna"
    get_settings.cache_clear()
    assert get_settings().media_secret == settings.media_secret


def test_empty_secrets_fall_back_to_defaults(monkeypatch):
    monkeypatch.setenv("VEYRA_MEDIA_SECRET", "")
    monkeypatch.setenv("VEYRA_SERVICE_TOKEN", "")
    get_settings.cache_clear()
    settings = get_settings()

    assert re.fullmatch(r"[0-9a-f]{64}", settings.media_secret)
    assert settings.service_token == "demo-worker-token"


def test_media_secret_from_env(monkeypatch):
    monkeypatch.setenv("VEYRA_MEDIA_SECRET", "configured-secret")
    get_settings.cache_clear()

    assert get_settings().media_secret == "configured-secret"


def test_settings_from_env(settings_env, tmp_path):
    assert settings_env.data_dir == tmp_path / "data"
    assert settings_env.sync_jobs is True
    assert settings_env.replay_speed == 0.0
    assert settings_env.perception_mode == "fixture"


def test_settings_reject_unknown_mode(monkeypatch):
    monkeypatch.setenv("VEYRA_LLM_MODE", "sometimes")
    get_settings.cache_clear()
    with pytest.raises(ValueError):
        get_settings()


@pytest.mark.parametrize("value", ["-1", "fast"])
def test_settings_reject_bad_replay_speed(monkeypatch, value):
    monkeypatch.setenv("VEYRA_REPLAY_SPEED", value)
    get_settings.cache_clear()
    with pytest.raises(ValueError, match="VEYRA_REPLAY_SPEED"):
        get_settings()


@pytest.mark.parametrize(("mode", "env", "expected"), [
    ("live", {}, "live"),
    ("offline", {"ANTHROPIC_API_KEY": "k"}, "offline"),
    ("auto", {"ANTHROPIC_API_KEY": "k"}, "live"),
    ("auto", {"ANTHROPIC_AUTH_TOKEN": "t"}, "live"),
    ("auto", {}, "offline"),
])
def test_resolve_llm_mode(settings_env, monkeypatch, mode, env, expected):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setenv("VEYRA_LLM_MODE", mode)
    get_settings.cache_clear()

    assert resolve_llm_mode(get_settings()) == expected


def test_clock_is_utc_and_overridable():
    assert clock.now().tzinfo is UTC
    frozen = datetime(2026, 10, 20, 9, 30, tzinfo=UTC)
    clock.set_now(lambda: frozen)
    try:
        assert clock.now() == frozen
    finally:
        clock.reset()
    assert clock.now() != frozen


def test_isoformat_uses_z_suffix():
    assert clock.isoformat(datetime(2026, 10, 20, 9, 30, tzinfo=UTC)) == "2026-10-20T09:30:00Z"
    offset = datetime(2026, 10, 20, 11, 30, tzinfo=timezone(timedelta(hours=2)))
    assert clock.isoformat(offset) == "2026-10-20T09:30:00Z"


def test_probe_treats_lfs_pointer_as_missing_model(tmp_path):
    pointer = tmp_path / "muzzle_embed_v1.onnx"
    pointer.write_text("version https://git-lfs.github.com/spec/v1\n")

    capabilities = probe_capabilities(model_path=pointer)

    assert capabilities["muzzle"] is False
    assert capabilities["age"] is True
    assert set(capabilities) == {"video", "muzzle", "weight", "age"}


def test_new_id_format():
    value = new_id("act")
    assert value.startswith("act-") and len(value) == 16
    assert new_id("act") != value
