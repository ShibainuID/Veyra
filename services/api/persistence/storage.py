"""Controlled media storage on the local filesystem, with SHA-256 for change detection.

Hashes show that a file has not changed since upload; they do not establish that the captured event is true.
"""

import hashlib
import uuid
from pathlib import Path
from typing import BinaryIO

CHUNK = 1024 * 1024


class MediaTooLarge(Exception):
    pass


class MediaStore:
    def __init__(self, root: Path, max_bytes: int):
        self.root = root
        self.max_bytes = max_bytes

    def path(self, storage_key: str) -> Path:
        path = (self.root / storage_key).resolve()
        if self.root.resolve() not in path.parents:
            raise ValueError("storage key escapes the media root")
        return path

    def save(self, farm_id: uuid.UUID, stream: BinaryIO, suffix: str, enforce_limit: bool = True) -> tuple[str, int, str]:
        """Write the stream to `<farm>/<uuid><suffix>`; return (storage_key, size_bytes, sha256).

        `enforce_limit=False` is for artifacts the service produces itself (tracks files), not for uploads.
        """
        safe_suffix = "".join(c for c in suffix.lower() if c.isalnum() or c == ".")[:10]
        key = f"{farm_id}/{uuid.uuid4()}{safe_suffix}"
        target = self.path(key)
        target.parent.mkdir(parents=True, exist_ok=True)
        digest, size = hashlib.sha256(), 0
        tmp = target.with_suffix(target.suffix + ".part")
        try:
            with tmp.open("wb") as out:
                while chunk := stream.read(CHUNK):
                    size += len(chunk)
                    if enforce_limit and size > self.max_bytes:
                        raise MediaTooLarge
                    digest.update(chunk)
                    out.write(chunk)
            tmp.rename(target)
        finally:
            tmp.unlink(missing_ok=True)
        return key, size, digest.hexdigest()

    def sha256(self, storage_key: str) -> str:
        digest = hashlib.sha256()
        with self.path(storage_key).open("rb") as f:
            while chunk := f.read(CHUNK):
                digest.update(chunk)
        return digest.hexdigest()

    def verify(self, storage_key: str, sha256: str) -> bool:
        digest = hashlib.sha256()
        with self.path(storage_key).open("rb") as f:
            while chunk := f.read(CHUNK):
                digest.update(chunk)
        return digest.hexdigest() == sha256
