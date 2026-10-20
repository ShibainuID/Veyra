"""Demo authentication and role capabilities.

People present a seeded bearer token; the internal worker presents `X-Service-Token`. A token is looked up and
then compared in constant time. Every farm-scoped query uses `Principal.farm_id`, and a record of another farm
is reported as `NOT_FOUND`. Role capabilities are named tuples of roles so routes read as rules.
"""

import hmac
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from config import Settings
from domain.errors import DomainError
from persistence.models import User

ALL_ROLES = ("manager", "operator", "vet", "assessor")
APPROVERS = ("manager",)
ENROLLERS = ("manager", "operator")
ALERT_REVIEWERS = ("manager", "operator", "vet")
SERVICE_ACTOR_ID = "service-worker"


@dataclass(frozen=True)
class Principal:
    user_id: str
    farm_id: str
    role: str
    name: str


@dataclass(frozen=True)
class ServicePrincipal:
    actor_id: str = SERVICE_ACTOR_ID


def _same(expected: str, given: str) -> bool:
    return hmac.compare_digest(expected.encode(), given.encode())


def authenticate(session: Session, token: str | None) -> Principal:
    if not token:
        raise DomainError("UNAUTHENTICATED", "Sign in with a bearer token.")
    user = session.scalar(select(User).where(User.token == token))
    if user is None or not _same(user.token, token):
        raise DomainError("UNAUTHENTICATED", "The bearer token is not valid.")
    return Principal(user_id=user.id, farm_id=user.farm_id, role=user.role, name=user.name)


def require_role(principal: Principal, *roles: str) -> None:
    if principal.role not in roles:
        raise DomainError("FORBIDDEN_ROLE", f"This needs the {' or '.join(roles)} role.",
                          {"required": list(roles), "role": principal.role})


def authenticate_service(header_value: str | None, settings: Settings) -> ServicePrincipal:
    expected = settings.service_token
    if not header_value or not expected or not _same(expected, header_value):
        raise DomainError("UNAUTHENTICATED", "A valid service token is required.")
    return ServicePrincipal()
