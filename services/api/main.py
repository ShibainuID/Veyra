"""VEYRA API app factory: routers under `/api/v1`, one error envelope, and DB setup on startup (plan Sections 0-1).

Run from `services/api`: `uv run uvicorn main:app --reload --port 8000`.
"""

import logging
import os
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from config import load_env_file
from domain.actions import recover_stranded
from domain.errors import CODE_BY_HTTP_STATUS, HTTP_ERROR, DomainError
from persistence.db import init_db, reset_engine, writer_scope
from persistence.seed import seed_if_empty
from routes import (
    alerts, animals, assistant, audit, auth_routes, demo, enrollments, health, jobs, media, monitoring,
)
from routes import agent, claims, incidents, insurance, valuations, wallet  # financial core (B4)
from routes import gallery  # camera muzzle gallery sync
from routes import agent_chat  # the in-app VEYRA agent conversations
from workers.jobs import recover_interrupted

API_PREFIX = "/api/v1"

ROUTERS = [
    health.router,
    auth_routes.router,
    animals.router,
    audit.router,
    enrollments.router,
    jobs.router,
    media.router,
    demo.router,
    gallery.router,  # before monitoring: `/cameras/gallery/publish` is a fixed path
    monitoring.router,
    alerts.router,
    assistant.router,
    valuations.router,
    insurance.router,
    agent.router,
    agent_chat.router,
    wallet.router,
    incidents.router,
    claims.router,
]

logger = logging.getLogger("veyra.api")


def _envelope(status: int, code: str, message: str, details, headers: dict | None = None) -> JSONResponse:
    content = {"error": {"code": code, "message": message, "details": details}}
    return JSONResponse(status_code=status, content=content, headers=headers)


async def _domain_error(request: Request, exc: DomainError) -> JSONResponse:
    return _envelope(exc.status, exc.code, exc.message, jsonable_encoder(exc.details))


async def _validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    errors = jsonable_encoder(exc.errors(), custom_encoder={Exception: str})
    return _envelope(422, "VALIDATION_FAILED", "The request is not valid.", {"errors": errors})


async def _http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    code = CODE_BY_HTTP_STATUS.get(exc.status_code, HTTP_ERROR)
    message = "Resource not found." if exc.status_code == 404 else str(exc.detail)
    return _envelope(exc.status_code, code, message, {}, headers=exc.headers)


async def _unhandled_error(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return _envelope(500, "INTERNAL_ERROR", "Something went wrong on the server.", {})


class _WriterScopeMiddleware:
    """Each HTTP request gets its own writer slot (see `persistence.db.writer_scope`)."""

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        with writer_scope():
            await self.app(scope, receive, send)


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    init_db()
    seed_if_empty()
    recover_interrupted()  # jobs a previous process left queued or running can never finish
    recover_stranded()  # executions left `executing` by a previous process become `unknown`
    yield
    reset_engine()


def create_app() -> FastAPI:
    """Build the app without side effects; the lifespan creates the schema and seeds an empty database."""
    app = FastAPI(title="VEYRA API", version=health.VERSION, lifespan=_lifespan)
    app.add_exception_handler(DomainError, _domain_error)
    app.add_exception_handler(RequestValidationError, _validation_error)
    app.add_exception_handler(StarletteHTTPException, _http_error)
    app.add_exception_handler(Exception, _unhandled_error)
    app.add_middleware(_WriterScopeMiddleware)
    for router in ROUTERS:
        app.include_router(router, prefix=API_PREFIX)
    web_dist = os.environ.get("VEYRA_WEB_DIST")
    if web_dist and (Path(web_dist) / "index.html").is_file():
        _mount_web(app, Path(web_dist).resolve())
    return app


def _mount_web(app: FastAPI, dist: Path) -> None:
    """Serve the built web app from the same origin (the Docker image); `/api` keeps its JSON 404s."""
    if (dist / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def web(path: str) -> FileResponse:
        if path == "api" or path.startswith("api/"):
            raise StarletteHTTPException(status_code=404)
        candidate = (dist / path).resolve()
        if path and candidate.is_file() and candidate.is_relative_to(dist):
            return FileResponse(candidate)
        return FileResponse(dist / "index.html")  # client-side routes such as /animals/:id


# `uv run uvicorn main:app` reads the repo's .env like docker compose does; tests keep their own environment.
if "pytest" not in sys.modules:
    load_env_file()
app = create_app()
