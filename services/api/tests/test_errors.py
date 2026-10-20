import pytest
from fastapi import APIRouter
from pydantic import BaseModel

from domain.errors import STATUS_BY_CODE, DomainError


class _Body(BaseModel):
    count: int


@pytest.fixture
def error_client(app, client):
    router = APIRouter()

    @router.get("/boom")
    def boom():
        raise DomainError("APPROVAL_STALE", "The approval no longer matches the action.", {"x": 1})

    @router.post("/echo")
    def echo(body: _Body):
        return body

    app.include_router(router, prefix="/api/v1/test")
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
    assert isinstance(error["details"], list) and error["details"]
    assert error["details"][0]["loc"] == ["body", "count"]


def test_unknown_route_returns_not_found_envelope(client):
    response = client.get("/api/v1/does-not-exist")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


def test_status_is_derived_from_code():
    assert DomainError("FORBIDDEN_ROLE", "no").status == 403
    assert DomainError("NOT_FOUND", "missing").details == {}
    assert STATUS_BY_CODE["IDEMPOTENCY_KEY_REQUIRED"] == 400
    assert len(STATUS_BY_CODE) == 13


def test_unknown_code_is_rejected():
    with pytest.raises(ValueError):
        DomainError("NOT_A_CODE", "nope")
