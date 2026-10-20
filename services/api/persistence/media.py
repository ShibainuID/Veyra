"""Local media storage behind signed URLs (plan Section 1: media on disk, served by signature).

Files live at `<media_dir>/<farm_id>/<media_id>.<ext>`; the row stores that path relative to `media_dir`,
plus the SHA-256 that evidence manifests cite. A URL carries `exp` and `sig = HMAC-SHA256(secret, "id:exp")`,
and the signature is the only credential, so `GET /media/{id}` needs no bearer token. Inputs are checked
before anything is written: the farm id and extension must be plain tokens, the target must stay inside
`media_dir`, and the content type must be on the allow-list for the media kind.
"""

import hashlib
import hmac
import os
import re
import shutil
from pathlib import Path

from sqlalchemy.orm import Session

from config import get_settings
from domain import clock
from domain.ids import new_id
from persistence.models import Media

IMAGE_TYPES = frozenset({"image/jpeg", "image/png", "image/webp"})
CONTENT_TYPES: dict[str, frozenset[str]] = {
    "video": frozenset({"video/mp4", "video/webm", "video/quicktime"}),
    "frame": IMAGE_TYPES,
    "crop": IMAGE_TYPES,
    "clip": frozenset({"video/mp4", "video/webm", "image/jpeg"}),
    "document": frozenset({"application/pdf", "image/jpeg", "image/png"}),
}
MEDIA_KINDS = tuple(CONTENT_TYPES)
_FARM_ID = re.compile(r"[a-z0-9-]{1,64}")
_EXT = re.compile(r"[a-z0-9]{1,8}")
_CHUNK = 1 << 20


def _new_media(farm_id: str, kind: str, content_type: str, ext: str) -> tuple[str, str, str, Path]:
    """Validate the inputs and return (media_id, relative path, normalized content type, target path)."""
    if kind not in CONTENT_TYPES:
        raise ValueError(f"unknown media kind {kind!r}")
    content_type = content_type.split(";")[0].strip().lower()
    if content_type not in CONTENT_TYPES[kind]:
        raise ValueError(f"content type {content_type!r} is not allowed for {kind} media")
    ext = ext.lstrip(".").lower()
    if not _EXT.fullmatch(ext):
        raise ValueError(f"unsafe media extension {ext!r}")
    if not _FARM_ID.fullmatch(farm_id):
        raise ValueError(f"unsafe farm id {farm_id!r}")
    media_id = new_id("media")
    relative = f"{farm_id}/{media_id}.{ext}"
    media_dir = get_settings().media_dir.resolve()
    target = media_dir / relative
    if not target.resolve().is_relative_to(media_dir):
        raise ValueError(f"media path escapes the media dir: {relative!r}")
    target.parent.mkdir(parents=True, exist_ok=True)
    return media_id, relative, content_type, target


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(_CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


def _add_row(session: Session, media: Media, target: Path) -> Media:
    try:
        session.add(media)
        session.flush()
    except Exception:
        target.unlink(missing_ok=True)
        raise
    return media


def store_bytes(session: Session, farm_id: str, kind: str, data: bytes, content_type: str, ext: str) -> Media:
    media_id, relative, content_type, target = _new_media(farm_id, kind, content_type, ext)
    target.write_bytes(data)
    media = Media(id=media_id, farm_id=farm_id, kind=kind, path=relative, sha256=hashlib.sha256(data).hexdigest(),
                  content_type=content_type, bytes=len(data))
    return _add_row(session, media, target)


def store_file(session: Session, farm_id: str, kind: str, src_path: Path, content_type: str) -> Media:
    src_path = Path(src_path)
    media_id, relative, content_type, target = _new_media(farm_id, kind, content_type, src_path.suffix or "bin")
    shutil.copyfile(src_path, target)
    media = Media(id=media_id, farm_id=farm_id, kind=kind, path=relative, sha256=_file_sha256(target),
                  content_type=content_type, bytes=target.stat().st_size)
    return _add_row(session, media, target)


def place_file(farm_id: str, kind: str, src_path: Path, content_type: str, sha256: str, size: int) -> Media:
    """Move an already-hashed file into the media dir and return its row, not yet added to a session.

    For large uploads: hash while receiving, move (`os.replace`, same volume) before any writing transaction
    opens, then add only the row in a short transaction; on rollback, unlink `media_path(media)`.
    """
    src_path = Path(src_path)
    media_id, relative, content_type, target = _new_media(farm_id, kind, content_type, src_path.suffix or "bin")
    os.replace(src_path, target)
    return Media(id=media_id, farm_id=farm_id, kind=kind, path=relative, sha256=sha256, content_type=content_type,
                 bytes=size)


def media_path(media: Media) -> Path:
    return get_settings().media_dir / media.path


def _signature(media_id: str, exp: int) -> str:
    secret = get_settings().media_secret
    if not secret:
        raise RuntimeError("media_secret is empty; media URLs cannot be signed")
    return hmac.new(secret.encode(), f"{media_id}:{exp}".encode(), hashlib.sha256).hexdigest()


def signed_url(media_id: str, ttl_s: int = 3600) -> str:
    exp = int(clock.now().timestamp()) + ttl_s
    return f"/api/v1/media/{media_id}?exp={exp}&sig={_signature(media_id, exp)}"


def verify_signature(media_id: str, exp: int, sig: str) -> bool:
    if not media_id or not sig or not get_settings().media_secret:
        return False
    if exp < clock.now().timestamp():
        return False
    return hmac.compare_digest(_signature(media_id, exp).encode(), sig.encode())
