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
    yolo_weights: str = "yolov8x-seg.pt"
    # Fine-tuned barn camera detector (models/MODEL_CARD.md).
    calf_detector_weights: str = str(SERVICE_ROOT / "models" / "calf_detector_v1.pt")
    # Enables /demo endpoints that replay labelled fixture scenarios.
    demo_mode: bool = False
    fixtures_root: Path = SERVICE_ROOT.parents[1] / "demo" / "fixtures"
    # Illustrative demo price, not a market quote (USD 4.00/kg).
    demo_price_minor_per_kg: int = 400

    @classmethod
    def from_env(cls) -> "Settings":
        var = SERVICE_ROOT / "var"
        return cls(
            database_url=os.getenv("VEYRA_DATABASE_URL", "postgresql+psycopg://veyra:veyra@localhost:5432/veyra"),
            media_root=Path(os.getenv("VEYRA_MEDIA_ROOT", str(var / "media"))),
            max_upload_bytes=int(os.getenv("VEYRA_MAX_UPLOAD_MB", "500")) * 1024 * 1024,
            job_poll_seconds=float(os.getenv("VEYRA_JOB_POLL_SECONDS", "1.0")),
            job_max_attempts=int(os.getenv("VEYRA_JOB_MAX_ATTEMPTS", "2")),
            yolo_weights=os.getenv("VEYRA_YOLO_WEIGHTS", str(var / "models" / "yolov8x-seg.pt")),
            demo_price_minor_per_kg=int(os.getenv("VEYRA_DEMO_PRICE_MINOR_PER_KG", "400")),
            calf_detector_weights=os.getenv("VEYRA_CALF_DETECTOR_WEIGHTS", str(SERVICE_ROOT / "models" / "calf_detector_v1.pt")),
            demo_mode=os.getenv("VEYRA_DEMO_MODE", "0") == "1",
            fixtures_root=Path(os.getenv("VEYRA_FIXTURES_ROOT", str(SERVICE_ROOT.parents[1] / "demo" / "fixtures"))),
        )
