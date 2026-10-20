"""Local media storage behind signed URLs (plan Section 1: media on disk, served by signature).

Files live at `<media_dir>/<farm_id>/<media_id>.<ext>`; the row stores that path relative to `media_dir`,
plus the SHA-256 that evidence manifests cite. A URL carries `exp` and `sig = HMAC-SHA256(secret, "id:exp")`,
and the signature is the only credential, so `GET /media/{id}` needs no bearer token.
"""

import hashlib
import hmac
import shutil
from pathlib import Path

from sqlalchemy.orm import Session

from config import get_settings
from domain import clock
from domain.ids import new_id
from persistence.models import Media

MEDIA_KINDS = ("video", "frame", "crop", "clip", "document")
_CHUNK = 1 << 20


def _new_media(farm_id: str, kind: str, ext: str) -> tuple[str, str, Path]:
    if kind not in MEDIA_KINDS:
        raise ValueError(f"unknown media kind {kind!r}")
    media_id = new_id("media")
    relative = f"{farm_id}/{media_id}.{ext.lstrip('.').lower()}"
    target = get_settings().media_dir / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    return media_id, relative, target


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(_CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


def store_bytes(session: Session, farm_id: str, kind: str, data: bytes, content_type: str, ext: str) -> Media:
    media_id, relative, target = _new_media(farm_id, kind, ext)
    target.write_bytes(data)
    media = Media(id=media_id, farm_id=farm_id, kind=kind, path=relative, sha256=hashlib.sha256(data).hexdigest(),
                  content_type=content_type, bytes=len(data))
    session.add(media)
    session.flush()
    return media


def store_file(session: Session, farm_id: str, kind: str, src_path: Path, content_type: str) -> Media:
    src_path = Path(src_path)
    media_id, relative, target = _new_media(farm_id, kind, src_path.suffix or "bin")
    shutil.copyfile(src_path, target)
    media = Media(id=media_id, farm_id=farm_id, kind=kind, path=relative, sha256=_file_sha256(target),
                  content_type=content_type, bytes=target.stat().st_size)
    session.add(media)
    session.flush()
    return media


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
