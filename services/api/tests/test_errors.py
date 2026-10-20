import pytest
from fastapi import APIRouter, HTTPException
from fastapi.testclient import TestClient
from pydantic import BaseModel

from domain.errors import STATUS_BY_CODE, DomainError


class _Body(BaseModel):
    count: int


@pytest.fixture
def test_router(app):
    router = APIRouter()

    @router.get("/boom")
    def boom():
        raise DomainError("APPROVAL_STALE", "The approval no longer matches the action.", {"x": 1})

    @router.post("/echo")
    def echo(body: _Body):
        return body

    @router.get("/login")
    def login():
        raise HTTPException(401, "Missing bearer token.", headers={"WWW-Authenticate": "Bearer"})

    @router.get("/teapot")
    def teapot():
        raise HTTPException(418, "Short and stout.")

    @router.get("/crash")
    def crash():
        raise RuntimeError("secret internals")

    app.include_router(router, prefix="/api/v1/test")
    return app


@pytest.fixture
def error_client(test_router, client):
    return client


def test_domain_error_maps_to_envelope(error_client):
    response = error_client.get("/api/v1/test/boom")

    assert response.status_code == 409
    assert response.json() == {
        "error": {
            "code": "APPROVAL_STALE",
            "message": "The approval no longer matches the action.",
            "details": {"x": 1},
        }
    }


def test_validation_error_maps_to_envelope(error_client):
    response = error_client.post("/api/v1/test/echo", json={"count": "not-a-number"})

    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "VALIDATION_FAILED"
    assert error["details"]["errors"][0]["loc"] == ["body", "count"]


def test_malformed_body_maps_to_envelope(error_client):
    response = error_client.post("/api/v1/test/echo", content=b"\xff",
                                 headers={"content-type": "application/json"})

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "BAD_REQUEST"


def test_unknown_route_returns_not_found_envelope(client):
    response = client.get("/api/v1/does-not-exist")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


def test_wrong_method_returns_envelope(client):
    response = client.post("/api/v1/health")

    assert response.status_code == 405
    assert response.json()["error"]["code"] == "METHOD_NOT_ALLOWED"


def test_http_401_keeps_headers(error_client):
    response = error_client.get("/api/v1/test/login")

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert response.json() == {"error": {"code": "UNAUTHENTICATED", "message": "Missing bearer token.", "details": {}}}


def test_other_http_status_uses_http_error(error_client):
    response = error_client.get("/api/v1/test/teapot")

    assert response.status_code == 418
    assert response.json()["error"] == {"code": "HTTP_ERROR", "message": "Short and stout.", "details": {}}


def test_unhandled_exception_returns_internal_error(test_router):
    with TestClient(test_router, raise_server_exceptions=False) as crash_client:
        response = crash_client.get("/api/v1/test/crash")

    assert response.status_code == 500
    error = response.json()["error"]
    assert error["code"] == "INTERNAL_ERROR"
    assert "secret internals" not in error["message"]


def test_status_is_derived_from_code():
    assert DomainError("FORBIDDEN_ROLE", "no").status == 403
    assert DomainError("NOT_FOUND", "missing").details == {}
    assert STATUS_BY_CODE["IDEMPOTENCY_KEY_REQUIRED"] == 400
    assert STATUS_BY_CODE["METHOD_NOT_ALLOWED"] == 405
    assert STATUS_BY_CODE["INTERNAL_ERROR"] == 500


@pytest.mark.parametrize("code", ["NOT_A_CODE", "HTTP_ERROR"])
def test_unknown_code_is_rejected(code):
    with pytest.raises(ValueError):
        DomainError(code, "nope")
