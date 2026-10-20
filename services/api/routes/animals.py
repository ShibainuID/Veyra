"""Herd list, Digital Livestock Passport, and passport documents (plan Section 5: `/animals`,
`/animals/{id}/passport`, `/animals/{id}/documents`). Any role may read; managers and operators add documents;
every query is scoped to the principal's farm."""

import hashlib
import tempfile
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy.orm import Session

from config import get_settings
from domain import documents, passport
from domain.auth import ENROLLERS, Principal
from domain.errors import DomainError
from persistence.db import SessionLocal, get_read_session, read_session
from persistence.media import media_path, place_file
from routes.deps import current_principal, require_roles
from schemas import AnimalDocumentList, AnimalDocumentOut, AnimalList, DocumentKind, Passport, error_responses

router = APIRouter(prefix="/animals", tags=["animals"])
_CHUNK = 1 << 20


@router.get("", response_model=AnimalList, responses=error_responses(401, 422))
def list_animals(coverage: Literal["none", "active", "pending"] | None = None, alerts: Literal["open"] | None = None,
                 q: str | None = None, principal: Principal = Depends(current_principal),
                 session: Session = Depends(get_read_session)) -> dict:
    return passport.list_herd(session, principal.farm_id, coverage=coverage, alerts=alerts, q=q)


@router.get("/{animal_id}/passport", response_model=Passport, responses=error_responses(401, 404))
def get_passport(animal_id: str, principal: Principal = Depends(current_principal),
                 session: Session = Depends(get_read_session)) -> dict:
    return passport.build_passport(session, principal.farm_id, animal_id)


@router.get("/{animal_id}/documents", response_model=AnimalDocumentList, responses=error_responses(401, 404))
def list_documents(animal_id: str, principal: Principal = Depends(current_principal),
                   session: Session = Depends(get_read_session)) -> dict:
    return {"items": documents.list_documents(session, principal.farm_id, animal_id)}


def _spool(upload: UploadFile, ext: str) -> tuple[Path, str, int]:
    """Copy the upload to `<data_dir>/uploads/*.ext` (same volume as the media dir), hashing and capping it."""
    upload_dir = get_settings().data_dir / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(dir=upload_dir, suffix=f".{ext}", delete=False)  # noqa: SIM115
    digest, size = hashlib.sha256(), 0
    try:
        with handle:
            while chunk := upload.file.read(_CHUNK):
                size += len(chunk)
                if size > documents.MAX_DOCUMENT_BYTES:
                    raise DomainError("VALIDATION_FAILED", "The document is larger than 10 MB.",
                                      {"max_bytes": documents.MAX_DOCUMENT_BYTES})
                digest.update(chunk)
                handle.write(chunk)
        if size == 0:
            raise DomainError("VALIDATION_FAILED", "The uploaded document is empty.", {"bytes": 0})
    except BaseException:
        Path(handle.name).unlink(missing_ok=True)
        raise
    return Path(handle.name), digest.hexdigest(), size


@router.post("/{animal_id}/documents", response_model=AnimalDocumentOut, status_code=201,
             responses=error_responses(401, 403, 404, 422))
def add_document(animal_id: str, file: UploadFile = File(..., description="A PDF, JPEG, or PNG, up to 10 MB."),
                 kind: DocumentKind = Form(...), title: str | None = Form(None),
                 principal: Principal = Depends(require_roles(*ENROLLERS))) -> dict:
    """Keep a document on the passport. An `ownership` document also becomes the animal's ownership reference,
    which the Mortality + Theft eligibility rule reads."""
    documents.check_kind(kind)
    with read_session() as session:
        documents.farm_animal(session, principal.farm_id, animal_id)
    clean_title = documents.clean_title(title, kind, file.filename)
    content_type, ext = documents.resolve_type(file.content_type, file.filename)
    spooled, sha256, size = _spool(file, ext)
    # Check and move the file before the writing transaction, so only the row inserts hold the write lock.
    try:
        documents.check_magic(spooled, content_type)
        media = place_file(principal.farm_id, "document", spooled, content_type, sha256, size)
    finally:
        spooled.unlink(missing_ok=True)
    try:
        with SessionLocal() as session:
            document = documents.add(session, principal, animal_id, media, kind=kind, title=clean_title,
                                     filename=file.filename or "")
            session.commit()
    except BaseException:
        media_path(media).unlink(missing_ok=True)
        raise
    with read_session() as session:
        return documents.document_view(session, document)
