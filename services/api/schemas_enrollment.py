"""Request and response models for enrollment and jobs (`/enrollments`, `/jobs`).

Perception payloads (manifest, identity, estimates) are the adapters' dicts stored verbatim, so their models
name the fields the app relies on and allow the rest (`extra="allow"`): an adapter that adds a field does not
break the contract. Every perception result carries `source` (`prototype`, `simulated`, `documented`).
"""

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from schemas import UTCDateTime

EnrollmentStatus = Literal["created", "uploaded", "processing", "review", "confirmed", "rejected", "failed"]
JobStatus = Literal["queued", "running", "succeeded", "failed"]
Decision = Literal["register_new", "link_existing", "reject"]


class EnrollmentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sample_key: str | None = Field(None, description="A demo sample from `demo/fixtures/enrollment_samples.json`.")


class UploadTarget(BaseModel):
    method: Literal["PUT"]
    url: str


class EnrollmentCreated(BaseModel):
    id: str
    status: EnrollmentStatus
    sample_key: str | None
    retry_of_id: str | None
    upload: UploadTarget


class JobAccepted(BaseModel):
    job_id: str


class AnimalIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=80)
    breed: str = Field(min_length=1, max_length=80)
    breed_category: str = Field(min_length=1, max_length=40)
    sex: Literal["F", "M"]
    birth_date: date | None = None


class ConfirmBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: Decision
    animal: AnimalIn | None = Field(None, description="For `register_new`; defaults to the sample's proposal.")
    link_to: str | None = Field(None, description="For `link_existing`: an animal id on this farm.")
    override_note: str | None = Field(None, max_length=500,
                                      description="Required to register a possible duplicate, or with a required "
                                                  "view missing or an uncertain identity.")
    reject_reason: str | None = Field(None, max_length=500, description="Required for `reject`.")


class JobRef(BaseModel):
    id: str
    status: JobStatus


class Candidate(BaseModel):
    model_config = ConfigDict(extra="allow")

    animal_id: str
    animal_name: str | None = None
    cosine: float | None = None
    inliers: int | None = None


class Identity(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str
    method_version: str
    outcome: Literal["candidate", "new", "uncertain"]
    reason: str | None = None
    animal_id: str | None = None
    animal_name: str | None = None
    candidates: list[Candidate] = []
    possible_duplicate: bool


class ViewOut(BaseModel):
    model_config = ConfigDict(extra="allow")

    frame_id: str | None
    time_s: float | None
    media_id: str | None = None
    url: str | None = None
    crop_media_id: str | None = None
    crop_url: str | None = None


class Manifest(BaseModel):
    model_config = ConfigDict(extra="allow")

    processing_mode: str | None = None
    source: str | None = None
    method_version: str | None = None
    video: dict[str, Any] | None = None
    views: dict[str, ViewOut] = {}
    checks: dict[str, Any] = {}
    review_required: bool | None = None
    review_reasons: list[str] = []


class EnrollmentSummary(BaseModel):
    id: str
    status: EnrollmentStatus
    sample_key: str | None
    video_media_id: str | None
    video_url: str | None
    processing_mode: str | None
    review_reasons: list[str]
    sources: dict[str, str | None] | None
    capabilities: dict[str, bool] | None
    decision: dict[str, Any] | None
    reviewer_id: str | None
    animal_id: str | None
    retry_of_id: str | None
    created_by: str
    created_at: UTCDateTime
    updated_at: UTCDateTime
    job: JobRef | None


class EnrollmentOut(EnrollmentSummary):
    manifest: Manifest | None
    identity: Identity | None
    estimates: dict[str, dict[str, Any]] | None


class EnrollmentList(BaseModel):
    items: list[EnrollmentSummary]


class JobOut(BaseModel):
    id: str
    kind: str
    subject_id: str
    status: JobStatus
    result: dict[str, Any] | None
    error: dict[str, Any] | None
