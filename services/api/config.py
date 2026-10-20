"""Service settings from the environment (plan Section 0: run, tests, auth).

Every value has a demo-safe default so `uv run uvicorn main:app` works with no setup. Tests set the
environment and call `get_settings.cache_clear()` to pick up the change.
"""

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

API_DIR = Path(__file__).resolve().parent
REPO_ROOT = API_DIR.parents[1]

PERCEPTION_MODES = ("auto", "prototype", "fixture")
LLM_MODES = ("auto", "live", "offline")


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    database_url: str
    media_dir: Path
    media_secret: str
    service_token: str
    sync_jobs: bool
    replay_speed: float
    perception_mode: str
    llm_mode: str
    llm_model: str
    demo_mode: bool
    repo_root: Path = REPO_ROOT
    fixtures_dir: Path = REPO_ROOT / "demo" / "fixtures"
    scenarios_dir: Path = REPO_ROOT / "demo" / "scenarios"


def _env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None or value.strip() == "":
        return default
    return value.strip().lower() in ("1", "true", "yes")


def _env_choice(name: str, default: str, choices: tuple[str, ...]) -> str:
    value = os.environ.get(name, default).strip().lower() or default
    if value not in choices:
        raise ValueError(f"{name} must be one of {', '.join(choices)}, got {value!r}")
    return value


def _env_replay_speed() -> float:
    raw = os.environ.get("VEYRA_REPLAY_SPEED") or "10.0"
    try:
        value = float(raw)
    except ValueError:
        raise ValueError(f"VEYRA_REPLAY_SPEED must be a number, got {raw!r}") from None
    if value < 0:
        raise ValueError(f"VEYRA_REPLAY_SPEED must be >= 0 (0 = instant), got {raw!r}")
    return value


@lru_cache
def get_settings() -> Settings:
    data_dir = Path(os.environ.get("VEYRA_DATA_DIR") or API_DIR / ".data").resolve()
    return Settings(
        data_dir=data_dir,
        database_url=os.environ.get("VEYRA_DATABASE_URL") or f"sqlite:///{(data_dir / 'veyra.db').as_posix()}",
        media_dir=data_dir / "media",
        media_secret=os.environ.get("VEYRA_MEDIA_SECRET") or "dev-media-secret",
        service_token=os.environ.get("VEYRA_SERVICE_TOKEN") or "demo-worker-token",
        sync_jobs=_env_bool("VEYRA_SYNC_JOBS", False),
        replay_speed=_env_replay_speed(),
        perception_mode=_env_choice("VEYRA_PERCEPTION_MODE", "auto", PERCEPTION_MODES),
        llm_mode=_env_choice("VEYRA_LLM_MODE", "auto", LLM_MODES),
        llm_model=os.environ.get("VEYRA_LLM_MODEL") or "claude-opus-5-5",
        demo_mode=_env_bool("VEYRA_DEMO_MODE", True),
    )
