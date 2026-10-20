"""Evidence manifests (plan Section 4: a matching evidence manifest version is created or reused).

A manifest lists the records an agent action relies on: `{type, ref, label, sha256?}` items, hashed as canonical
JSON. Each subject keeps its own version sequence. Proposing reuses the latest version when the hash is
unchanged, else writes version + 1. `resolve_version` computes the same number without writing, which is how an
execution detects that the evidence changed since approval (for example a new valuation).
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from domain.canonical import sha256_hex
from domain.eligibility import latest_estimate
from domain.ids import new_id
from domain.passbook import product_name
from domain.valuation import latest_valuation, money
from persistence.models import (
    Alert, Animal, AnimalReference, Camera, EvidenceManifest, Incident, Media, Policy, PolicyApplication,
)


def item(type_: str, ref: str, label: str, sha256: str | None = None) -> dict:
    entry = {"type": type_, "ref": ref, "label": label}
    if sha256:
        entry["sha256"] = sha256
    return entry


def manifest_hash(items: list[dict]) -> str:
    return sha256_hex(items)


def latest(session: Session, farm_id: str, subject_type: str, subject_id: str) -> EvidenceManifest | None:
    return session.scalar(select(EvidenceManifest).where(
        EvidenceManifest.farm_id == farm_id, EvidenceManifest.subject_type == subject_type,
        EvidenceManifest.subject_id == subject_id).order_by(EvidenceManifest.version.desc()).limit(1))


def resolve_version(session: Session, farm_id: str, subject: tuple[str, str], items: list[dict]) -> int:
    current = latest(session, farm_id, *subject)
    if current is not None and current.manifest_hash == manifest_hash(items):
        return current.version
    return (current.version if current else 0) + 1


def ensure(session: Session, farm_id: str, subject: tuple[str, str], items: list[dict]) -> EvidenceManifest:
    current = latest(session, farm_id, *subject)
    digest = manifest_hash(items)
    if current is not None and current.manifest_hash == digest:
        return current
    manifest = EvidenceManifest(id=new_id("man"), farm_id=farm_id, subject_type=subject[0], subject_id=subject[1],
                                version=(current.version if current else 0) + 1, items=list(items),
                                manifest_hash=digest)
    session.add(manifest)
    session.flush()
    return manifest


def _media_sha(session: Session, media_id: str | None) -> str | None:
    media = session.get(Media, media_id) if media_id else None
    return media.sha256 if media else None


def _num(value) -> str:
    """A range bound without a trailing `.0` (480, not 480.0)."""
    return f"{value:g}" if isinstance(value, float) else str(value)


def identity_items(session: Session, animal: Animal) -> list[dict]:
    references = session.scalars(select(AnimalReference).where(AnimalReference.animal_id == animal.id)
                                 .order_by(AnimalReference.view, AnimalReference.id)).all()
    return [item("identity_reference", ref.id, f"Passport {ref.view} reference",
                 _media_sha(session, ref.crop_media_id or ref.media_id)) for ref in references]


def animal_items(session: Session, animal: Animal) -> list[dict]:
    """Passport identity references, the latest estimates and valuation, and ownership documents."""
    items = identity_items(session, animal)
    for kind in ("weight", "age"):
        estimate = latest_estimate(session, animal.id, kind)
        if estimate is not None:
            items.append(item(f"{kind}_estimate", estimate.id,
                              f"{kind.title()} estimate {_num(estimate.range_low)}–{_num(estimate.range_high)} {estimate.unit} "
                              f"({estimate.source})"))
    valuation = latest_valuation(session, animal.id)
    if valuation is not None:
        items.append(item("valuation", valuation.id,
                          f"Valuation v{valuation.version} · {money(valuation.value_low_minor)}–"
                          f"{money(valuation.value_high_minor)} {valuation.currency}"))
    items += ownership_items(animal)
    return items


def ownership_items(animal: Animal) -> list[dict]:
    return [item("ownership_document", ref, "Ownership document") for ref in animal.ownership_doc_refs or []]


def application_items(application: PolicyApplication, policy: Policy) -> list[dict]:
    return [item("policy_application", application.id, f"Accepted application {application.provider_ref or ''}".strip()),
            item("policy", policy.id, f"{policy_item(policy)['label']}, {policy.status.replace('_', ' ')}")]


def policy_item(policy: Policy) -> dict:
    return item("policy", policy.id, f"Policy {product_name(policy.product_id)} ({policy.terms_version})")


def alert_items(session: Session, alert: Alert) -> list[dict]:
    camera = session.get(Camera, alert.camera_id) if alert.camera_id else None
    kind = alert.kind.replace("_", " ").capitalize()
    items = [item("alert", alert.id, f"{kind} alert on {camera.name if camera else alert.camera_id}")]
    clip = alert.clip or {}
    if clip.get("media_id"):
        items.append(item("clip", clip["media_id"], "Alert clip", _media_sha(session, clip["media_id"])))
    elif clip:  # a replay window: {scenario_id, camera_id, start_s, end_s, video}
        ref = f"{clip.get('scenario_id')}:{clip.get('camera_id')}:{clip.get('start_s')}-{clip.get('end_s')}"
        items.append(item("clip", ref, f"Replay clip {clip.get('start_s')}–{clip.get('end_s')} s"))
    return items


_FINDING_WORDS = {"vet_assessment": "Vet assessment", "vet_health_record": "Vet health record"}


def incident_items(incident: Incident) -> list[dict]:
    items = [item("incident", incident.id, f"Incident: {incident.kind.replace('_', ' ')}")]
    for document in incident.documents or []:
        ref = document.get("media_id") or document.get("ref") if isinstance(document, dict) else str(document)
        if ref:
            items.append(item("incident_document", ref, "Incident document",
                              document.get("sha256") if isinstance(document, dict) else None))
    for finding in incident.professional_findings or []:
        items.append(item("professional_finding", finding["id"], f"{_FINDING_WORDS.get(finding['finding_type'], finding['finding_type'])} by {finding['author_name']}"))
    return items
