"""VEYRA API app factory: routers under `/api/v1` and the error envelope (plan Sections 0-1).

Run from `services/api`: `uv run uvicorn main:app --reload --port 8000`.
"""

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from domain.errors import DomainError
from routes import health

API_PREFIX = "/api/v1"

ROUTERS = [
    health.router,
]


def _envelope(status: int, code: str, message: str, details) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": {"code": code, "message": message, "details": details}})


async def _domain_error(request: Request, exc: DomainError) -> JSONResponse:
    return _envelope(exc.status, exc.code, exc.message, jsonable_encoder(exc.details))


async def _validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    details = jsonable_encoder(exc.errors(), custom_encoder={Exception: str})
    return _envelope(422, "VALIDATION_FAILED", "The request is not valid.", details)


async def _http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    if exc.status_code == 404:
        return _envelope(404, "NOT_FOUND", "Resource not found.", {})
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail}, headers=exc.headers)


def create_app() -> FastAPI:
    app = FastAPI(title="VEYRA API", version=health.VERSION)
    app.add_exception_handler(DomainError, _domain_error)
    app.add_exception_handler(RequestValidationError, _validation_error)
    app.add_exception_handler(StarletteHTTPException, _http_error)
    for router in ROUTERS:
        app.include_router(router, prefix=API_PREFIX)
    return app


app = create_app()
