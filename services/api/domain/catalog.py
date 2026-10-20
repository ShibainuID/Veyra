"""The sample policy catalog (`demo/fixtures/policies.json`, version `sample-v1`).

The catalog is fictional and read-only. Every rule, price, and exclusion carries a `terms_ref`, the only
references an explanation may cite.
"""

import json
from functools import lru_cache
from pathlib import Path

from config import get_settings
from domain.errors import DomainError


@lru_cache
def _read(path: Path, mtime_ns: int) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def load_catalog() -> dict:
    path = get_settings().fixtures_dir / "policies.json"
    return _read(path, path.stat().st_mtime_ns)


def get_product(catalog: dict, product_id: str) -> dict:
    for product in catalog["products"]:
        if product["product_id"] == product_id:
            return product
    raise DomainError("NOT_FOUND", "Policy product not found.", {"product_id": product_id})


def provider_name(catalog: dict, provider_id: str) -> str:
    provider = catalog["provider"]
    return provider["name"] if provider["id"] == provider_id else provider_id


def terms_refs(catalog: dict) -> set[str]:
    """Every `terms_ref` in the catalog, found anywhere in its structure."""
    found: set[str] = set()

    def walk(node) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if key == "terms_ref" and isinstance(value, str):
                    found.add(value)
                else:
                    walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(catalog)
    return found
