"""Request and response models for the financial core: valuation, insurance, agent wallet, incidents, claims.

Kept apart from `schemas.py` so parallel work does not collide; shared shapes (`ErrorEnvelope`, `UTCDateTime`,
`ValuationOut`, `PolicyOut`, ...) are reused from there. Money is integer minor units next to a `currency`.
"""

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, Field

from schemas import ApplicationOut, ClaimOut, IncidentOut, PolicyOut, UTCDateTime, ValuationOut  # noqa: F401

ActionType = Literal["POLICY_APPLICATION", "PREMIUM_PAYMENT", "INSURER_NOTIFICATION", "CLAIM_SUBMISSION"]
ActionStatus = Literal["draft", "pending_approval", "approved", "declined", "expired", "cancelled", "executing",
                       "succeeded", "failed", "unknown"]


# Valuation -----------------------------------------------------------------------------------------------------

class ValuationRequest(BaseModel):
    weight_basis: Literal["estimate", "override"]
    estimate_id: str | None = None
    weight_low_kg: float | None = Field(default=None, gt=0)
    weight_high_kg: float | None = Field(default=None, gt=0)
    unit_price_minor_per_kg: int = Field(gt=0)
    price_source: str = Field(min_length=1)
    price_date: date


# Insurance -----------------------------------------------------------------------------------------------------

class RuleReason(BaseModel):
    field: str
    terms_ref: str
    text: str
    status: Literal["pass", "fail", "unknown"]
    detail: str


class TermsText(BaseModel):
    text: str
    terms_ref: str


class Recommendation(BaseModel):
    product_id: str
    product_name: str
    outcome: Literal["eligible", "ineligible", "unknown"]
    reasons: list[RuleReason]
    needs_review: list[str]
    premium_minor: int | None
    deductible_minor: int | None
    currency: str
    covered_perils: list[str]
    exclusions: list[TermsText]
    payout_formula: dict[str, Any] | None


class ExplanationItem(BaseModel):
    product_id: str
    explanation: str
    terms_refs: list[str]


class Explanation(BaseModel):
    source: Literal["live", "simulated"]
    model: str | None
    fallback_reason: str | None
    summary: str
    items: list[ExplanationItem]
    caveats: list[str]
    grounding_dropped: bool


class RecommendationsOut(BaseModel):
    animal_id: str
    catalog_version: str
    insured_value_minor: int | None
    currency: str
    valuation_id: str | None
    results: list[Recommendation]
    explanation: Explanation


class PolicyDetail(PolicyOut):
    animal_id: str


class PolicyList(BaseModel):
    items: list[PolicyDetail]


# Agent actions -------------------------------------------------------------------------------------------------

class ProposeRequest(BaseModel):
    action_type: ActionType
    animal_id: str | None = None
    product_id: str | None = None
    policy_application_id: str | None = None
    alert_id: str | None = None
    claim_id: str | None = None
    rationale: str | None = Field(default=None, max_length=2000)


class DecisionRequest(BaseModel):
    decision: Literal["approve", "decline"]
    payload_hash: str
    version: int
    note: str | None = Field(default=None, max_length=2000)


class EvidenceItem(BaseModel):
    type: str
    ref: str
    label: str
    sha256: str | None = None


class EvidenceManifestOut(BaseModel):
    id: str
    version: int
    manifest_hash: str
    items: list[EvidenceItem]


class ExecutionOut(BaseModel):
    id: str
    idempotency_key: str
    status: Literal["executing", "succeeded", "failed", "unknown"]
    provider_id: str
    provider_receipt: dict[str, Any] | None
    error: dict[str, Any] | None
    started_at: UTCDateTime
    completed_at: UTCDateTime | None


class ActionReview(BaseModel):
    recipient: str
    animal_id: str | None
    amount_minor: int | None
    currency: str | None
    terms_version: str | None
    evidence_manifest_version: int | None
    balance_after_minor: int | None


class ActionOut(BaseModel):
    id: str
    action_type: ActionType
    status: ActionStatus
    version: int
    animal_id: str | None
    subject_type: str | None
    subject_id: str | None
    supersedes_id: str | None
    payload: dict[str, Any]
    payload_hash: str
    rationale: str | None
    proposed_by_type: str
    proposed_by_id: str
    expires_at: UTCDateTime
    decided_by: str | None
    decided_at: UTCDateTime | None
    decision: str | None
    decision_note: str | None
    cancel_reason: str | None
    created_at: UTCDateTime
    updated_at: UTCDateTime
    evidence_manifest: EvidenceManifestOut | None
    execution: ExecutionOut | None
    review: ActionReview


class ActionList(BaseModel):
    items: list[ActionOut]


# Wallet --------------------------------------------------------------------------------------------------------

class WalletEntryOut(BaseModel):
    id: str
    entry_type: Literal["credit", "debit", "hold", "release"]
    amount_minor: int
    currency: str
    action_id: str | None
    description: str
    created_at: UTCDateTime


class WalletOut(BaseModel):
    balance_minor: int
    available_minor: int
    held_minor: int
    currency: str
    entries: list[WalletEntryOut]


# Incidents and claims ------------------------------------------------------------------------------------------

class IncidentRequest(BaseModel):
    animal_id: str
    kind: str = Field(min_length=1)
    occurred_at: UTCDateTime
    description: str = Field(min_length=1, max_length=4000)
    estimated_loss_minor: int = Field(ge=0)
    linked_alert_ids: list[str] = Field(default_factory=list)
    facts: dict[str, Any] = Field(default_factory=dict)


class FindingRequest(BaseModel):
    summary: str = Field(min_length=1, max_length=4000)
    finding_type: Literal["vet_assessment", "vet_health_record"]


class IncidentDetail(IncidentOut):
    animal_id: str
    # The reporter's display name, so the farm's report reads as a person rather than a user id.
    reported_by_name: str | None = None


class ClaimDraftRequest(BaseModel):
    incident_id: str


class ClaimPatch(BaseModel):
    declaration_confirmed: Literal[True]


class ChecklistItem(BaseModel):
    key: str
    label: str
    status: Literal["present", "missing"]
    ref: str | None
    # Words for a person-shaped ref, e.g. "Confirmed by W. Santoso" for the declaration.
    detail: str | None = None


class IllustrativePayout(BaseModel):
    amount_minor: int
    currency: str
    expression: str
    terms_ref: str
    illustrative: Literal[True]
    note: str


class ClaimDetail(ClaimOut):
    animal_id: str
    checklist: list[ChecklistItem]
    missing: list[str]
    product_id: str | None
    illustrative_payout: IllustrativePayout | None


class ClaimList(BaseModel):
    items: list[ClaimDetail]
