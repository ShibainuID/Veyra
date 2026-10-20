"""Request and response models for the camera muzzle gallery (`domain.gallery`)."""

from typing import Literal

from pydantic import BaseModel, Field

from schemas import UTCDateTime
from schemas_monitoring import CameraGalleryStatus

GallerySource = Literal["prototype", "simulated"]


class GalleryReference(BaseModel):
    reference_id: str
    view: Literal["muzzle"]
    # A signed URL of the muzzle crop; null for a seeded reference without footage.
    media_url: str | None
    created_at: UTCDateTime


class GalleryAnimal(BaseModel):
    animal_id: str
    name: str
    identity_status: Literal["confirmed", "pending_review"]
    references: list[GalleryReference]


class CameraGallery(BaseModel):
    camera_id: str
    farm_id: str
    version: int
    updated_at: UTCDateTime | None
    animals: list[GalleryAnimal]
    source: GallerySource


class GalleryAck(BaseModel):
    version: int = Field(ge=0)


class GalleryAckOut(BaseModel):
    camera_id: str
    gallery: CameraGalleryStatus


class GalleryPublishOut(BaseModel):
    version: int
    published_at: UTCDateTime
    # Cameras whose acknowledgement was simulated in this request (demo mode); empty otherwise.
    acknowledged: list[str]
    source: GallerySource
    cameras: dict[str, CameraGalleryStatus]
