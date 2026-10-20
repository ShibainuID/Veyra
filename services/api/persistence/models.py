"""Core records from PRD Section 4.4, as PostgreSQL tables.

Conventions: UUID primary keys, timezone-aware UTC timestamps, explicit units in column names,
integer minor units plus an ISO currency code for money, JSONB for adapter outputs and manifests,
and status columns guarded by CHECK constraints. Every farm-owned row carries `farm_id` so access
can be scoped on the server.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


def utcnow() -> datetime:
    return datetime.now(UTC)


def _id() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


def _fk(table: str, nullable: bool = False, index: bool = True) -> Mapped:
    return mapped_column(UUID(as_uuid=True), ForeignKey(f"{table}.id"), nullable=nullable, index=index)


def _created() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


def _status_check(column: str, values: tuple[str, ...], name: str) -> CheckConstraint:
    quoted = ", ".join(f"'{v}'" for v in values)
    return CheckConstraint(f"{column} IN ({quoted})", name=name)


ROLES = ("manager", "operator", "veterinarian", "assessor")
SOURCES = ("live", "prototype", "simulated", "documented", "measured", "manual")


class Farm(Base):
    __tablename__ = "farms"
    id: Mapped[uuid.UUID] = _id()
    name: Mapped[str] = mapped_column(String(200))
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    created_at: Mapped[datetime] = _created()


class User(Base):
    __tablename__ = "users"
    __table_args__ = (_status_check("role", ROLES, "ck_users_role"),)
    id: Mapped[uuid.UUID] = _id()
    farm_id: Mapped[uuid.UUID] = _fk("farms")
    name: Mapped[str] = mapped_column(String(200))
    role: Mapped[str] = mapped_column(String(20))
    # SHA-256 of an opaque API token; the token itself is never stored.
    token_sha256: Mapped[str] = mapped_column(String(64), unique=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = _created()


class Media(Base):
    __tablename__ = "media"
    __table_args__ = (_status_check("kind", ("video", "image", "document", "clip"), "ck_media_kind"),)
    id: Mapped[uuid.UUID] = _id()
    farm_id: Mapped[uuid.UUID] = _fk("farms")
    kind: Mapped[str] = mapped_column(String(20))
    storage_key: Mapped[str] = mapped_column(String(500), unique=True)
    original_filename: Mapped[str | None] = mapped_column(String(300))
    content_type: Mapped[str | None] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    uploaded_by: Mapped[uuid.UUID] = _fk("users")
    created_at: Mapped[datetime] = _created()


class Animal(Base):
    """The persistent passport anchor. A visual track ID is never an animal ID."""

    __tablename__ = "animals"
    __table_args__ = (
        _status_check("identity_status", ("pending_review", "confirmed", "disputed"), "ck_animals_identity_status"),
        UniqueConstraint("farm_id", "display_id", name="uq_animals_farm_display_id"),
    )
    id: Mapped[uuid.UUID] = _id()
    farm_id: Mapped[uuid.UUID] = _fk("farms")
    display_id: Mapped[str] = mapped_column(String(50))
    identity_status: Mapped[str] = mapped_column(String(20), default="pending_review")
    confirmed_by: Mapped[uuid.UUID | None] = _fk("users", nullable=True, index=False)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sex: Mapped[str | None] = mapped_column(String(10))
    breed: Mapped[str | None] = mapped_column(String(100))
    ownership_document_ids: Mapped[list] = mapped_column(JSONB, default=list)
    created_at: Mapped[datetime] = _created()


class MuzzleReference(Base):
    """Gallery entry used by the muzzle adapter: embedding plus SIFT features of one reference crop."""

    __tablename__ = "muzzle_references"
    id: Mapped[uuid.UUID] = _id()
    farm_id: Mapped[uuid.UUID] = _fk("farms")
    animal_id: Mapped[uuid.UUID] = _fk("animals")
    media_id: Mapped[uuid.UUID] = _fk("media")
    model_version: Mapped[str] = mapped_column(String(50))
    embedding: Mapped[list] = mapped_column(JSONB)
    sift_storage_key: Mapped[str] = mapped_column(String(500))
    created_at: Mapped[datetime] = _created()


class Enrollment(Base):
    __tablename__ = "enrollments"
    __table_args__ = (
        _status_check("status", ("created", "uploaded", "processing", "needs_review", "ready", "confirmed", "rejected", "failed"),
                      "ck_enrollments_status"),
    )
    id: Mapped[uuid.UUID] = _id()
    farm_id: Mapped[uuid.UUID] = _fk("farms")
    status: Mapped[str] = mapped_column(String(20), default="created")
    video_media_id: Mapped[uuid.UUID | None] = _fk("media", nullable=True)
    processing_mode: Mapped[str | None] = mapped_column(String(20))
    manifest: Mapped[dict | None] = mapped_column(JSONB)
    identity_result: Mapped[dict | None] = mapped_column(JSONB)
    review_reasons: Mapped[list] = mapped_column(JSONB, default=list)
    animal_id: Mapped[uuid.UUID | None] = _fk("animals", nullable=True)
    created_by: Mapped[uuid.UUID] = _fk("users", index=False)
    reviewed_by: Mapped[uuid.UUID | None] = _fk("users", nullable=True, index=False)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = _created()


class Estimate(Base):
    """Age or weight estimate with provenance; original estimates and confirmed overrides are separate rows."""

    __tablename__ = "estimates"
    __table_args__ = (
        _status_check("kind", ("age", "weight"), "ck_estimates_kind"),
        _status_check("source", SOURCES, "ck_estimates_source"),
    )
    id: Mapped[uuid.UUID] = _id()
    farm_id: Mapped[uuid.UUID] = _fk("farms")
    animal_id: Mapped[uuid.UUID] = _fk("animals")
    enrollment_id: Mapped[uuid.UUID | None] = _fk("enrollments", nullable=True)
    kind: Mapped[str] = mapped_column(String(10))
    range_low: Mapped[float | None] = mapped_column(Numeric(10, 2))
    range_high: Mapped[float | None] = mapped_column(Numeric(10, 2))
    unit: Mapped[str] = mapped_column(String(10))
    source: Mapped[str] = mapped_column(String(20))
    method_version: Mapped[str] = mapped_column(String(50))
    details: Mapped[dict] = mapped_column(JSONB, default=dict)
    review_required: Mapped[bool] = mapped_column(Boolean, default=False)
    supersedes_id: Mapped[uuid.UUID | None] = _fk("estimates", nullable=True, index=False)
    confirmed_by: Mapped[uuid.UUID | None] = _fk("users", nullable=True, index=False)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = _created()


class Valuation(Base):
    __tablename__ = "valuations"
    id: Mapped[uuid.UUID] = _id()
    farm_id: Mapped[uuid.UUID] = _fk("farms")
    animal_id: Mapped[uuid.UUID] = _fk("animals")
    weight_estimate_id: Mapped[uuid.UUID] = _fk("estimates", index=False)
    currency: Mapped[str] = mapped_column(String(3))
    unit_price_minor_per_kg: Mapped[int] = mapped_column(BigInteger)
    price_source: Mapped[str] = mapped_column(String(200))
    price_date: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    value_low_minor: Mapped[int] = mapped_column(BigInteger)
    value_high_minor: Mapped[int] = mapped_column(BigInteger)
    confirmed_by: Mapped[uuid.UUID | None] = _fk("users", nullable=True, index=False)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = _created()


class Camera(Base):
    __tablename__ = "cameras"
    id: Mapped[uuid.UUID] = _id()
    farm_id: Mapped[uuid.UUID] = _fk("farms")
    name: Mapped[str] = mapped_column(String(100))
    location: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = _created()


class Observation(Base):
    __tablename__ = "observations"
    __table_args__ = (
        _status_check("association_status", ("unassociated", "candidate", "confirmed", "uncertain"),
                      "ck_observations_association"),
        Index("ix_observations_animal_time", "animal_id", "observed_at"),
    )
    id: Mapped[uuid.UUID] = _id()
    farm_id: Mapped[uuid.UUID] = _fk("farms")
    camera_id: Mapped[uuid.UUID] = _fk("cameras")
    track_id: Mapped[str] = mapped_column(String(100))
    animal_id: Mapped[uuid.UUID | None] = _fk("animals", nullable=True, index=False)
    association_status: Mapped[str] = mapped_column(String(20), default="unassociated")
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    window_seconds: Mapped[float] = mapped_column(Numeric(8, 2))
    movement_score: Mapped[float | None] = mapped_column(Numeric(10, 4))
    quality: Mapped[dict] = mapped_column(JSONB, default=dict)
    media_id: Mapped[uuid.UUID | None] = _fk("media", nullable=True, index=False)
    source: Mapped[str] = mapped_column(String(20))
    created_at: Mapped[datetime] = _created()


class Alert(Base):
    __tablename__ = "alerts"
    __table_args__ = (
        _status_check("kind", ("reduced_movement", "observation_quality"), "ck_alerts_kind"),
        _status_check("status", ("open", "acknowledged", "resolved"), "ck_alerts_status"),
    )
    id: Mapped[uuid.UUID] = _id()
    farm_id: Mapped[uuid.UUID] = _fk("farms")
    animal_id: Mapped[uuid.UUID | None] = _fk("animals", nullable=True)
    track_id: Mapped[str | None] = mapped_column(String(100))
    kind: Mapped[str] = mapped_column(String(30))
    rule: Mapped[dict] = mapped_column(JSONB)
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    window_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    evidence_media_ids: Mapped[list] = mapped_column(JSONB, default=list)
    status: Mapped[str] = mapped_column(String(20), default="open")
    review_notes: Mapped[str | None] = mapped_column(Text)
    reviewed_by: Mapped[uuid.UUID | None] = _fk("users", nullable=True, index=False)
    created_at: Mapped[datetime] = _created()


class PolicyProduct(Base):
    """A fictional catalog entry. Terms are versioned and immutable once published."""

    __tablename__ = "policy_products"
    __table_args__ = (UniqueConstraint("code", "terms_version", name="uq_policy_products_code_version"),)
    id: Mapped[uuid.UUID] = _id()
    provider_id: Mapped[str] = mapped_column(String(100))
    code: Mapped[str] = mapped_column(String(50))
    terms_version: Mapped[str] = mapped_column(String(20))
    terms: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[datetime] = _created()


class Policy(Base):
    __tablename__ = "policies"
    __table_args__ = (
        _status_check("status", ("draft", "applied", "payment_pending", "paid", "active", "rejected", "expired", "cancelled"),
                      "ck_policies_status"),
    )
    id: Mapped[uuid.UUID] = _id()
    farm_id: Mapped[uuid.UUID] = _fk("farms")
    animal_id: Mapped[uuid.UUID] = _fk("animals")
    product_id: Mapped[uuid.UUID] = _fk("policy_products", index=False)
    status: Mapped[str] = mapped_column(String(20), default="draft")
    eligibility_inputs: Mapped[dict] = mapped_column(JSONB, default=dict)
    currency: Mapped[str] = mapped_column(String(3))
    insured_value_minor: Mapped[int] = mapped_column(BigInteger)
    premium_minor: Mapped[int] = mapped_column(BigInteger)
    deductible_minor: Mapped[int] = mapped_column(BigInteger)
    coverage_limit_minor: Mapped[int] = mapped_column(BigInteger)
    effective_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    effective_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    provider_reference: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = _created()


class Incident(Base):
    __tablename__ = "incidents"
    id: Mapped[uuid.UUID] = _id()
    farm_id: Mapped[uuid.UUID] = _fk("farms")
    animal_id: Mapped[uuid.UUID] = _fk("animals")
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # Farmer-reported facts, observed behaviour, and professional findings are kept apart (PRD Section 8).
    reported_facts: Mapped[dict] = mapped_column(JSONB)
    professional_findings: Mapped[dict | None] = mapped_column(JSONB)
    related_alert_ids: Mapped[list] = mapped_column(JSONB, default=list)
    document_media_ids: Mapped[list] = mapped_column(JSONB, default=list)
    reported_by: Mapped[uuid.UUID] = _fk("users", index=False)
    created_at: Mapped[datetime] = _created()


class Claim(Base):
    __tablename__ = "claims"
    __table_args__ = (
        _status_check("status", ("draft", "pending_approval", "submitted", "assessment_pending", "accepted", "rejected"),
                      "ck_claims_status"),
    )
    id: Mapped[uuid.UUID] = _id()
    farm_id: Mapped[uuid.UUID] = _fk("farms")
    policy_id: Mapped[uuid.UUID] = _fk("policies")
    incident_id: Mapped[uuid.UUID] = _fk("incidents")
    status: Mapped[str] = mapped_column(String(20), default="draft")
    evidence_checklist: Mapped[list] = mapped_column(JSONB, default=list)
    farmer_declaration: Mapped[str | None] = mapped_column(Text)
    submission_receipt: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = _created()


class AgentAction(Base):
    """An immutable proposal version. Approval binds to `payload_sha256` and `evidence_manifest_version`."""

    __tablename__ = "agent_actions"
    __table_args__ = (
        _status_check("action_type", ("POLICY_APPLICATION", "PREMIUM_PAYMENT", "INSURER_NOTIFICATION", "CLAIM_SUBMISSION"),
                      "ck_agent_actions_type"),
        _status_check("status", ("draft", "pending_approval", "approved", "executing", "succeeded", "failed", "unknown",
                                 "declined", "cancelled", "expired"), "ck_agent_actions_status"),
        UniqueConstraint("lineage_id", "version", name="uq_agent_actions_lineage_version"),
    )
    id: Mapped[uuid.UUID] = _id()
    farm_id: Mapped[uuid.UUID] = _fk("farms")
    lineage_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    action_type: Mapped[str] = mapped_column(String(30))
    animal_id: Mapped[uuid.UUID] = _fk("animals")
    payload: Mapped[dict] = mapped_column(JSONB)
    payload_sha256: Mapped[str] = mapped_column(String(64))
    evidence_manifest_version: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default="pending_approval")
    proposed_by: Mapped[str] = mapped_column(String(100))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    decided_by: Mapped[uuid.UUID | None] = _fk("users", nullable=True, index=False)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decision: Mapped[str | None] = mapped_column(String(10))
    created_at: Mapped[datetime] = _created()


class Execution(Base):
    """One provider dispatch. The unique idempotency key stops a retried request from executing twice."""

    __tablename__ = "executions"
    __table_args__ = (
        _status_check("status", ("executing", "succeeded", "failed", "unknown"), "ck_executions_status"),
        UniqueConstraint("farm_id", "idempotency_key", name="uq_executions_idempotency"),
        # At most one successful or in-flight execution per approved action.
        Index("uq_executions_one_live_per_action", "action_id", unique=True,
              postgresql_where=text("status IN ('executing', 'succeeded', 'unknown')")),
    )
    id: Mapped[uuid.UUID] = _id()
    farm_id: Mapped[uuid.UUID] = _fk("farms")
    action_id: Mapped[uuid.UUID] = _fk("agent_actions")
    idempotency_key: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(20), default="executing")
    provider_receipt: Mapped[dict | None] = mapped_column(JSONB)
    error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = _created()
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class WalletEntry(Base):
    """Append-only sandbox ledger. The balance is the sum of entries; no real funds are held."""

    __tablename__ = "wallet_entries"
    id: Mapped[uuid.UUID] = _id()
    farm_id: Mapped[uuid.UUID] = _fk("farms")
    execution_id: Mapped[uuid.UUID | None] = _fk("executions", nullable=True)
    amount_minor: Mapped[int] = mapped_column(BigInteger)
    currency: Mapped[str] = mapped_column(String(3))
    memo: Mapped[str] = mapped_column(String(300))
    created_at: Mapped[datetime] = _created()


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (
        _status_check("status", ("queued", "running", "succeeded", "failed"), "ck_jobs_status"),
        Index("ix_jobs_queue", "status", "created_at"),
    )
    id: Mapped[uuid.UUID] = _id()
    farm_id: Mapped[uuid.UUID] = _fk("farms")
    job_type: Mapped[str] = mapped_column(String(50))
    status: Mapped[str] = mapped_column(String(20), default="queued")
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)
    result: Mapped[dict | None] = mapped_column(JSONB)
    error: Mapped[str | None] = mapped_column(Text)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    created_by: Mapped[uuid.UUID | None] = _fk("users", nullable=True, index=False)
    created_at: Mapped[datetime] = _created()
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AuditEvent(Base):
    """Append-only history of identity, review, approval, and execution events."""

    __tablename__ = "audit_events"
    __table_args__ = (
        _status_check("actor_type", ("user", "agent", "system", "worker"), "ck_audit_actor_type"),
        Index("ix_audit_farm_time", "farm_id", "created_at"),
        Index("ix_audit_entity", "entity_type", "entity_id"),
    )
    id: Mapped[uuid.UUID] = _id()
    farm_id: Mapped[uuid.UUID] = _fk("farms", index=False)
    actor_type: Mapped[str] = mapped_column(String(10))
    actor_id: Mapped[str | None] = mapped_column(String(100))
    action: Mapped[str] = mapped_column(String(100))
    entity_type: Mapped[str] = mapped_column(String(50))
    entity_id: Mapped[str] = mapped_column(String(100))
    details: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = _created()
