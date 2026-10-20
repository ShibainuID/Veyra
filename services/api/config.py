"""Service settings from environment variables, with local defaults for the hackathon."""

import os
from dataclasses import dataclass
from pathlib import Path

SERVICE_ROOT = Path(__file__).resolve().parent


@dataclass(frozen=True)
class Settings:
    database_url: str
    media_root: Path
    max_upload_bytes: int
    job_poll_seconds: float
    job_max_attempts: int

    @classmethod
    def from_env(cls) -> "Settings":
        var = SERVICE_ROOT / "var"
        return cls(
            database_url=os.getenv("VEYRA_DATABASE_URL", "postgresql+psycopg://veyra:veyra@localhost:5432/veyra"),
            media_root=Path(os.getenv("VEYRA_MEDIA_ROOT", str(var / "media"))),
            max_upload_bytes=int(os.getenv("VEYRA_MAX_UPLOAD_MB", "500")) * 1024 * 1024,
            job_poll_seconds=float(os.getenv("VEYRA_JOB_POLL_SECONDS", "1.0")),
            job_max_attempts=int(os.getenv("VEYRA_JOB_MAX_ATTEMPTS", "2")),
        )
