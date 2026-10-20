"""Claims (plan Section 5: `/claims`). Managers and operators draft from an incident; only a manager confirms the
farmer declaration; any role of the farm (including the assessor) may read. Submission is a `CLAIM_SUBMISSION`
agent action.

`POST /claims/{id}/identity-checks` (managers and operators) takes either a multipart muzzle scan (`file`: a photo
or a short video) or JSON `{"sample": "match"|"mismatch"}` for the demo without a camera. The scan is spooled and
compared with no transaction open; one short writing session records the result (`domain.identity_check`).
"""

import hashlib
import shutil
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, Request
from starlette.datastructures import UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError
from sqlalchemy.orm import Session

from config import get_settings
from domain import claims, identity_check
from domain.auth import APPROVERS, ENROLLERS, Principal
from domain.errors import DomainError
from persistence.db import SessionLocal, get_read_session, get_session, read_session
from persistence.media import media_path, place_file
from routes.deps import current_principal, require_roles
from schemas import error_responses
from schemas_finance import (
    ClaimDetail, ClaimDraftRequest, ClaimList, ClaimPatch, IdentityCheckRequest, IdentityCheckResult,
)

router = APIRouter(prefix="/claims", tags=["claims"])


@router.post("/drafts", response_model=ClaimDetail, responses=error_responses(401, 403, 404, 409, 422))
def draft_claim(body: ClaimDraftRequest, principal: Principal = Depends(require_roles(*ENROLLERS)),
                session: Session = Depends(get_session)) -> dict:
    claim = claims.draft_claim(session, principal, body.incident_id)
    session.commit()
    return claims.claim_view(session, claim)


@router.get("", response_model=ClaimList, responses=error_responses(401))
def list_claims(animal_id: str | None = None, principal: Principal = Depends(current_principal),
                session: Session = Depends(get_read_session)) -> dict:
    return {"items": [claims.claim_view(session, c) for c in claims.list_claims(session, principal.farm_id, animal_id)]}


@router.get("/{claim_id}", response_model=ClaimDetail, responses=error_responses(401, 404))
def get_claim(claim_id: str, principal: Principal = Depends(current_principal),
              session: Session = Depends(get_read_session)) -> dict:
    return claims.claim_view(session, claims.farm_claim(session, principal.farm_id, claim_id))


@router.patch("/{claim_id}", response_model=ClaimDetail, responses=error_responses(401, 403, 404, 409, 422))
def patch_claim(claim_id: str, body: ClaimPatch, principal: Principal = Depends(require_roles(*APPROVERS)),
                session: Session = Depends(get_session)) -> dict:
    claim = claims.confirm_declaration(session, principal, claim_id)
    session.commit()
    return claims.claim_view(session, claim)


# Identity checks -----------------------------------------------------------------------------------------------

_CHUNK = 1 << 20
MULTIPART_OVERHEAD = 1 << 20  # boundaries and part headers on top of the file itself
_IDENTITY_BODY = {
    "required": True,
    "content": {
        "multipart/form-data": {"schema": {
            "type": "object", "required": ["file"],
            "properties": {"file": {"type": "string", "format": "binary",
                                    "description": "A muzzle photo (JPEG, PNG, WebP) or short video (MP4, WebM, "
                                                   "MOV)."}},
        }},
        "application/json": {"schema": IdentityCheckRequest.model_json_schema()},
    },
}


def _too_large() -> DomainError:
    return DomainError("VALIDATION_FAILED", "The scan is larger than 50 MB.",
                       {"max_bytes": identity_check.MAX_SCAN_BYTES})


def _spool(upload: UploadFile, ext: str) -> tuple[Path, str, int]:
    """Copy the scan to `<data_dir>/uploads/*.ext`, hashing as it goes (same volume as the media dir)."""
    upload_dir = get_settings().data_dir / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(dir=upload_dir, suffix=f".{ext}", delete=False)  # noqa: SIM115
    digest, size = hashlib.sha256(), 0
    try:
        with handle:
            while chunk := upload.file.read(_CHUNK):
                size += len(chunk)
                if size > identity_check.MAX_SCAN_BYTES:
                    raise _too_large()
                digest.update(chunk)
                handle.write(chunk)
        if size == 0:
            raise DomainError("VALIDATION_FAILED", "The uploaded scan is empty.", {"bytes": 0})
    except BaseException:
        Path(handle.name).unlink(missing_ok=True)
        raise
    return Path(handle.name), digest.hexdigest(), size


def _prepare(principal: Principal, claim_id: str) -> identity_check.Prepared:
    with read_session() as session:
        return identity_check.prepare(session, principal, claim_id)


def _outcome(principal: Principal, claim_id: str, check_id: str) -> dict:
    with read_session() as session:
        view = claims.claim_view(session, claims.farm_claim(session, principal.farm_id, claim_id))
    check = next(c for c in view["identity_checks"] if c["id"] == check_id)
    return {"check": check, "claim": view}


def _check_sample(principal: Principal, claim_id: str, sample: str) -> dict:
    prepared = _prepare(principal, claim_id)
    result = identity_check.simulated(prepared, sample)
    with SessionLocal() as session:
        check = identity_check.record(session, principal, prepared, result)
        session.commit()
    return _outcome(principal, claim_id, check.id)


def _check_upload(principal: Principal, claim_id: str, upload: UploadFile) -> dict:
    prepared = _prepare(principal, claim_id)
    kind, content_type, ext = identity_check.resolve_scan_type(upload.content_type, upload.filename)
    spooled, sha256, size = _spool(upload, ext)
    work_root = get_settings().data_dir / "work"
    work_root.mkdir(parents=True, exist_ok=True)
    work_dir = Path(tempfile.mkdtemp(prefix="idcheck-", dir=work_root))
    try:
        # The matcher runs before any writing transaction opens (persistence.db session rules).
        result = identity_check.run(prepared, spooled, kind, work_dir)
        media = place_file(principal.farm_id, "frame" if kind == "photo" else "video", spooled, content_type,
                           sha256, size)
        stored = [media_path(media)]
        try:
            with SessionLocal() as session:
                check = identity_check.record(session, principal, prepared, result, scan_media=media, stored=stored)
                session.commit()
        except BaseException:
            for path in stored:
                path.unlink(missing_ok=True)
            raise
    finally:
        spooled.unlink(missing_ok=True)
        shutil.rmtree(work_dir, ignore_errors=True)
    return _outcome(principal, claim_id, check.id)


@router.post("/{claim_id}/identity-checks", status_code=201, response_model=IdentityCheckResult,
             responses=error_responses(401, 403, 404, 409, 422), openapi_extra={"requestBody": _IDENTITY_BODY})
async def check_identity(claim_id: str, request: Request,
                         principal: Principal = Depends(require_roles(*ENROLLERS))) -> dict:
    """Compare a muzzle re-scan of the claimed animal with its enrolled references; a death claim needs a match."""
    content_type = request.headers.get("content-type", "").split(";")[0].strip().lower()
    if content_type == "multipart/form-data":
        length = request.headers.get("content-length", "")
        if length.isdigit() and int(length) > identity_check.MAX_SCAN_BYTES + MULTIPART_OVERHEAD:
            raise _too_large()
        form = await request.form(max_files=1, max_fields=4)
        try:
            upload = form.get("file")
            if not isinstance(upload, UploadFile):
                raise DomainError("VALIDATION_FAILED", "Attach the muzzle scan as the `file` field.",
                                  {"field": "file"})
            return await run_in_threadpool(_check_upload, principal, claim_id, upload)
        finally:
            await form.close()
    if content_type == "application/json":
        try:
            body = IdentityCheckRequest.model_validate_json(await request.body())
        except ValidationError as error:
            raise RequestValidationError(error.errors(include_url=False)) from None
        return await run_in_threadpool(_check_sample, principal, claim_id, body.sample)
    raise DomainError("VALIDATION_FAILED", "Send a multipart muzzle scan or a JSON sample.",
                      {"content_type": content_type or None,
                       "allowed": ["multipart/form-data", "application/json"]})
