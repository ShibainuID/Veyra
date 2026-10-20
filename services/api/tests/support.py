"""Test helpers shared across modules: request headers for the seeded demo users."""


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


MANAGER = bearer("demo-manager")
OPERATOR = bearer("demo-operator")
VET = bearer("demo-vet")
ASSESSOR = bearer("demo-assessor")
OTHER_FARM = bearer("other-farm-manager")
