"""Request dependencies: database session, authenticated user, role checks, and farm-scoped lookups."""

import uuid
from collections.abc import Callable, Iterator
from typing import Annotated, TypeVar

from fastapi import Depends, Header, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from domain.errors import APIError, ErrorCode
from domain.security import token_hash
from persistence.models import User

T = TypeVar("T")


def get_session(request: Request) -> Iterator[Session]:
    yield from request.app.state.db.session()


SessionDep = Annotated[Session, Depends(get_session)]


def current_user(session: SessionDep, authorization: Annotated[str | None, Header()] = None) -> User:
    if not authorization or not authorization.startswith("Bearer "):
        raise APIError(ErrorCode.UNAUTHENTICATED, "Missing bearer token.")
    user = session.scalars(
        select(User).where(User.token_sha256 == token_hash(authorization.removeprefix("Bearer ").strip()), User.active)
    ).first()
    if user is None:
        raise APIError(ErrorCode.UNAUTHENTICATED, "Invalid or inactive token.")
    return user


UserDep = Annotated[User, Depends(current_user)]


def require_roles(*roles: str) -> Callable[[User], User]:
    def check(user: UserDep) -> User:
        if user.role not in roles:
            raise APIError(ErrorCode.FORBIDDEN, f"Role '{user.role}' cannot perform this action.",
                           {"allowed_roles": list(roles)})
        return user

    return check


def get_owned(session: Session, model: type[T], object_id: uuid.UUID, user: User) -> T:
    """Fetch a farm-owned row. Rows of other farms are reported as not found, not forbidden."""
    obj = session.get(model, object_id)
    if obj is None or getattr(obj, "farm_id", None) != user.farm_id:
        raise APIError(ErrorCode.NOT_FOUND, f"{model.__name__} not found.")
    return obj
