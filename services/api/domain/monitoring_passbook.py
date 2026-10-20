"""Passbook lines for monitoring events: camera identification, lost tracks, and alert review.

Imported by the monitoring and alert routes, so these formatters are registered before any passbook is built.
They replace B3's generic `alert.created` and `alert.acknowledged` lines with the alert's plain summary.
"""

from domain.passbook import PassbookContext, register_formatter
from persistence.models import AuditEvent, Camera


def _camera_name(event: AuditEvent, ctx: PassbookContext) -> str:
    camera_id = event.data.get("camera_id")
    camera = ctx.get(Camera, camera_id)
    return camera.name if camera else (camera_id or "camera")


@register_formatter("alert.created")
def _alert_created(event: AuditEvent, ctx: PassbookContext) -> dict:
    kind = event.data.get("kind")
    title = "Alert · reduced movement" if kind == "reduced_movement" else "Observation quality warning"
    return {"title": title, "detail": event.data.get("summary")}


@register_formatter("alert.acknowledged")
def _alert_acknowledged(event: AuditEvent, ctx: PassbookContext) -> dict:
    return {"title": "Alert acknowledged", "detail": event.data.get("note"), "stamp": {"kind": "confirmed"}}


@register_formatter("alert.resolved")
def _alert_resolved(event: AuditEvent, ctx: PassbookContext) -> dict:
    return {"title": "Alert resolved", "detail": event.data.get("note"), "stamp": {"kind": "confirmed"}}


@register_formatter("alert.note_added")
def _alert_note(event: AuditEvent, ctx: PassbookContext) -> dict:
    title = "Assessment note" if event.data.get("note_kind") == "assessment" else "Review note"
    return {"title": title, "detail": event.data.get("text")}


@register_formatter("track.associated")
def _track_associated(event: AuditEvent, ctx: PassbookContext) -> dict:
    data = event.data
    if data.get("method") == "human_review":
        detail = "Human review" + (f" · {data['note']}" if data.get("note") else "")
    elif data.get("method") == "zone_handoff":
        detail = (f"Scanned alone in the scan zone · muzzle scan {data.get('inliers')} inliers · "
                  f"quality {data.get('quality')}")
    else:
        detail = f"Muzzle match · {data.get('inliers')} inliers · quality {data.get('quality')}"
    return {"title": f"Identified on camera {_camera_name(event, ctx)}", "detail": detail,
            "stamp": {"kind": "confirmed"}}


@register_formatter("track.lost")
def _track_lost(event: AuditEvent, ctx: PassbookContext) -> dict:
    reason = (event.data.get("reason") or "unspecified").replace("_", " ")
    return {"title": f"Camera track lost · {_camera_name(event, ctx)}",
            "detail": f"Tracking lost ({reason}); later sightings on this track are not attributed to the animal."}


@register_formatter("track.unassigned")
def _track_unassigned(event: AuditEvent, ctx: PassbookContext) -> dict:
    note = event.data.get("note")
    return {"title": f"Camera track unassigned · {_camera_name(event, ctx)}",
            "detail": f"Human review · {note}" if note else "Human review"}
