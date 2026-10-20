"""Passport documents (PRD: ownership-document references; plan Section 5: `/animals/{id}/documents`).

A document is a PDF, JPEG, or PNG kept on the animal's passport, stored as `document` media (downloaded as an
attachment, never rendered in the app's origin). Its declared type must match the file's leading bytes. Adding an
`ownership` document also adds its id to `animal.ownership_doc_refs`, which is the fact the eligibility rule
`ownership_document` reads, and records `animal.document_added` in the same transaction.

The route spools and places the file before any writing transaction opens (persistence.db session rules); `add`
then only inserts the rows.
"""

from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from domain import audit, clock
from domain.auth import Principal
from domain.errors import DomainError
from domain.ids import new_id
from domain.passbook import PassbookContext, register_formatter
from persistence.media import signed_url
from persistence.models import Animal, AnimalDocument, AuditEvent, Media, User

DOCUMENT_KINDS = ("ownership", "purchase_receipt", "vet_record", "other")
KIND_LABELS = {"ownership": "Ownership", "purchase_receipt": "Purchase receipt", "vet_record": "Vet record",
               "other": "Other document"}
MAX_DOCUMENT_BYTES = 10 * 1024 * 1024
MAX_TITLE_CHARS = 120
EXT_BY_TYPE = {"application/pdf": "pdf", "image/jpeg": "jpg", "image/png": "png"}
TYPE_BY_EXT = {"pdf": "application/pdf", "jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png"}
_MAGIC = {"application/pdf": (b"%PDF-",), "image/jpeg": (b"\xff\xd8\xff",), "image/png": (b"\x89PNG\r\n\x1a\n",)}


def farm_animal(session: Session, farm_id: str, animal_id: str) -> Animal:
    animal = session.get(Animal, animal_id)
    if animal is None or animal.farm_id != farm_id:
        raise DomainError("NOT_FOUND", "Animal not found.", {"animal_id": animal_id})
    return animal


def check_kind(kind: str) -> str:
    if kind not in DOCUMENT_KINDS:
        raise DomainError("VALIDATION_FAILED", "Choose a document kind.", {"kind": kind, "allowed": list(DOCUMENT_KINDS)})
    return kind


def clean_title(title: str | None, kind: str, filename: str | None) -> str:
    text = " ".join((title or "").split())
    if len(text) > MAX_TITLE_CHARS:
        raise DomainError("VALIDATION_FAILED", f"The title is longer than {MAX_TITLE_CHARS} characters.",
                          {"max_chars": MAX_TITLE_CHARS})
    return text or Path(filename or "").stem.strip() or KIND_LABELS[kind]


def resolve_type(declared: str | None, filename: str | None) -> tuple[str, str]:
    """(content type, extension) from an allowed declared type, or from the file extension when none is declared."""
    content_type = (declared or "").split(";")[0].strip().lower()
    if content_type in ("", "application/octet-stream"):
        content_type = TYPE_BY_EXT.get(Path(filename or "").suffix.lstrip(".").lower(), content_type)
    if content_type not in EXT_BY_TYPE:
        raise DomainError("VALIDATION_FAILED", "A document must be a PDF, JPEG, or PNG file.",
                          {"content_type": content_type or None, "filename": filename, "allowed": sorted(EXT_BY_TYPE)})
    return content_type, EXT_BY_TYPE[content_type]


def check_magic(path: Path, content_type: str) -> None:
    """Refuse a file whose leading bytes are not the declared type (a renamed executable is not a PDF)."""
    with path.open("rb") as handle:
        head = handle.read(16)
    if not any(head.startswith(magic) for magic in _MAGIC[content_type]):
        raise DomainError("VALIDATION_FAILED", "The file's contents don't match its type.",
                          {"content_type": content_type})


def add(session: Session, principal: Principal, animal_id: str, media: Media, *, kind: str, title: str,
        filename: str) -> AnimalDocument:
    """Insert the media row, the document, the ownership reference, and the audit event. The caller commits."""
    animal = farm_animal(session, principal.farm_id, animal_id)
    session.add(media)
    session.flush()
    document = AnimalDocument(id=new_id("doc"), farm_id=principal.farm_id, animal_id=animal.id, media_id=media.id,
                              kind=kind, title=title, filename=Path(filename or "").name[:200] or media.path,
                              uploaded_by=principal.user_id, created_at=clock.now())
    session.add(document)
    if kind == "ownership":
        animal.ownership_doc_refs = [*(animal.ownership_doc_refs or []), document.id]
    actor_type, actor_id = audit.actor_from(principal)
    audit.record(session, farm_id=principal.farm_id, actor_type=actor_type, actor_id=actor_id,
                 event_type="animal.document_added", subject_type="animal_document", subject_id=document.id,
                 animal_id=animal.id, data={"kind": kind, "title": title, "media_id": media.id,
                                            "sha256": media.sha256, "bytes": media.bytes,
                                            "content_type": media.content_type})
    session.flush()
    return document


def list_documents(session: Session, farm_id: str, animal_id: str) -> list[dict]:
    farm_animal(session, farm_id, animal_id)
    rows = session.execute(select(AnimalDocument, Media).join(Media, Media.id == AnimalDocument.media_id)
                           .where(AnimalDocument.farm_id == farm_id, AnimalDocument.animal_id == animal_id)
                           .order_by(AnimalDocument.created_at.desc(), AnimalDocument.id)).all()
    names = audit.user_names(session, farm_id)
    return [view(document, media, names) for document, media in rows]


def view(document: AnimalDocument, media: Media, names: dict[str, str]) -> dict:
    return {"id": document.id, "animal_id": document.animal_id, "kind": document.kind, "title": document.title,
            "filename": document.filename, "content_type": media.content_type, "bytes": media.bytes,
            "sha256": media.sha256, "url": signed_url(media.id), "uploaded_by": names.get(document.uploaded_by,
                                                                                            document.uploaded_by),
            "created_at": document.created_at}


def document_view(session: Session, document: AnimalDocument) -> dict:
    media = session.get(Media, document.media_id)
    names = dict(session.execute(select(User.id, User.name).where(User.id == document.uploaded_by)).all())
    return view(document, media, names)


@register_formatter("animal.document_added")
def _document_added(event: AuditEvent, ctx: PassbookContext) -> dict:
    kind = event.data.get("kind")
    return {"title": f"Document on file · {KIND_LABELS.get(kind, 'Document')}", "detail": event.data.get("title")}
