from dataclasses import replace

import pytest
from fastapi import APIRouter, Depends
from fastapi.testclient import TestClient

from domain.auth import ServicePrincipal, authenticate_service
from domain.errors import DomainError
from main import API_PREFIX
from routes.deps import service_principal
from tests.support import ASSESSOR, MANAGER, OPERATOR, OTHER_FARM, VET, bearer


def _assert_error(response, status: int, code: str) -> dict:
    assert response.status_code == status, response.text
    body = response.json()
    assert set(body) == {"error"}
    assert set(body["error"]) == {"code", "message", "details"}
    assert body["error"]["code"] == code
    return body["error"]


def test_missing_token_is_unauthenticated(client):
    error = _assert_error(client.get("/api/v1/auth/whoami"), 401, "UNAUTHENTICATED")

    assert error["details"] == {}
    assert error["message"]


@pytest.mark.parametrize("headers", [
    bearer("not-a-token"),
    bearer(""),
    {"Authorization": "demo-manager"},
    {"Authorization": "Basic demo-manager"},
    bearer("demo-manager-extra"),
], ids=["unknown", "empty", "no-scheme", "wrong-scheme", "prefix"])
def test_bad_token_is_unauthenticated(client, headers):
    _assert_error(client.get("/api/v1/auth/whoami", headers=headers), 401, "UNAUTHENTICATED")


@pytest.mark.parametrize("headers, user_id, name, role, farm", [
    (MANAGER, "user-manager", "W. Santoso", "manager", ("farm-wahyu", "Wahyu Farms")),
    (OPERATOR, "user-operator", "A. Pratama", "operator", ("farm-wahyu", "Wahyu Farms")),
    (VET, "user-vet", "dr. R. Lestari", "vet", ("farm-wahyu", "Wahyu Farms")),
    (ASSESSOR, "user-assessor", "Sandbox Mutual Assessor", "assessor", ("farm-wahyu", "Wahyu Farms")),
    (OTHER_FARM, "user-other-manager", "Other Manager", "manager", ("farm-other", "Other Farm")),
])
def test_whoami_for_each_role(client, headers, user_id, name, role, farm):
    response = client.get("/api/v1/auth/whoami", headers=headers)

    assert response.status_code == 200
    assert response.json() == {"user_id": user_id, "name": name, "role": role,
                               "farm": {"id": farm[0], "name": farm[1]}}


def test_other_farm_cannot_see_passport(client):
    _assert_error(client.get("/api/v1/animals/animal-demo-002/passport", headers=OTHER_FARM), 404, "NOT_FOUND")


def test_other_farm_sees_only_its_own_herd_and_audit(client):
    animals = client.get("/api/v1/animals", headers=OTHER_FARM).json()
    events = client.get("/api/v1/audit-events", headers=OTHER_FARM, params={"animal_id": "animal-demo-002"}).json()

    assert [item["id"] for item in animals["items"]] == ["animal-other-001"]
    assert animals["summary"]["wallet_balance_minor"] == 0
    assert events == []


def test_unknown_animal_is_not_found(client):
    _assert_error(client.get("/api/v1/animals/animal-demo-999/passport", headers=MANAGER), 404, "NOT_FOUND")


@pytest.mark.parametrize("path", ["/api/v1/animals", "/api/v1/animals/animal-demo-002/passport",
                                  "/api/v1/audit-events", "/api/v1/demo/settings"])
def test_read_routes_require_a_token(client, path):
    _assert_error(client.get(path), 401, "UNAUTHENTICATED")


def test_operator_cannot_reset(client):
    error = _assert_error(client.post("/api/v1/demo/reset", headers=OPERATOR), 403, "FORBIDDEN_ROLE")

    assert error["details"] == {"required": ["manager"], "role": "operator"}


def test_other_farm_manager_cannot_reset_the_demo(client):
    error = _assert_error(client.post("/api/v1/demo/reset", headers=OTHER_FARM), 403, "FORBIDDEN_ROLE")

    assert error["details"] == {"required": ["manager"], "role": "manager", "farm_id": "farm-wahyu"}
    assert client.get("/api/v1/animals", headers=MANAGER).json()["summary"]["animal_count"] == 5


def test_manager_can_reset(client):
    response = client.post("/api/v1/demo/reset", headers=MANAGER)

    assert response.status_code == 200
    assert response.json()["animals"] == 5


def test_demo_settings_roles(client):
    body = {"payment_mode": "fail", "insurer_activation": "confirm"}

    assert client.get("/api/v1/demo/settings", headers=VET).status_code == 200
    _assert_error(client.put("/api/v1/demo/settings", json=body, headers=OPERATOR), 403, "FORBIDDEN_ROLE")
    _assert_error(client.put("/api/v1/demo/settings", json=body), 401, "UNAUTHENTICATED")
    _assert_error(client.get("/api/v1/demo/settings", headers=OTHER_FARM), 404, "NOT_FOUND")
    assert client.put("/api/v1/demo/settings", json=body, headers=MANAGER).status_code == 200


@pytest.fixture
def service_client(app):
    router = APIRouter()

    @router.get("/test-only/service")
    def probe(principal: ServicePrincipal = Depends(service_principal)) -> dict:
        return {"actor_id": principal.actor_id}

    app.include_router(router, prefix=API_PREFIX)
    with TestClient(app) as test_client:
        yield test_client


@pytest.mark.parametrize("headers", [{}, {"X-Service-Token": ""}, {"X-Service-Token": "wrong"}, MANAGER],
                         ids=["missing", "empty", "wrong", "bearer-user"])
def test_service_token_rejected(service_client, headers):
    _assert_error(service_client.get("/api/v1/test-only/service", headers=headers), 401, "UNAUTHENTICATED")


def test_service_token_accepted(service_client, settings_env):
    response = service_client.get("/api/v1/test-only/service", headers={"X-Service-Token": settings_env.service_token})

    assert response.status_code == 200
    assert response.json() == {"actor_id": "service-worker"}


def test_authenticate_service_rejects_empty_configured_token(settings_env):
    with pytest.raises(DomainError) as raised:
        authenticate_service("", replace(settings_env, service_token=""))
    assert raised.value.code == "UNAUTHENTICATED"
    assert authenticate_service(settings_env.service_token, settings_env) == ServicePrincipal()
