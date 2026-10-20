"""Veyra API application: `uvicorn main:app` from services/api."""

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from config import Settings
from domain.errors import APIError, ErrorCode
from persistence.db import Database
from persistence.storage import MediaStore
from routes import alerts, animals, cameras, demo, enrollments, foundation


def create_app(settings: Settings | None = None, db: Database | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    app = FastAPI(title="Veyra API", version="0.1.0")
    app.state.settings = settings
    app.state.db = db or Database(settings.database_url)
    app.state.media = MediaStore(settings.media_root, settings.max_upload_bytes)

    @app.exception_handler(APIError)
    async def api_error(_: Request, exc: APIError) -> JSONResponse:
        return JSONResponse(exc.body(), status_code=exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        # Drop `ctx`, which can hold exception objects that are not JSON-serialisable.
        errors = [{k: v for k, v in e.items() if k != "ctx"} for e in exc.errors()]
        err = APIError(ErrorCode.VALIDATION_FAILED, "Request validation failed.", {"errors": errors})
        return JSONResponse(err.body(), status_code=err.status_code)

    for router in (foundation.router, enrollments.router, animals.router, cameras.router, alerts.router, demo.router):
        app.include_router(router, prefix="/api/v1")
    return app


app = create_app()
