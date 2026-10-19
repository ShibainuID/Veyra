"""Build synthetic enrollment videos from dataset photos to exercise the enrollment worker.

These are test fixtures, not demo footage: real enrollment needs one continuous phone video.
- continuous.mp4: one R11 cow, zooming out from the head to the whole body, ArUco marker pasted on the flank.
- spliced.mp4: an R9 muzzle clip followed by a different R11 cow, which the worker must flag as a cut.

usage: python scripts/make_sample_videos.py
"""

from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "ml/runs/sample_videos"
R11 = ROOT / "ml/data/raw/mendeley_weight/Cattle side view and back view dataset/Cattle side and back view images/side view"
R9 = ROOT / "ml/data/raw/li2022_muzzle/BeefCattle_Muzzle_Individualized"
W, H, FPS = 1280, 720, 24
MARKER_PX = 240


def with_marker(img: np.ndarray) -> np.ndarray:
    marker = cv2.aruco.generateImageMarker(cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50), 7, MARKER_PX)
    marker = cv2.copyMakeBorder(marker, 30, 30, 30, 30, cv2.BORDER_CONSTANT, value=255)
    out = img.copy()
    h, w = img.shape[:2]
    y, x = int(0.42 * h), int(0.5 * w)
    out[y:y + marker.shape[0], x:x + marker.shape[1]] = cv2.cvtColor(marker, cv2.COLOR_GRAY2BGR)
    return out


def zoom_clip(img: np.ndarray, start: tuple[float, float, float], end: tuple[float, float, float], seconds: float) -> list[np.ndarray]:
    """Crop windows interpolated from start to end, each (centre x, centre y, width) as image fractions."""
    h, w = img.shape[:2]
    frames = []
    n = int(seconds * FPS)
    for t in np.linspace(0, 1, n):
        cx, cy, fw = (s + (e - s) * t for s, e in zip(start, end))
        cw = fw * w
        ch = cw * H / W
        x0 = int(np.clip(cx * w - cw / 2, 0, w - cw))
        y0 = int(np.clip(cy * h - ch / 2, 0, h - ch))
        frames.append(cv2.resize(img[y0:y0 + int(ch), x0:x0 + int(cw)], (W, H), interpolation=cv2.INTER_AREA))
    return frames


def write(path: Path, frames: list[np.ndarray]) -> None:
    vw = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), FPS, (W, H))
    for f in frames:
        vw.write(f)
    vw.release()
    print(f"{path.name}: {len(frames) / FPS:.1f}s")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    cow = with_marker(cv2.imread(str(R11 / "3.png")))
    head_to_body = (zoom_clip(cow, (0.08, 0.36, 0.14), (0.08, 0.36, 0.14), 2.0)
                    + zoom_clip(cow, (0.08, 0.36, 0.14), (0.5, 0.5, 1.0), 3.0)
                    + zoom_clip(cow, (0.5, 0.5, 1.0), (0.5, 0.5, 1.0), 2.0))
    write(OUT / "continuous.mp4", head_to_body)

    muzzle = cv2.imread(str(next((R9 / "cattle_0100").glob("*.jpg"))))
    other_cow = with_marker(cv2.imread(str(R11 / "6.png")))
    spliced = (zoom_clip(muzzle, (0.5, 0.5, 0.9), (0.5, 0.5, 0.75), 2.5)
               + zoom_clip(other_cow, (0.5, 0.5, 1.0), (0.5, 0.5, 1.0), 2.5))
    write(OUT / "spliced.mp4", spliced)


if __name__ == "__main__":
    main()
