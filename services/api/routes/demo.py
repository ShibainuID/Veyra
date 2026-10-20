"""Demo controls: reset to a scenario and the sandbox provider switches (`/demo/*`).

`POST /demo/claims/{id}/insurer-update` (managers) plays the sandbox insurer's assessment of a submitted claim.

Hidden (`NOT_FOUND`) unless `VEYRA_DEMO_MODE` is on; that check runs before auth. Reset (which reseeds every farm)
needs a manager of the demo farm; changing the settings needs a manager; any signed-in user may read their farm's
settings.
"""

from datetime import datetime
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from config import get_settings
from domain import claims, clock, insurer_updates
from domain.auth import APPROVERS, Principal
from domain.errors import DomainError
from persistence.db import get_read_session, get_session
from persistence.models import DemoSettings
from persistence.seed import DEMO_FARM_ID, reset_database
from routes.deps import current_principal, require_roles
from schemas import error_responses
from schemas_finance import ClaimDetail, InsurerUpdateRequest

Scenario = Literal["fresh", "post-enrollment"]
PaymentMode = Literal["succeed", "fail", "timeout"]
InsurerActivation = Literal["confirm", "withhold"]


def require_demo_mode() -> None:
    if not get_settings().demo_mode:
        raise DomainError("NOT_FOUND", "Resource not found.")


router = APIRouter(prefix="/demo", tags=["demo"], dependencies=[Depends(require_demo_mode)])


class ResetResult(BaseModel):
    status: Literal["reset"]
    scenario: Scenario
    animals: int


class DemoSettingsUpdate(BaseModel):
    payment_mode: PaymentMode
    insurer_activation: InsurerActivation


class DemoSettingsOut(DemoSettingsUpdate):
    farm_id: str
    updated_at: datetime


def _settings_row(session: Session, farm_id: str) -> DemoSettings:
    row = session.get(DemoSettings, farm_id)
    if row is None:
        raise DomainError("NOT_FOUND", "Demo settings are not seeded; reset the demo first.")
    return row


def _out(row: DemoSettings) -> DemoSettingsOut:
    return DemoSettingsOut(farm_id=row.farm_id, payment_mode=row.payment_mode,
                           insurer_activation=row.insurer_activation, updated_at=row.updated_at)


def require_demo_farm_manager(principal: Principal = Depends(require_roles(*APPROVERS))) -> Principal:
    if principal.farm_id != DEMO_FARM_ID:
        raise DomainError("FORBIDDEN_ROLE", "Only a manager of the demo farm can reset the demo.",
                          {"required": list(APPROVERS), "role": principal.role, "farm_id": DEMO_FARM_ID})
    return principal


# The demo's AI-generated (Google Veo) clips, by the only names this route serves (demo/media/veo/VEO_PROMPTS.md).
FOOTAGE = {
    "video_cctv.mp4": "video_cctv.mp4",  # the CCTV clip the veo_barn scenario overlays
    "video_cctv_tracked.mp4": "out/video_cctv_tracked.mp4",  # the ML teammate's tracker render of the same clip
    "video_hp.mp4": "video_hp.mp4",  # the phone enrollment video
}
FOOTAGE_PROVENANCE = "simulated; AI-generated footage (Google Veo), not a real farm"
_LFS_POINTER = b"version https://git-lfs"


def footage_dir() -> Path:
    return get_settings().repo_root / "demo" / "media" / "veo"


@router.get("/footage/{name}", response_class=FileResponse,
            responses={200: {"content": {"video/mp4": {}}, "description": "The clip; supports HTTP Range."},
                       **error_responses(404)})
def footage(name: str) -> FileResponse:
    """Stream one of the demo's AI-generated clips (read-only, demo mode only, no sign-in: a `<video>` element
    cannot send a bearer token, and these clips hold no farm data). Unknown names are 404; so is a clip whose Git LFS
    content was never pulled."""
    relative = FOOTAGE.get(name)
    path = footage_dir() / relative if relative else None
    if path is None or not path.is_file():
        raise DomainError("NOT_FOUND", "Footage not found.", {"name": name})
    with path.open("rb") as handle:
        if handle.read(len(_LFS_POINTER)) == _LFS_POINTER:
            raise DomainError("NOT_FOUND", "This clip is a Git LFS pointer; run `git lfs pull` to fetch it.",
                              {"name": name})
    return FileResponse(path, media_type="video/mp4", filename=name, content_disposition_type="inline",
                        headers={"Cache-Control": "public, max-age=3600", "X-Veyra-Provenance": FOOTAGE_PROVENANCE})


@router.post("/reset", dependencies=[Depends(require_demo_farm_manager)], responses=error_responses(401, 403, 404, 422))
def reset(scenario: Scenario = "fresh") -> ResetResult:
    return ResetResult(status="reset", scenario=scenario, animals=reset_database(scenario))


@router.get("/settings", responses=error_responses(401, 404))
def get_demo_settings(principal: Principal = Depends(current_principal),
                      session: Session = Depends(get_read_session)) -> DemoSettingsOut:
    return _out(_settings_row(session, principal.farm_id))


@router.put("/settings", responses=error_responses(401, 403, 404, 422))
def put_demo_settings(body: DemoSettingsUpdate, principal: Principal = Depends(require_roles(*APPROVERS)),
                      session: Session = Depends(get_session)) -> DemoSettingsOut:
    row = _settings_row(session, principal.farm_id)
    row.payment_mode = body.payment_mode
    row.insurer_activation = body.insurer_activation
    row.updated_at = clock.now()
    session.commit()
    return _out(row)


@router.post("/claims/{claim_id}/insurer-update", response_model=ClaimDetail,
             responses=error_responses(401, 403, 404, 409, 422))
def insurer_update(claim_id: str, body: InsurerUpdateRequest, principal: Principal = Depends(require_roles(*APPROVERS)),
                   session: Session = Depends(get_session)) -> dict:
    """Play the sandbox insurer's assessment of a submitted claim for the demo: record what the insurer reports
    (`under_review`, `more_info_requested`, `approved` with an optional stated settlement, `declined`). Recorded as a
    provider event labeled sandbox; VEYRA never decides a claim or pays it."""
    insurer_updates.record_update(session, principal, claim_id, **body.model_dump())
    session.commit()
    return claims.claim_view(session, claims.farm_claim(session, principal.farm_id, claim_id))
