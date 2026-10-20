"""Signed media download (plan Section 5: `GET /media/{id}?exp&sig`).

The signature is the credential. Every failure (bad or expired signature, unknown id, missing file) is the
same `NOT_FOUND`, so a caller cannot probe which media ids exist. Responses are never content-sniffed, and
documents download as attachments instead of rendering in the app's origin.
"""

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from domain.errors import DomainError
from persistence.db import get_session
from persistence.media import media_path, verify_signature
from persistence.models import Media

router = APIRouter(tags=["media"])


def _not_found() -> DomainError:
    return DomainError("NOT_FOUND", "Media not found or link expired.")


@router.get("/media/{media_id}", response_class=FileResponse)
def get_media(media_id: str, exp: str = "", sig: str = "", session: Session = Depends(get_session)) -> FileResponse:
    try:
        expires = int(exp)
    except ValueError:
        raise _not_found() from None
    if not verify_signature(media_id, expires, sig):
        raise _not_found()
    media = session.get(Media, media_id)
    if media is None or not media_path(media).is_file():
        raise _not_found()
    path = media_path(media)
    headers = {"X-Content-Type-Options": "nosniff"}
    if media.kind == "document":
        return FileResponse(path, media_type=media.content_type, headers=headers, filename=path.name,
                            content_disposition_type="attachment")
    return FileResponse(path, media_type=media.content_type, headers=headers)
