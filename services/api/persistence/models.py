"""Every ORM table (plan Section 2: data model).

Status and kind columns are plain strings; the domain modules validate them. `Mapped[datetime]` is stored
as `UTCDateTime` and `Mapped[dict]`/`Mapped[list]` as mutation-tracked JSON through `Base.type_annotation_map`.
Inserts are not ordered by foreign key (there are no `relationship()`s): flush parents before children.
Money is integer minor units plus a currency code.
"""

from datetime import date, datetime

from sqlalchemy import ForeignKey, Index, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from domain import clock
from persistence.db import Base


def _farm_fk():
    return mapped_column(ForeignKey("farms.id"), index=True)


def _animal_fk(nullable: bool = False):
    return mapped_column(ForeignKey("animals.id"), index=True, nullable=nullable)


def _created_at():
    return mapped_column(default=clock.now)


def _updated_at():
    return mapped_column(default=clock.now, onupdate=clock.now)


class Farm(Base):
    __tablename__ = "farms"

    id: Mapped[str] = mapped_column(primary_key=True)
    name: Mapped[str]


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(primary_key=True)
    farm_id: Mapped[str] = _farm_fk()
    name: Mapped[str]
    role: Mapped[str]
    token: Mapped[str] = mapped_column(unique=True)


class Animal(Base):
    __tablename__ = "animals"

    id: Mapped[str] = mapped_column(primary_key=True)
    farm_id: Mapped[str] = _farm_fk()
    name: Mapped[str]
    breed: Mapped[str]
    breed_category: Mapped[str]
    sex: Mapped[str]
    birth_date: Mapped[date | None]
    identity_status: Mapped[str]
    confirmed_by: Mapped[str | None]
    confirmed_at: Mapped[datetime | None]
    ownership_doc_refs: Mapped[list] = mapped_column(default=list)
    enrollment_id: Mapped[str | None]
    created_at: Mapped[datetime] = _created_at()


class Media(Base):
    __tablename__ = "media"

    id: Mapped[str] = mapped_column(primary_key=True)
    farm_id: Mapped[str] = _farm_fk()
    kind: Mapped[str]
    path: Mapped[str]
    sha256: Mapped[str]
    content_type: Mapped[str]
    bytes: Mapped[int]
    created_at: Mapped[datetime] = _created_at()


class AnimalReference(Base):
    __tablename__ = "animal_references"

    id: Mapped[str] = mapped_column(primary_key=True)
    animal_id: Mapped[str] = _animal_fk()
    view: Mapped[str]
    media_id: Mapped[str | None] = mapped_column(ForeignKey("media.id"))
    crop_media_id: Mapped[str | None] = mapped_column(ForeignKey("media.id"))
    enrollment_id: Mapped[str | None] = mapped_column(ForeignKey("enrollments.id"))
    frame_time_s: Mapped[float | None]
    quality: Mapped[dict] = mapped_column(default=dict)
    created_at: Mapped[datetime] = _created_at()


class AnimalDocument(Base):
    """A file kept on the passport (ownership certificate, purchase receipt, vet record); the bytes are `media`."""

    __tablename__ = "animal_documents"

    id: Mapped[str] = mapped_column(primary_key=True)
    farm_id: Mapped[str] = _farm_fk()
    animal_id: Mapped[str] = _animal_fk()
    media_id: Mapped[str] = mapped_column(ForeignKey("media.id"))
    kind: Mapped[str]
    title: Mapped[str]
    filename: Mapped[str]
    uploaded_by: Mapped[str]
    created_at: Mapped[datetime] = _created_at()


class Enrollment(Base):
    __tablename__ = "enrollments"

    id: Mapped[str] = mapped_column(primary_key=True)
    farm_id: Mapped[str] = _farm_fk()
    status: Mapped[str]
    sample_key: Mapped[str | None]
    video_media_id: Mapped[str | None] = mapped_column(ForeignKey("media.id"))
    processing_mode: Mapped[str | None]
    manifest: Mapped[dict | None]
    identity: Mapped[dict | None]
    estimates: Mapped[dict | None]
    review_reasons: Mapped[list] = mapped_column(default=list)
    decision: Mapped[dict | None]
    reviewer_id: Mapped[str | None]
    animal_id: Mapped[str | None] = _animal_fk(nullable=True)
    retry_of_id: Mapped[str | None]
    created_by: Mapped[str]
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = _updated_at()


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (Index("ix_jobs_subject", "kind", "subject_id"),)

    id: Mapped[str] = mapped_column(primary_key=True)
    farm_id: Mapped[str] = _farm_fk()
    kind: Mapped[str]
    subject_id: Mapped[str]
    status: Mapped[str] = mapped_column(index=True)
    result: Mapped[dict | None]
    error: Mapped[dict | None]
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = _updated_at()


class Estimate(Base):
    __tablename__ = "estimates"

    id: Mapped[str] = mapped_column(primary_key=True)
    animal_id: Mapped[str] = _animal_fk()
    kind: Mapped[str]
    range_low: Mapped[float | None]
    range_high: Mapped[float | None]
    point: Mapped[float | None]
    unit: Mapped[str]
    source: Mapped[str]
    method_version: Mapped[str]
    evidence: Mapped[dict] = mapped_column(default=dict)
    review_required: Mapped[bool] = mapped_column(default=False)
    review_reason: Mapped[str | None]
    created_at: Mapped[datetime] = _created_at()


class Valuation(Base):
    __tablename__ = "valuations"
    __table_args__ = (UniqueConstraint("animal_id", "version"),)

    id: Mapped[str] = mapped_column(primary_key=True)
    animal_id: Mapped[str] = _animal_fk()
    version: Mapped[int]
    weight_low_kg: Mapped[float]
    weight_high_kg: Mapped[float]
    weight_basis: Mapped[str]
    estimate_id: Mapped[str | None] = mapped_column(ForeignKey("estimates.id"))
    unit_price_minor_per_kg: Mapped[int]
    currency: Mapped[str]
    price_source: Mapped[str]
    price_date: Mapped[date]
    value_low_minor: Mapped[int]
    value_high_minor: Mapped[int]
    confirmed_by: Mapped[str]
    created_at: Mapped[datetime] = _created_at()


class PolicyApplication(Base):
    __tablename__ = "policy_applications"

    id: Mapped[str] = mapped_column(primary_key=True)
    farm_id: Mapped[str] = _farm_fk()
    animal_id: Mapped[str] = _animal_fk()
    product_id: Mapped[str]
    provider_id: Mapped[str]
    terms_version: Mapped[str]
    insured_value_minor: Mapped[int]
    premium_minor: Mapped[int]
    deductible_minor: Mapped[int]
    currency: Mapped[str]
    coverage_start: Mapped[date]
    coverage_end: Mapped[date]
    status: Mapped[str]
    provider_ref: Mapped[str | None]
    created_at: Mapped[datetime] = _created_at()


class Policy(Base):
    __tablename__ = "policies"

    id: Mapped[str] = mapped_column(primary_key=True)
    farm_id: Mapped[str] = _farm_fk()
    animal_id: Mapped[str] = _animal_fk()
    application_id: Mapped[str | None] = mapped_column(ForeignKey("policy_applications.id"))
    product_id: Mapped[str]
    provider_id: Mapped[str]
    terms_version: Mapped[str]
    insured_value_minor: Mapped[int]
    premium_minor: Mapped[int]
    deductible_minor: Mapped[int]
    currency: Mapped[str]
    status: Mapped[str] = mapped_column(index=True)
    effective_date: Mapped[date | None]
    expiry_date: Mapped[date | None]
    activation_receipt: Mapped[dict | None]
    created_at: Mapped[datetime] = _created_at()


class EvidenceManifest(Base):
    __tablename__ = "evidence_manifests"
    __table_args__ = (UniqueConstraint("subject_type", "subject_id", "version"),)

    id: Mapped[str] = mapped_column(primary_key=True)
    farm_id: Mapped[str] = _farm_fk()
    subject_type: Mapped[str]
    subject_id: Mapped[str]
    version: Mapped[int]
    items: Mapped[list] = mapped_column(default=list)
    manifest_hash: Mapped[str]
    created_at: Mapped[datetime] = _created_at()


class AgentAction(Base):
    __tablename__ = "agent_actions"
    __table_args__ = (Index("ix_agent_actions_subject", "action_type", "subject_type", "subject_id"),)

    id: Mapped[str] = mapped_column(primary_key=True)
    farm_id: Mapped[str] = _farm_fk()
    action_type: Mapped[str]
    animal_id: Mapped[str | None] = _animal_fk(nullable=True)
    subject_type: Mapped[str | None]
    subject_id: Mapped[str | None]
    version: Mapped[int] = mapped_column(default=1)
    supersedes_id: Mapped[str | None]
    payload: Mapped[dict]
    payload_hash: Mapped[str]
    evidence_manifest_id: Mapped[str | None] = mapped_column(ForeignKey("evidence_manifests.id"))
    evidence_manifest_version: Mapped[int | None]
    status: Mapped[str] = mapped_column(index=True)
    rationale: Mapped[str | None]
    proposed_by_type: Mapped[str]
    proposed_by_id: Mapped[str]
    expires_at: Mapped[datetime]
    decided_by: Mapped[str | None]
    decided_at: Mapped[datetime | None]
    decision: Mapped[str | None]
    decision_note: Mapped[str | None]
    cancel_reason: Mapped[str | None]
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = _updated_at()


class ActionExecution(Base):
    __tablename__ = "action_executions"

    id: Mapped[str] = mapped_column(primary_key=True)
    action_id: Mapped[str] = mapped_column(ForeignKey("agent_actions.id"), unique=True)
    idempotency_key: Mapped[str] = mapped_column(unique=True)
    status: Mapped[str]
    provider_id: Mapped[str]
    provider_receipt: Mapped[dict | None]
    error: Mapped[dict | None]
    started_at: Mapped[datetime] = mapped_column(default=clock.now)
    completed_at: Mapped[datetime | None]


class WalletEntry(Base):
    __tablename__ = "wallet_entries"

    id: Mapped[str] = mapped_column(primary_key=True)
    farm_id: Mapped[str] = _farm_fk()
    entry_type: Mapped[str]
    amount_minor: Mapped[int]
    currency: Mapped[str]
    action_id: Mapped[str | None] = mapped_column(ForeignKey("agent_actions.id"), index=True)
    description: Mapped[str]
    created_at: Mapped[datetime] = _created_at()


class ProviderRecord(Base):
    __tablename__ = "provider_records"
    __table_args__ = (UniqueConstraint("provider", "operation", "idempotency_key"),)

    id: Mapped[str] = mapped_column(primary_key=True)
    provider: Mapped[str]
    operation: Mapped[str]
    idempotency_key: Mapped[str]
    request: Mapped[dict]
    response: Mapped[dict]
    created_at: Mapped[datetime] = _created_at()


class DemoSettings(Base):
    __tablename__ = "demo_settings"

    farm_id: Mapped[str] = mapped_column(ForeignKey("farms.id"), primary_key=True)
    payment_mode: Mapped[str] = mapped_column(default="succeed")
    insurer_activation: Mapped[str] = mapped_column(default="confirm")
    updated_at: Mapped[datetime] = _updated_at()


class Camera(Base):
    __tablename__ = "cameras"

    id: Mapped[str] = mapped_column(primary_key=True)
    farm_id: Mapped[str] = _farm_fk()
    name: Mapped[str]
    location: Mapped[str]
    map_x: Mapped[float]
    map_y: Mapped[float]


class CameraScanZone(Base):
    """A camera's calibrated scan zone: the floor area where one animal at a time is muzzle-scanned, so its identity
    can be handed to the one camera track inside it (domain/association.py). A separate table, so an existing
    database gains it on startup without a migration."""

    __tablename__ = "camera_scan_zones"

    camera_id: Mapped[str] = mapped_column(ForeignKey("cameras.id"), primary_key=True)
    polygon: Mapped[list]  # [[x, y], ...] normalized 0–1 to the camera frame, top-left origin
    label: Mapped[str]
    source: Mapped[str]
    calibrated_at: Mapped[datetime] = _created_at()


class Replay(Base):
    __tablename__ = "replays"

    id: Mapped[str] = mapped_column(primary_key=True)
    farm_id: Mapped[str] = _farm_fk()
    scenario_id: Mapped[str]
    camera_id: Mapped[str] = mapped_column(ForeignKey("cameras.id"))
    status: Mapped[str]
    speed: Mapped[float]
    started_at: Mapped[datetime] = mapped_column(default=clock.now)
    finished_at: Mapped[datetime | None]


class Track(Base):
    __tablename__ = "tracks"
    __table_args__ = (UniqueConstraint("replay_id", "camera_id", "track_key"),)

    id: Mapped[str] = mapped_column(primary_key=True)
    replay_id: Mapped[str | None] = mapped_column(ForeignKey("replays.id"), index=True)
    camera_id: Mapped[str] = mapped_column(ForeignKey("cameras.id"))
    track_key: Mapped[str]
    animal_id: Mapped[str | None] = _animal_fk(nullable=True)
    association_status: Mapped[str]
    association_method: Mapped[str | None]
    association_evidence: Mapped[dict | None]
    first_seen: Mapped[datetime]
    last_seen: Mapped[datetime]


class Observation(Base):
    __tablename__ = "observations"
    __table_args__ = (Index("ix_observations_animal_time", "animal_id", "observed_at"),)

    id: Mapped[str] = mapped_column(primary_key=True)
    farm_id: Mapped[str] = _farm_fk()
    camera_id: Mapped[str] = mapped_column(ForeignKey("cameras.id"))
    track_id: Mapped[str] = mapped_column(ForeignKey("tracks.id"), index=True)
    animal_id: Mapped[str | None] = mapped_column(ForeignKey("animals.id"))
    association_status: Mapped[str]
    observed_at: Mapped[datetime]
    bbox: Mapped[list]
    visibility: Mapped[float]
    event: Mapped[str]
    media_ref: Mapped[str | None]
    source: Mapped[str]


class Alert(Base):
    __tablename__ = "alerts"

    id: Mapped[str] = mapped_column(primary_key=True)
    farm_id: Mapped[str] = _farm_fk()
    kind: Mapped[str]
    animal_id: Mapped[str | None] = _animal_fk(nullable=True)
    track_id: Mapped[str | None] = mapped_column(ForeignKey("tracks.id"))
    camera_id: Mapped[str] = mapped_column(ForeignKey("cameras.id"))
    window_start: Mapped[datetime]
    window_end: Mapped[datetime]
    baseline_start: Mapped[datetime | None]
    baseline_end: Mapped[datetime | None]
    rule: Mapped[dict]
    clip: Mapped[dict | None]
    status: Mapped[str] = mapped_column(index=True)
    notes: Mapped[list] = mapped_column(default=list)
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = _updated_at()


class Incident(Base):
    __tablename__ = "incidents"

    id: Mapped[str] = mapped_column(primary_key=True)
    farm_id: Mapped[str] = _farm_fk()
    animal_id: Mapped[str] = _animal_fk()
    policy_id: Mapped[str | None] = mapped_column(ForeignKey("policies.id"))
    kind: Mapped[str]
    occurred_at: Mapped[datetime]
    description: Mapped[str]
    estimated_loss_minor: Mapped[int]
    currency: Mapped[str]
    reported_by: Mapped[str]
    facts: Mapped[dict] = mapped_column(default=dict)
    documents: Mapped[list] = mapped_column(default=list)
    professional_findings: Mapped[list] = mapped_column(default=list)
    linked_alert_ids: Mapped[list] = mapped_column(default=list)
    created_at: Mapped[datetime] = _created_at()


class Claim(Base):
    __tablename__ = "claims"

    id: Mapped[str] = mapped_column(primary_key=True)
    farm_id: Mapped[str] = _farm_fk()
    policy_id: Mapped[str] = mapped_column(ForeignKey("policies.id"))
    incident_id: Mapped[str] = mapped_column(ForeignKey("incidents.id"), index=True)
    animal_id: Mapped[str] = _animal_fk()
    status: Mapped[str]
    checklist: Mapped[list] = mapped_column(default=list)
    blocked_reason: Mapped[dict | None]
    declaration_confirmed: Mapped[bool] = mapped_column(default=False)
    declaration_by: Mapped[str | None]
    claimed_amount_minor: Mapped[int]
    currency: Mapped[str]
    evidence_manifest_id: Mapped[str | None] = mapped_column(ForeignKey("evidence_manifests.id"))
    receipt: Mapped[dict | None]
    assessment_status: Mapped[str | None]
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = _updated_at()


class AuditEvent(Base):
    __tablename__ = "audit_events"
    __table_args__ = (
        Index("ix_audit_events_farm_created", "farm_id", "created_at"),
        Index("ix_audit_events_animal_created", "animal_id", "created_at"),
        Index("ix_audit_events_subject", "subject_type", "subject_id"),
    )

    id: Mapped[str] = mapped_column(primary_key=True)
    farm_id: Mapped[str] = mapped_column(ForeignKey("farms.id"))
    actor_type: Mapped[str]
    actor_id: Mapped[str]
    event_type: Mapped[str]
    subject_type: Mapped[str]
    subject_id: Mapped[str]
    animal_id: Mapped[str | None]
    data: Mapped[dict] = mapped_column(default=dict)
    created_at: Mapped[datetime] = _created_at()


class IdentityCheck(Base):
    """A claim-time muzzle re-scan compared with the claimed animal's enrolled references (the anti-fraud step)."""

    __tablename__ = "identity_checks"
    __table_args__ = (Index("ix_identity_checks_claim_created", "claim_id", "created_at"),)

    id: Mapped[str] = mapped_column(primary_key=True)
    farm_id: Mapped[str] = _farm_fk()
    claim_id: Mapped[str] = mapped_column(ForeignKey("claims.id"))
    animal_id: Mapped[str] = _animal_fk()
    media_id: Mapped[str | None] = mapped_column(ForeignKey("media.id"))
    crop_media_id: Mapped[str | None] = mapped_column(ForeignKey("media.id"))
    reference_id: Mapped[str | None] = mapped_column(ForeignKey("animal_references.id"))
    outcome: Mapped[str]
    reason: Mapped[str | None]
    matched_animal_id: Mapped[str | None]
    candidates: Mapped[list] = mapped_column(default=list)
    inliers: Mapped[int | None]
    source: Mapped[str]
    method_version: Mapped[str]
    evidence: Mapped[dict] = mapped_column(default=dict)
    checked_by: Mapped[str]
    created_at: Mapped[datetime] = _created_at()


class CameraGallerySync(Base):
    """The muzzle gallery version a camera worker last acknowledged."""

    __tablename__ = "camera_gallery_syncs"

    camera_id: Mapped[str] = mapped_column(ForeignKey("cameras.id"), primary_key=True)
    farm_id: Mapped[str] = _farm_fk()
    synced_version: Mapped[int]
    synced_at: Mapped[datetime]
    source: Mapped[str]


class GalleryPublication(Base):
    """The gallery version a manager last pushed to the farm's cameras."""

    __tablename__ = "gallery_publications"

    farm_id: Mapped[str] = mapped_column(ForeignKey("farms.id"), primary_key=True)
    version: Mapped[int]
    published_by: Mapped[str]
    published_at: Mapped[datetime]
