"""VEYRA API app factory: routers under `/api/v1`, one error envelope, and DB setup on startup (plan Sections 0-1).

Run from `services/api`: `uv run uvicorn main:app --reload --port 8000`.
"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from domain.errors import CODE_BY_HTTP_STATUS, HTTP_ERROR, DomainError
from persistence.db import init_db, reset_engine
from persistence.seed import seed_if_empty
from routes import animals, audit, auth_routes, demo, enrollments, health, jobs, media

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


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    init_db()
    seed_if_empty()
    yield
    reset_engine()


def create_app() -> FastAPI:
    """Build the app without side effects; the lifespan creates the schema and seeds an empty database."""
    app = FastAPI(title="VEYRA API", version=health.VERSION, lifespan=_lifespan)
    app.add_exception_handler(DomainError, _domain_error)
    app.add_exception_handler(RequestValidationError, _validation_error)
    app.add_exception_handler(StarletteHTTPException, _http_error)
    app.add_exception_handler(Exception, _unhandled_error)
    for router in ROUTERS:
        app.include_router(router, prefix=API_PREFIX)
    return app


app = create_app()
