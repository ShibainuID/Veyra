import asyncio
import time
from collections import Counter

import anyio.to_thread
import httpx
from fastapi import APIRouter, Depends
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from domain.errors import DomainError
from main import API_PREFIX
from persistence.db import get_session
from persistence.models import Farm

REQUESTS = 300
BURST_TIMEOUT_S = 60


def _add_probe_routes(app) -> None:
    router = APIRouter()

    @router.post("/test-only/write")
    def write(session: Session = Depends(get_session)) -> dict:
        session.scalar(select(Farm.id).limit(1))
        time.sleep(0.002)
        session.commit()
        return {"ok": True}

    @router.post("/test-only/fail")
    def fail(session: Session = Depends(get_session)) -> dict:
        session.scalar(select(Farm.id).limit(1))
        raise DomainError("NOT_FOUND", "Probe failure.")

    app.include_router(router, prefix=API_PREFIX)


async def _burst(app) -> Counter:
    anyio.to_thread.current_default_thread_limiter().total_tokens = 3
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test", timeout=BURST_TIMEOUT_S) as client:
        paths = [f"{API_PREFIX}/test-only/{'fail' if i % 2 else 'write'}" for i in range(REQUESTS)]
        responses = await asyncio.wait_for(asyncio.gather(*(client.post(path) for path in paths)), BURST_TIMEOUT_S)
    return Counter((r.request.url.path.rsplit("/", 1)[-1], r.status_code) for r in responses)


def test_concurrent_writing_requests_never_trip_the_writer_guard(app):
    """A request's dependency teardown can run on another worker thread than its route, so the writer guard must
    follow the request, not the thread: the route's thread may already be serving the next request."""
    _add_probe_routes(app)
    with TestClient(app):
        pass

    counts = asyncio.run(_burst(app))

    assert counts == {("write", 200): REQUESTS // 2, ("fail", 404): REQUESTS // 2}
