"""Create tables and a demo farm with one user per role: `python seed.py` from services/api.

Tokens are printed once and written to var/dev_tokens.json (gitignored). Re-running issues new tokens
for the same users instead of creating duplicates.
"""

import json

from sqlalchemy import select

from config import SERVICE_ROOT, Settings
from domain import audit
from domain.security import new_token, token_hash
from persistence.db import Database
from persistence.models import Farm, User

DEMO_FARM = "Veyra Demo Farm"
DEMO_USERS = (
    ("Farm Manager", "manager"),
    ("Farm Operator", "operator"),
    ("Farm Veterinarian", "veterinarian"),
    ("Sandbox Insurance Assessor", "assessor"),
    ("Camera Worker", "service"),
)


def seed(db: Database) -> dict[str, str]:
    db.create_all()
    tokens = {}
    with db.sessions() as session:
        farm = session.scalars(select(Farm).where(Farm.name == DEMO_FARM)).first()
        if farm is None:
            farm = Farm(name=DEMO_FARM, currency="USD")
            session.add(farm)
            session.flush()
            audit.record(session, farm.id, "farm.created", "farm", farm.id, actor_type="system")
        for name, role in DEMO_USERS:
            token = new_token()
            user = session.scalars(select(User).where(User.farm_id == farm.id, User.role == role)).first()
            if user is None:
                user = User(farm_id=farm.id, name=name, role=role, token_sha256=token_hash(token))
                session.add(user)
            else:
                user.token_sha256 = token_hash(token)
            tokens[role] = token
        session.commit()
    return tokens


if __name__ == "__main__":
    import sys

    database = Database(Settings.from_env().database_url)
    if "--reset" in sys.argv:
        # Development only: drops every table, then recreates the schema and demo users.
        database.drop_all()
    tokens = seed(database)
    out = SERVICE_ROOT / "var" / "dev_tokens.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(tokens, indent=1))
    print(f"Seeded {DEMO_FARM}. Bearer tokens written to {out}")
