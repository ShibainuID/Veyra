"""Camera muzzle gallery sync: the cloud tells each pen camera which enrolled animals it should recognise.

`GET /cameras/{id}/gallery` takes the camera worker's `X-Service-Token`, or a manager's bearer token for the UI
(scoped to the manager's farm). The acknowledgement takes the service token only. `POST /cameras/gallery/publish`
is manager-only; in demo mode it also simulates the camera workers' acknowledgements.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from config import get_settings
from domain import gallery
from domain.auth import APPROVERS, Principal, ServicePrincipal
from persistence.db import get_read_session, get_session
from routes.deps import require_roles, service_or_roles, service_principal
from schemas import error_responses
from schemas_gallery import CameraGallery, GalleryAck, GalleryAckOut, GalleryPublishOut

router = APIRouter(prefix="/cameras", tags=["monitoring"])


def gallery_reader(caller: Principal | ServicePrincipal = Depends(service_or_roles(*APPROVERS))) -> str | None:
    """The farm to scope to: None for the camera worker (service token), the manager's farm otherwise."""
    return caller.farm_id if isinstance(caller, Principal) else None


@router.post("/gallery/publish", response_model=GalleryPublishOut, responses=error_responses(401, 403))
def publish_gallery(principal: Principal = Depends(require_roles(*APPROVERS)),
                    session: Session = Depends(get_session)) -> dict:
    result = gallery.publish(session, principal, simulate_acks=get_settings().demo_mode)
    result["cameras"] = gallery.status(session, principal.farm_id, result["version"])
    session.commit()
    return result


@router.get("/{camera_id}/gallery", response_model=CameraGallery, responses=error_responses(401, 403, 404))
def camera_gallery(camera_id: str, farm_id: str | None = Depends(gallery_reader),
                   session: Session = Depends(get_read_session)) -> dict:
    return gallery.gallery(session, gallery.farm_camera(session, farm_id, camera_id))


@router.post("/{camera_id}/gallery/ack", response_model=GalleryAckOut, responses=error_responses(401, 404, 422))
def acknowledge_gallery(camera_id: str, body: GalleryAck, service: ServicePrincipal = Depends(service_principal),
                        session: Session = Depends(get_session)) -> dict:
    camera = gallery.farm_camera(session, None, camera_id)
    gallery.acknowledge(session, camera, body.version, source="prototype")
    status = gallery.status(session, camera.farm_id)[camera.id]
    session.commit()
    return {"camera_id": camera.id, "gallery": status}
