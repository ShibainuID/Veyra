"""API response models, the source of the OpenAPI contract (plan Section 1: `schemas.py`).

Money fields are integers in minor units named `*_minor`, next to a `currency`. Datetimes serialize as ISO 8601
UTC ending in `Z` (`UTCDateTime`); passbook lines already carry ISO strings (`IsoTimestamp`). Routes list
`ErrorEnvelope` under `responses=` through `error_responses(...)`, so the exported contract types every error.
"""

from datetime import date, datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, PlainSerializer, WithJsonSchema

from domain import clock

_DATE_TIME_SCHEMA = WithJsonSchema({"type": "string", "format": "date-time"})
UTCDateTime = Annotated[datetime, PlainSerializer(clock.isoformat, return_type=str, when_used="json"),
                        _DATE_TIME_SCHEMA]
IsoTimestamp = Annotated[str, _DATE_TIME_SCHEMA]

CoverageStatus = Literal["active", "pending", "none"]
StampKind = Literal["approved", "declined", "posted", "failed", "unknown", "confirmed"]


class ErrorBody(BaseModel):
    code: str
    message: str
    details: dict[str, Any]


class ErrorEnvelope(BaseModel):
    error: ErrorBody


def error_responses(*statuses: int) -> dict[int | str, dict[str, Any]]:
    return {status: {"model": ErrorEnvelope} for status in statuses}


class FarmRef(BaseModel):
    id: str
    name: str


class WhoAmI(BaseModel):
    user_id: str
    name: str
    role: str
    farm: FarmRef


class ActorRef(BaseModel):
    type: str
    id: str
    name: str


class RangeEstimate(BaseModel):
    range_low: float | None
    range_high: float | None
    unit: str
    source: str


class ValuationBrief(BaseModel):
    value_low_minor: int
    value_high_minor: int
    currency: str
    price_date: date
    version: int


class Coverage(BaseModel):
    status: CoverageStatus
    policy_id: str | None
    product_id: str | None
    policy_status: str | None


class AlertCounts(BaseModel):
    open_count: int
    kinds: list[str]


class LastObservation(BaseModel):
    camera_id: str
    camera_name: str | None
    observed_at: UTCDateTime
    association_status: str


class HealthStatus(BaseModel):
    """A monitoring state from records (alerts, review notes, observations); never a diagnosis."""

    status: Literal["needs_inspection", "under_review", "observation_gap", "veterinary_reviewed", "normal",
                    "not_monitored"]
    reason: str
    since: UTCDateTime | None


class AnimalListItem(BaseModel):
    id: str
    name: str
    breed: str
    breed_category: str
    sex: str
    identity_status: str
    age: RangeEstimate | None
    weight: RangeEstimate | None
    valuation: ValuationBrief | None
    coverage: Coverage
    alerts: AlertCounts
    last_observation: LastObservation | None
    health: HealthStatus
    awaiting_approval_count: int


class HerdSummary(BaseModel):
    animal_count: int
    exposure_low_minor: int
    exposure_high_minor: int
    insured_minor: int
    uncovered_count: int
    open_alerts: int
    pending_approvals: int
    wallet_balance_minor: int
    currency: str


class AnimalList(BaseModel):
    items: list[AnimalListItem]
    summary: HerdSummary


class PassportAnimal(AnimalListItem):
    birth_date: date | None
    ownership_doc_refs: list[str]
    confirmed_by: str | None
    confirmed_at: UTCDateTime | None
    enrollment_id: str | None


class ReferenceOut(BaseModel):
    id: str
    view: str
    frame_time_s: float | None
    quality: dict[str, Any]
    media_url: str | None
    crop_url: str | None


class EstimateOut(BaseModel):
    id: str
    kind: str
    range_low: float | None
    range_high: float | None
    point: float | None
    unit: str
    source: str
    method_version: str
    evidence: dict[str, Any]
    review_required: bool
    review_reason: str | None
    created_at: UTCDateTime


class ValuationOut(BaseModel):
    id: str
    version: int
    weight_low_kg: float
    weight_high_kg: float
    weight_basis: str
    estimate_id: str | None
    unit_price_minor_per_kg: int
    currency: str
    price_source: str
    price_date: date
    value_low_minor: int
    value_high_minor: int
    confirmed_by: str
    created_at: UTCDateTime


class PolicyOut(BaseModel):
    id: str
    application_id: str | None
    product_id: str
    product_name: str | None
    provider_id: str
    terms_version: str
    insured_value_minor: int
    premium_minor: int
    deductible_minor: int
    currency: str
    status: str
    effective_date: date | None
    expiry_date: date | None
    activation_receipt: dict[str, Any] | None
    created_at: UTCDateTime


class ApplicationOut(BaseModel):
    id: str
    product_id: str
    product_name: str | None
    provider_id: str
    terms_version: str
    insured_value_minor: int
    premium_minor: int
    deductible_minor: int
    currency: str
    coverage_start: date
    coverage_end: date
    status: str
    provider_ref: str | None
    created_at: UTCDateTime


class CameraSeen(BaseModel):
    camera_id: str
    camera_name: str | None
    count: int
    last_observed_at: UTCDateTime


class ObservationSummary(BaseModel):
    last: LastObservation | None
    count: int
    cameras: list[CameraSeen]


class AlertOut(BaseModel):
    id: str
    kind: str
    status: str
    camera_id: str
    track_id: str | None
    window_start: UTCDateTime
    window_end: UTCDateTime
    baseline_start: UTCDateTime | None
    baseline_end: UTCDateTime | None
    rule: dict[str, Any]
    clip: dict[str, Any] | None
    notes: list[Any]
    created_at: UTCDateTime
    updated_at: UTCDateTime


class IncidentOut(BaseModel):
    id: str
    policy_id: str | None
    kind: str
    occurred_at: UTCDateTime
    description: str
    estimated_loss_minor: int
    currency: str
    reported_by: str
    facts: dict[str, Any]
    documents: list[Any]
    professional_findings: list[Any]
    linked_alert_ids: list[str]
    created_at: UTCDateTime


class ClaimOut(BaseModel):
    id: str
    policy_id: str
    incident_id: str
    status: str
    checklist: list[Any]
    blocked_reason: dict[str, Any] | None
    declaration_confirmed: bool
    declaration_by: str | None
    claimed_amount_minor: int
    currency: str
    evidence_manifest_id: str | None
    receipt: dict[str, Any] | None
    assessment_status: str | None
    created_at: UTCDateTime
    updated_at: UTCDateTime


class PendingActionOut(BaseModel):
    id: str
    action_type: str
    status: str
    version: int
    subject_type: str | None
    subject_id: str | None
    payload_hash: str
    amount_minor: int | None
    currency: str | None
    rationale: str | None
    proposed_by: ActorRef
    expires_at: UTCDateTime
    created_at: UTCDateTime


class Stamp(BaseModel):
    kind: StampKind
    by: str
    at: IsoTimestamp


class PassbookLine(BaseModel):
    no: int
    at: IsoTimestamp
    kind: Literal["event", "awaiting"]
    event_type: str
    title: str
    detail: str | None
    actor: ActorRef
    amount_minor: int | None
    currency: str | None
    stamp: Stamp | None
    action_id: str | None
    subject_type: str
    subject_id: str
    status: Literal["posted", "awaiting", "void"]
    expires_at: IsoTimestamp | None
    payload_hash_prefix: str | None


class ExposureSummary(BaseModel):
    exposure_low_minor: int | None
    exposure_high_minor: int | None
    insured_minor: int
    uninsured_low_minor: int | None
    currency: str | None


class Passbook(BaseModel):
    lines: list[PassbookLine]
    summary: ExposureSummary


class Passport(BaseModel):
    animal: PassportAnimal
    references: list[ReferenceOut]
    estimates: list[EstimateOut]
    valuations: list[ValuationOut]
    policies: list[PolicyOut]
    applications: list[ApplicationOut]
    observations: ObservationSummary
    alerts: list[AlertOut]
    incidents: list[IncidentOut]
    claims: list[ClaimOut]
    pending_actions: list[PendingActionOut]
    passbook: Passbook


DocumentKind = Literal["ownership", "purchase_receipt", "vet_record", "other"]


class AnimalDocumentOut(BaseModel):
    """A file on the passport. `url` is a signed, expiring download link; documents download as attachments."""

    id: str
    animal_id: str
    kind: DocumentKind
    title: str
    filename: str
    content_type: str
    bytes: int
    sha256: str
    url: str
    uploaded_by: str
    created_at: UTCDateTime


class AnimalDocumentList(BaseModel):
    items: list[AnimalDocumentOut]


class AuditEventOut(BaseModel):
    id: str
    created_at: UTCDateTime
    actor: ActorRef
    event_type: str
    subject_type: str
    subject_id: str
    animal_id: str | None
    data: dict[str, Any]
