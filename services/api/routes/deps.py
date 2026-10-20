"""FastAPI auth dependencies. Failures raise `DomainError`, so they use the error envelope.

`current_principal` reads `Authorization: Bearer <token>` and looks the user up in its own short read session,
so it never holds the write lock. `require_roles(*roles)` builds a dependency that also checks the role.
`service_principal` checks `X-Service-Token` for the internal worker; `service_or_roles(*roles)` accepts either.
"""

from collections.abc import Callable

from fastapi import Depends
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer

from config import get_settings
from domain.auth import Principal, ServicePrincipal, authenticate, authenticate_service, require_role
from persistence.db import read_session

_bearer = HTTPBearer(auto_error=False, description="A demo user token, e.g. `demo-manager`.")
_service_token = APIKeyHeader(name="X-Service-Token", auto_error=False, description="The internal worker token.")


def current_principal(credentials: HTTPAuthorizationCredentials | None = Depends(_bearer)) -> Principal:
    with read_session() as session:
        return authenticate(session, credentials.credentials if credentials else None)


def require_roles(*roles: str) -> Callable[..., Principal]:
    def dependency(principal: Principal = Depends(current_principal)) -> Principal:
        require_role(principal, *roles)
        return principal

    return dependency


def service_principal(token: str | None = Depends(_service_token)) -> ServicePrincipal:
    return authenticate_service(token, get_settings())


def service_or_roles(*roles: str) -> Callable[..., Principal | ServicePrincipal]:
    """The worker's service token when one is sent, else a bearer token with one of `roles`."""

    def dependency(token: str | None = Depends(_service_token),
                   credentials: HTTPAuthorizationCredentials | None = Depends(_bearer)) -> Principal | ServicePrincipal:
        if token:
            return authenticate_service(token, get_settings())
        principal = current_principal(credentials)
        require_role(principal, *roles)
        return principal

    return dependency
