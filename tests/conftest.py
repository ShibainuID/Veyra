"""Shared fixtures. Tests run against PostgreSQL (`VEYRA_TEST_DATABASE_URL`, default veyra_test on localhost)."""

import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "services" / "api"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from config import Settings  # noqa: E402
from domain.security import new_token, token_hash  # noqa: E402
from main import create_app  # noqa: E402
from persistence.db import Base, Database  # noqa: E402
from domain.perception import set_perception  # noqa: E402
from fakes import FakePerception  # noqa: E402
from persistence.models import Farm, User  # noqa: E402
from persistence.storage import MediaStore  # noqa: E402
from workers.runner import WorkerContext, run_once  # noqa: E402

TEST_DB_URL = os.getenv("VEYRA_TEST_DATABASE_URL", "postgresql+psycopg://veyra:veyra@localhost:5432/veyra_test")


@pytest.fixture(scope="session")
def db() -> Database:
    database = Database(TEST_DB_URL)
    database.drop_all()
    database.create_all()
    return database


@pytest.fixture(autouse=True)
def clean_tables(db: Database):
    yield
    with db.engine.begin() as conn:
        tables = ", ".join(t.name for t in Base.metadata.sorted_tables)
        conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(database_url=TEST_DB_URL, media_root=tmp_path / "media", max_upload_bytes=1024 * 1024,
                    job_poll_seconds=0.01, job_max_attempts=2)


@pytest.fixture
def client(settings: Settings, db: Database) -> TestClient:
    return TestClient(create_app(settings, db))


@pytest.fixture
def make_user(db: Database):
    """Create a farm (or reuse one) and a user; return (user, auth headers)."""

    def _make(role: str = "manager", farm_id=None) -> tuple[User, dict]:
        with db.sessions() as s:
            if farm_id is None:
                farm = Farm(name="Test Farm", currency="USD")
                s.add(farm)
                s.flush()
                farm_id = farm.id
            token = new_token()
            user = User(farm_id=farm_id, name=f"Test {role}", role=role, token_sha256=token_hash(token))
            s.add(user)
            s.commit()
            s.refresh(user)
            return user, {"Authorization": f"Bearer {token}"}

    return _make


@pytest.fixture(autouse=True)
def fake_perception():
    set_perception(FakePerception())
    yield
    set_perception(None)


@pytest.fixture
def worker(db: Database, settings: Settings):
    """Run queued jobs the way the worker process would; returns how many jobs ran."""
    ctx = WorkerContext(settings, MediaStore(settings.media_root, settings.max_upload_bytes))

    def _drain() -> int:
        n = 0
        while run_once(db, ctx):
            n += 1
        return n

    return _drain
