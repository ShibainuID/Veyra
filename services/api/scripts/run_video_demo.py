"""Run the enrollment and camera handoff flow end to end on a pair of demo videos, through the real API and models.

    phone video -> enrollment (muzzle, body, weight, identity) -> confirmed passport
    scan zone   -> drawn on the yellow mat found in the camera video
    zone scan   -> the animal was scanned on the mat at `--scan-at` seconds into the camera video
    camera video -> tracker -> handoff -> observations; then an overlay video of the tracks

It uses its own database (default veyra_demo) and media folder, so development data is untouched, and every
step goes through the HTTP API with the role that would perform it.

usage (from services/api, with the perception extras installed):
    python scripts/run_video_demo.py --phone ../../demo/media/veo/video_hp.mp4 \
        --camera ../../demo/media/veo/video_cctv.mp4 --detector var/models/yolov8x.pt
"""

import argparse
import json
import shutil
import subprocess
import sys
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402

from config import SERVICE_ROOT, Settings  # noqa: E402
from main import create_app  # noqa: E402
from persistence.db import Database  # noqa: E402
from persistence.storage import MediaStore  # noqa: E402
from seed import seed  # noqa: E402
from workers.runner import WorkerContext, run_once  # noqa: E402

API = "/api/v1"


def yellow_mat_polygon(video: Path) -> list[list[float]]:
    """Normalised bounding box of the saturated yellow scan mat, merged over all frames (the animal covers part of it)."""
    cap = cv2.VideoCapture(str(video))
    union = None
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        # Straw is yellow too but much less saturated and bright than the rubber mat.
        mask = cv2.inRange(cv2.cvtColor(frame, cv2.COLOR_BGR2HSV), (20, 170, 170), (34, 255, 255))
        union = mask if union is None else cv2.bitwise_or(union, mask)
    cap.release()
    if union is None:
        raise SystemExit(f"cannot read {video}")
    h, w = union.shape
    union = cv2.morphologyEx(union, cv2.MORPH_CLOSE, np.ones((41, 41), np.uint8))
    contours, _ = cv2.findContours(union, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        raise SystemExit("no yellow scan mat found in the camera video")
    x, y, bw, bh = cv2.boundingRect(max(contours, key=cv2.contourArea))
    return [[round(px / w, 4), round(py / h, 4)] for px, py in ((x, y), (x + bw, y), (x + bw, y + bh), (x, y + bh))]


def render_overlay(video: Path, tracks: dict, links: list[dict], labels: dict[str, str], zone: list, out: Path) -> None:
    """Draw every track; tracks carrying a confirmed identity are green with the animal's display ID."""
    cap = cv2.VideoCapture(str(video))
    fps = cap.get(cv2.CAP_PROP_FPS) or 24.0
    w, h = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    writer = cv2.VideoWriter(str(out), cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h))
    frames = tracks["frames"]
    spans = {}
    for link in links:
        if link["status"] == "confirmed":
            start = datetime.fromisoformat(link["linked_from"])
            until = link["linked_until"] and datetime.fromisoformat(link["linked_until"])
            spans[link["track_id"]] = (start, until)
    zone_px = np.array([[x * w, y * h] for x, y in zone], np.int32)
    i = 0
    while True:
        ok, image = cap.read()
        if not ok:
            break
        t = i / fps
        boxes = min(frames, key=lambda f: abs(f[0] - t))[1]
        cv2.polylines(image, [zone_px], True, (0, 215, 255), 3)
        cv2.putText(image, "SCAN ZONE", (int(zone_px[0][0]), int(zone_px[0][1]) - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.9,
                    (0, 215, 255), 2)
        for tid, x0, y0, x1, y1, _ in boxes:
            label = labels.get(tid)
            color, text = ((60, 200, 60), f"{label}  (track {tid})") if label else ((170, 170, 170), f"track {tid}")
            cv2.rectangle(image, (int(x0), int(y0)), (int(x1), int(y1)), color, 3 if label else 2)
            cv2.putText(image, text, (int(x0), max(int(y0) - 8, 20)), cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2)
        cv2.putText(image, f"CAM-01  {t:05.2f}s  simulated (AI-generated) footage", (20, h - 24),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 255), 2)
        writer.write(image)
        i += 1
    writer.release()
    cap.release()
    if shutil.which("ffmpeg"):
        # OpenCV writes large mp4v files; H.264 is about five times smaller and plays in browsers.
        h264 = out.with_suffix(".h264.mp4")
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(out), "-c:v", "libx264", "-crf", "23",
                        "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(h264)], check=True)
        h264.replace(out)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--phone", type=Path, required=True)
    ap.add_argument("--camera", type=Path, required=True)
    ap.add_argument("--detector", default=None, help="Tracking detector weights (default: settings)")
    ap.add_argument("--scan-at", type=float, default=2.0, help="Seconds into the camera video when the muzzle was scanned")
    ap.add_argument("--database-url", default="postgresql+psycopg://veyra:veyra@localhost:5432/veyra_demo")
    ap.add_argument("--out", type=Path, default=Path("../../demo/media/veo/out"))
    args = ap.parse_args()

    base = Settings.from_env()
    settings = replace(base, database_url=args.database_url, media_root=SERVICE_ROOT / "var" / "demo_media",
                       calf_detector_weights=args.detector or base.calf_detector_weights)
    db = Database(settings.database_url)
    db.drop_all()
    tokens = seed(db)
    h = {role: {"Authorization": f"Bearer {t}"} for role, t in tokens.items()}
    client = TestClient(create_app(settings, db))
    ctx = WorkerContext(settings, MediaStore(settings.media_root, settings.max_upload_bytes))

    def drain():
        while run_once(db, ctx):
            pass

    out = args.out
    out.mkdir(parents=True, exist_ok=True)
    report = {}

    e = client.post(f"{API}/enrollments", json={"sample_key": "sample-enrollment-001"}, headers=h["operator"]).json()
    with args.phone.open("rb") as f:
        client.post(f"{API}/enrollments/{e['id']}/video", headers=h["operator"], files={"file": (args.phone.name, f, "video/mp4")})
    client.post(f"{API}/enrollments/{e['id']}/process", headers=h["operator"])
    drain()
    e = client.get(f"{API}/enrollments/{e['id']}", headers=h["operator"]).json()
    report["enrollment"] = {"status": e["status"], "review_reasons": e["review_reasons"],
                            "views": sorted((e["manifest"] or {}).get("views", {})),
                            "identity": e["identity_result"], "estimates": e["estimate_results"]}
    r = client.post(f"{API}/enrollments/{e['id']}/confirm",
                    json={"decision": "new_animal", "acknowledge_review": True,
                          "notes": "Demo enrollment from AI-generated footage"}, headers=h["operator"])
    if r.status_code != 200:
        print(json.dumps(report, indent=1, default=str))
        raise SystemExit(f"confirmation failed: {r.text}")
    animal = r.json()
    report["animal"] = animal

    zone = yellow_mat_polygon(args.camera)
    camera = client.post(f"{API}/cameras", json={"name": "CAM-01 barn side wall", "location": "Demo barn"},
                         headers=h["manager"]).json()
    zone_row = client.post(f"{API}/cameras/{camera['id']}/zones", json={"name": "Yellow scan mat", "polygon": zone},
                           headers=h["manager"]).json()
    started = datetime.now(UTC).replace(microsecond=0) - timedelta(minutes=5)
    client.post(f"{API}/cameras/{camera['id']}/scans", headers=h["operator"],
                json={"zone_id": zone_row["id"], "animal_id": animal["animal_id"], "enrollment_id": e["id"],
                      "scanned_at": (started + timedelta(seconds=args.scan_at)).isoformat()})
    with args.camera.open("rb") as f:
        up = client.post(f"{API}/cameras/{camera['id']}/recordings", headers=h["operator"],
                         data={"started_at": started.isoformat()}, files={"file": (args.camera.name, f, "video/mp4")}).json()
    drain()
    rec = client.get(f"{API}/cameras/{camera['id']}/recordings/{up['recording_id']}", headers=h["operator"]).json()
    report["zone"] = zone
    report["recording"] = {"status": rec["status"], "summary": rec["summary"], "links": rec["links"]}
    passport = client.get(f"{API}/animals/{animal['animal_id']}/passport", headers=h["manager"]).json()
    report["passport"] = {"display_id": passport["display_id"], "last_observed": passport["last_observed"],
                          "health": passport["health"], "estimates": passport["estimates"]}

    tracks_media = client.get(f"{API}/media/{rec['tracks_media_id']}", headers=h["operator"]).json()
    from persistence.models import Media  # noqa: E402

    with db.sessions() as s:
        tracks = json.loads(ctx.media.path(s.get(Media, tracks_media["id"]).storage_key).read_text())
    labels = {link["track_id"]: animal["display_id"] for link in rec["links"] if link["status"] == "confirmed"}
    render_overlay(args.camera, tracks, rec["links"], labels, zone, out / "video_cctv_tracked.mp4")
    (out / "tracks.json").write_text(json.dumps(tracks))
    (out / "run_report.json").write_text(json.dumps(report, indent=1, default=str))
    print(json.dumps(report, indent=1, default=str))
    print(f"wrote {out / 'video_cctv_tracked.mp4'} and {out / 'run_report.json'}")


if __name__ == "__main__":
    main()
