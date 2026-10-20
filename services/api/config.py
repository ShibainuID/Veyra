"""Service settings from the environment (run, tests, auth).

Every value has a demo-safe default so `uv run uvicorn main:app` works with no setup. Tests set the
environment and call `get_settings.cache_clear()` to pick up the change.
"""

import os
import secrets
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

API_DIR = Path(__file__).resolve().parent
REPO_ROOT = API_DIR.parents[1]

PERCEPTION_MODES = ("auto", "prototype", "fixture")
LLM_MODES = ("auto", "live", "offline")
LLM_PROVIDERS = ("openai", "anthropic")
# The model each provider uses unless VEYRA_LLM_MODEL names another.
DEFAULT_LLM_MODELS = {"openai": "gpt-6-luna", "anthropic": "claude-opus-5-5"}

# Without VEYRA_MEDIA_SECRET, signed media URLs use a per-process secret: they stop working after a restart.
_PROCESS_MEDIA_SECRET = secrets.token_hex(32)


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
    llm_provider: str
    llm_model: str
    demo_mode: bool
    repo_root: Path = REPO_ROOT
    fixtures_dir: Path = REPO_ROOT / "demo" / "fixtures"
    scenarios_dir: Path = REPO_ROOT / "demo" / "scenarios"
    # Ultralytics name (downloaded on first use) or a local path, e.g. pre-fetched weights on an offline demo machine.
    yolo_weights: str = "yolov8x-seg.pt"


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


def load_env_file(path: Path = REPO_ROOT / ".env") -> list[str]:
    """Fill unset variables from the repo's `.env`, so `uv run uvicorn main:app` reads the file compose reads.

    Lines are `KEY=VALUE` (an `export ` prefix and surrounding quotes are allowed); comments, blank lines, and
    empty values are skipped, and a variable already in the environment always wins. Returns the keys it set.
    """
    if not path.is_file():
        return []
    loaded = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.removeprefix("export ").split("=", 1)
        key, value = key.strip(), value.strip().strip("'\"")
        if key and value and key not in os.environ:
            os.environ[key] = value
            loaded.append(key)
    return loaded


@lru_cache
def get_settings() -> Settings:
    data_dir = Path(os.environ.get("VEYRA_DATA_DIR") or API_DIR / ".data").resolve()
    provider = _env_choice("VEYRA_LLM_PROVIDER", "openai", LLM_PROVIDERS)
    return Settings(
        data_dir=data_dir,
        database_url=os.environ.get("VEYRA_DATABASE_URL") or f"sqlite:///{(data_dir / 'veyra.db').as_posix()}",
        media_dir=data_dir / "media",
        media_secret=os.environ.get("VEYRA_MEDIA_SECRET") or _PROCESS_MEDIA_SECRET,
        service_token=os.environ.get("VEYRA_SERVICE_TOKEN") or "demo-worker-token",
        sync_jobs=_env_bool("VEYRA_SYNC_JOBS", False),
        replay_speed=_env_replay_speed(),
        perception_mode=_env_choice("VEYRA_PERCEPTION_MODE", "auto", PERCEPTION_MODES),
        llm_mode=_env_choice("VEYRA_LLM_MODE", "auto", LLM_MODES),
        llm_provider=provider,
        llm_model=os.environ.get("VEYRA_LLM_MODEL") or DEFAULT_LLM_MODELS[provider],
        demo_mode=_env_bool("VEYRA_DEMO_MODE", True),
        yolo_weights=os.environ.get("VEYRA_YOLO_WEIGHTS") or "yolov8x-seg.pt",
    )
