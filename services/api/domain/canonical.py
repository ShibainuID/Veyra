"""Canonical JSON and SHA-256 (payloads are hashed as keys-sorted, compact JSON)."""

import hashlib
import json


def canonical_json(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_hex(value) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()
