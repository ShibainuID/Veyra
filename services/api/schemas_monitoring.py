"""Request and response models for monitoring, alerts, and the assistant (plan Section 5; OpenAPI source).

Kept apart from `schemas.py` so parallel tasks do not edit one file. Datetimes serialize as UTC ending in `Z`.
"""

from typing import Any, Literal

from pydantic import AwareDatetime, BaseModel, Field, model_validator

from schemas import UTCDateTime

AssociationStatus = Literal["unassigned", "associated", "uncertain"]
AlertKind = Literal["reduced_movement", "observation_quality"]
AlertStatus = Literal["open", "acknowledged", "resolved"]
ReplayStatus = Literal["running", "finished", "failed", "stopped"]
Want = Literal["passport", "location", "coverage", "alerts"]
Intent = Literal["animal_lookup", "location_lookup", "alert_lookup", "coverage_lookup", "unknown"]
Bbox = list[float]


# --- scenarios and replays -------------------------------------------------------------------------------------


class ScenarioFrame(BaseModel):
    t: float
    bbox: Bbox
    visibility: float


class ScenarioEvent(BaseModel):
    t: float
    type: Literal["muzzle_match", "track_lost"]
    candidate_animal_id: str | None = None
    inliers: int | None = None
    quality: float | None = None
    reason: str | None = None


class ScenarioCameraEvent(BaseModel):
    """A camera event: a muzzle scan made in the scan zone, handed to the one track inside it (or to none)."""
    t: float
    type: Literal["zone_scan"]
    animal_id: str | None = Field(default=None, description="Who the muzzle matcher says was scanned.")
    inliers: int | None = None
    quality: float | None = None


class ScanZone(BaseModel):
    polygon: list[list[float]] = Field(description="[[x, y], ...] normalized 0-1 to the camera frame.")
    label: str
    source: str
    calibrated_at: UTCDateTime


class ScenarioFootage(BaseModel):
    label: str = Field(description="The caption shown with the clip, e.g. that it is AI-generated.")
    generator: str
    kind: Literal["ai_generated"]
    tracker: str
    tracks: str
    prompts: str


class ScenarioTrack(BaseModel):
    track_key: str
    frames: list[ScenarioFrame]
    events: list[ScenarioEvent]


class Scenario(BaseModel):
    id: str
    label: str
    description: str
    camera_id: str
    camera_name: str | None
    source: str
    duration_s: float
    fps: float
    window_s: float
    clip: str | None
    footage: ScenarioFootage | None = None
    events: list[ScenarioCameraEvent] = []
    scan_zone: ScanZone | None = None
    tracks: list[ScenarioTrack]


class CameraLastObservation(BaseModel):
    id: str
    observed_at: UTCDateTime
    track_id: str
    animal_id: str | None
    animal_name: str | None
    association_status: AssociationStatus
    visibility: float
    bbox: Bbox


class CameraOut(BaseModel):
    id: str
    name: str
    location: str
    map_x: float
    map_y: float
    scan_zone: ScanZone | None = Field(description="The calibrated scan zone, if the camera has one.")
    last_observation: CameraLastObservation | None


class CameraList(BaseModel):
    items: list[CameraOut]


class ScenarioList(BaseModel):
    scenarios: list[Scenario]
    cameras: list[CameraOut]


class ReplayStarted(BaseModel):
    replay_id: str
    scenario_id: str
    status: ReplayStatus
    started_at: UTCDateTime
    anchor_at: UTCDateTime = Field(description="Observation time of scenario t=0: replays are footage ending by now.")
    speed: float
    duration_s: float


class TrackOut(BaseModel):
    id: str
    replay_id: str | None
    camera_id: str
    track_key: str
    animal_id: str | None
    animal_name: str | None
    association_status: AssociationStatus
    association_method: str | None
    association_evidence: dict[str, Any] | None
    first_seen: UTCDateTime
    last_seen: UTCDateTime


class AlertView(BaseModel):
    id: str
    kind: AlertKind
    status: AlertStatus
    animal_id: str | None
    animal_name: str | None
    track_id: str | None
    track_key: str | None
    camera_id: str
    camera_name: str
    window_start: UTCDateTime
    window_end: UTCDateTime
    baseline_start: UTCDateTime | None
    baseline_end: UTCDateTime | None
    rule: dict[str, Any]
    clip: dict[str, Any] | None
    notes: list[dict[str, Any]]
    summary: str
    created_at: UTCDateTime
    updated_at: UTCDateTime


class ReplayOut(BaseModel):
    id: str
    scenario_id: str
    camera_id: str
    status: ReplayStatus
    speed: float
    started_at: UTCDateTime
    finished_at: UTCDateTime | None
    anchor_at: UTCDateTime
    duration_s: float
    progress_s: float
    scan_zone: ScanZone | None
    tracks: list[TrackOut]
    alerts: list[AlertView]


# --- observations ----------------------------------------------------------------------------------------------


class ObservationIn(BaseModel):
    """One track observation, or (`event: "zone_scan"`) a muzzle scan in the camera's scan zone, which needs no
    track, box, or visibility: it is handed to the one track inside the zone at `observed_at`, or to none."""
    track_key: str | None = Field(default=None, min_length=1, max_length=64)
    observed_at: AwareDatetime
    bbox: Bbox | None = Field(default=None, min_length=4, max_length=4)
    visibility: float | None = Field(default=None, ge=0, le=1)
    event: Literal["frame", "muzzle_match", "track_lost", "zone_scan"] = "frame"
    candidate_animal_id: str | None = Field(default=None,
                                            description="The matched animal; for a zone_scan, the scanned one.")
    inliers: int | None = Field(default=None, ge=0)
    quality: float | None = Field(default=None, ge=0, le=1)
    reason: str | None = Field(default=None, max_length=200)
    media_ref: str | None = Field(default=None, max_length=500)
    replay_id: str | None = None

    @model_validator(mode="after")
    def _track_fields(self) -> "ObservationIn":
        if self.event != "zone_scan" and (self.track_key is None or self.bbox is None or self.visibility is None):
            raise ValueError("track_key, bbox, and visibility are required unless event is zone_scan")
        return self


class ObservationOut(BaseModel):
    id: str
    camera_id: str
    track_id: str
    animal_id: str | None
    association_status: AssociationStatus
    observed_at: UTCDateTime
    bbox: Bbox
    visibility: float
    event: str
    media_ref: str | None
    source: str


class ZoneHandoffOut(BaseModel):
    outcome: Literal["associated", "already_associated", "rejected", "no_track", "crowded", "track_uncertain",
                     "conflict"]
    reason: str | None
    message: str
    track_ids: list[str]
    track_keys: list[str]
    tracks_in_zone: int


class ObservationIngested(BaseModel):
    observation: ObservationOut | None = Field(description="Null for a zone_scan without exactly one track in "
                                                           "the zone.")
    track: TrackOut | None
    handoff: ZoneHandoffOut | None = Field(default=None, description="What a zone_scan did.")


class AnimalLastObservation(BaseModel):
    id: str
    camera_id: str
    camera_name: str | None
    observed_at: UTCDateTime
    bbox: Bbox
    visibility: float
    association_status: AssociationStatus


class QualitySummary(BaseModel):
    observations: int
    mean_visibility: float | None
    low_visibility: int
    min_visibility: float
    open_quality_alerts: int


class AnimalObservations(BaseModel):
    animal_id: str
    last_observation: AnimalLastObservation | None
    tracks: list[TrackOut]
    recent: list[ObservationOut]
    quality_summary: QualitySummary


class TrackReview(BaseModel):
    animal_id: str | None = Field(description="The confirmed animal to associate, or null to unassign the track.")
    note: str | None = Field(default=None, max_length=1000)


# --- alerts ----------------------------------------------------------------------------------------------------


class AlertList(BaseModel):
    items: list[AlertView]


class AlertReview(BaseModel):
    status: Literal["acknowledged", "resolved"] | None = None
    note: str | None = Field(default=None, max_length=2000)


# --- assistant -------------------------------------------------------------------------------------------------


class AssistantQuery(BaseModel):
    text: str = Field(min_length=1, max_length=500)
    # The asker's UTC offset in minutes east of UTC (Jakarta is 420), so times in the answer read as local
    # time; UTC when absent.
    utc_offset_minutes: int | None = Field(default=None, ge=-840, le=840)


class AssistantFact(BaseModel):
    label: str
    value: Any
    record_type: str
    record_id: str


class AssistantRecords(BaseModel):
    animals: list[dict[str, Any]]
    last_observations: list[dict[str, Any]]
    coverage: list[dict[str, Any]]
    alerts: list[AlertView]


class AssistantAnswer(BaseModel):
    intent: Intent
    parsed_by: Literal["live", "simulated"]
    answer: str
    facts: list[AssistantFact]
    records: AssistantRecords
    missing: list[str]
    fallback_reason: str | None
