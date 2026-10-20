"""Synthetic enrollment footage for tests: three colored, patterned segments written with cv2.VideoWriter.

Segments line up with `sample-enrollment-001`'s view times (muzzle 1.5 s, teeth 3.2 s, body 6.0 s): 0-2.5 s a
red speckled "muzzle", 2.5-4.5 s green stripes "teeth", 4.5-7 s a blue checkerboard "body".
"""

from pathlib import Path

import cv2
import numpy as np

FPS = 24
SECONDS = 7.0
SIZE = (320, 240)  # width, height
SEGMENTS = ((0.0, 2.5, "muzzle"), (2.5, 4.5, "teeth"), (4.5, SECONDS, "body"))
# BGR means of each segment, used to check that a stored frame came from the expected segment.
DOMINANT_CHANNEL = {"muzzle": 2, "teeth": 1, "body": 0}


def textured_image(seed: int = 7, size: tuple[int, int] = SIZE) -> np.ndarray:
    """A speckled texture with enough corners for SIFT (muzzle-like ridges)."""
    rng = np.random.default_rng(seed)
    w, h = size
    noise = rng.integers(0, 255, (h // 4, w // 4), dtype=np.uint8)
    gray = cv2.resize(noise, (w, h), interpolation=cv2.INTER_NEAREST)
    gray = cv2.GaussianBlur(gray, (3, 3), 0)
    return cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)


def _segment_frame(view: str, i: int) -> np.ndarray:
    w, h = SIZE
    frame = np.zeros((h, w, 3), np.uint8)
    if view == "muzzle":
        texture = textured_image(seed=3)
        frame[:] = (40, 40, 200)
        frame[:, :, 2] = np.maximum(frame[:, :, 2], texture[:, :, 2])
        frame[:, :, :2] = texture[:, :, :2] // 5
    elif view == "teeth":
        frame[:] = (40, 190, 40)
        for x in range(0, w, 16):
            frame[:, x:x + 6] = (230, 240, 230)
        frame[:, :, 1] = 200
    else:
        tile = 20
        for y in range(0, h, tile):
            for x in range(0, w, tile):
                frame[y:y + tile, x:x + tile] = (210, 60, 30) if (x // tile + y // tile) % 2 else (150, 30, 10)
    cv2.putText(frame, str(i), (8, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
    return frame


def write_enrollment_video(path: Path, seconds: float = SECONDS, fps: int = FPS) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), fps, SIZE)
    if not writer.isOpened():
        raise RuntimeError("cv2.VideoWriter could not open an mp4v writer")
    for i in range(int(seconds * fps)):
        t = i / fps
        view = next(name for start, end, name in SEGMENTS if start <= t < end or (name == "body" and t >= start))
        writer.write(_segment_frame(view, i))
    writer.release()
    return path


def dominant_channel(image: np.ndarray) -> int:
    return int(np.argmax(image.reshape(-1, 3).mean(axis=0)))
