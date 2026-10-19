"""Body measurements and weight range from one side-view frame (PRD Section 4.3).

Pipeline: cow mask -> orientation -> landmarks -> pixel measurements -> scale (ArUco marker)
-> centimetres -> weight model (tape heart girth formulas, or withers-height model when only the image
is available). Every result carries `source: prototype`.
"""

from dataclasses import dataclass, field

import cv2
import numpy as np

from .formulas import ellipse_girth, weight_from_image, weight_from_tape_girth

COCO_COW = 19
ARUCO_DICT = cv2.aruco.DICT_4X4_50
# Heart girth from chest depth, as an elliptical chest (shown for review, not used for weight).
WIDTH_RATIO = 0.725
HG_FROM_ELLIPSE = 0.9794
WH_PLAUSIBLE_CM = (90, 160)


@dataclass
class Landmarks:
    front_is_left: bool
    ground_y: int
    withers: tuple[int, int]
    chest_floor_y: int
    trunk_row: int
    trunk_x: tuple[int, int]
    flags: list[str] = field(default_factory=list)

    @property
    def withers_height_px(self) -> float:
        return float(self.ground_y - self.withers[1])

    @property
    def chest_depth_px(self) -> float:
        return float(self.chest_floor_y - self.withers[1])

    @property
    def trunk_extent_px(self) -> float:
        return float(self.trunk_x[1] - self.trunk_x[0])


def segment_cow(image_bgr: np.ndarray, model) -> np.ndarray | None:
    """Largest cow mask from a YOLOv8-seg model, or None when no cow is found."""
    r = model.predict(image_bgr, classes=[COCO_COW], imgsz=1024, verbose=False, retina_masks=True)[0]
    if r.masks is None or len(r.masks) == 0:
        return None
    masks = r.masks.data.cpu().numpy().astype(bool)
    return masks[masks.sum((1, 2)).argmax()]


def find_landmarks(mask: np.ndarray) -> Landmarks:
    h, w = mask.shape
    flags = []
    ys, xs = np.nonzero(mask)
    x0, x1 = xs.min(), xs.max()
    span = x1 - x0
    if x0 <= 2 or x1 >= w - 3 or ys.min() <= 2:
        flags.append("animal_touches_frame_edge")

    col_count = mask.sum(0)
    edge = max(1, int(0.08 * span))
    # The head/neck end is thick; the rear end has a thin tail and narrow hocks.
    front_is_left = col_count[x0:x0 + edge].mean() >= col_count[x1 - edge:x1 + 1].mean()

    ground_y = int(np.percentile(ys, 99.5))
    row_count = mask.sum(1)
    trunk_rows = np.nonzero(row_count >= 0.6 * row_count.max())[0]
    trunk_row = int(np.median(trunk_rows))
    row_xs = np.nonzero(mask[trunk_row])[0]
    trunk_x = (int(row_xs.min()), int(row_xs.max()))

    def frac_x(f: float) -> int:
        return int(trunk_x[0] + f * (trunk_x[1] - trunk_x[0])) if front_is_left else int(trunk_x[1] - f * (trunk_x[1] - trunk_x[0]))

    top_y = np.where(mask.any(0), mask.argmax(0), h)
    lo, hi = sorted((frac_x(0.20), frac_x(0.32)))
    window = top_y[lo:hi + 1]
    withers = (lo + int(np.argmin(window)), int(np.median(window)))

    # Chest floor: bottom of the first mask run from the top, in columns just behind the front legs
    # whose top run does not reach the ground (leg columns are skipped).
    lo, hi = sorted((frac_x(0.15), frac_x(0.45)))
    bottoms = []
    for x in range(lo, hi + 1):
        col = mask[:, x]
        if not col.any():
            continue
        start = int(col.argmax())
        gap = np.nonzero(~col[start:])[0]
        end = start + (int(gap[0]) if len(gap) else len(col) - start)
        if end < ground_y - 0.1 * (ground_y - start):
            bottoms.append(end)
    if bottoms:
        chest_floor_y = int(np.median(bottoms))
    else:
        chest_floor_y = int(trunk_rows.max())
        flags.append("chest_floor_from_trunk_rows")

    lm = Landmarks(front_is_left, ground_y, withers, chest_floor_y, trunk_row, trunk_x, flags)
    ratio = lm.trunk_extent_px / max(lm.withers_height_px, 1)
    if not 0.9 <= ratio <= 1.9:
        flags.append("pose_check_failed")
    return lm


def marker_px_per_cm(image_bgr: np.ndarray, marker_cm: float) -> dict | None:
    """Pixels per centimetre from the first detected ArUco marker of known side length."""
    detector = cv2.aruco.ArucoDetector(cv2.aruco.getPredefinedDictionary(ARUCO_DICT))
    corners, ids, _ = detector.detectMarkers(cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY))
    if ids is None:
        return None
    c = corners[0].reshape(4, 2)
    side_px = float(np.mean([np.linalg.norm(c[i] - c[(i + 1) % 4]) for i in range(4)]))
    return {"marker_id": int(ids[0][0]), "px_per_cm": side_px / marker_cm, "marker_cm": marker_cm}


def estimate_weight(
    image_bgr: np.ndarray,
    model,
    marker_cm: float = 15.0,
    tape_heart_girth_cm: float | None = None,
    scale_override: dict | None = None,
) -> dict:
    """Weight range from one side-view frame. `scale_override` replaces marker detection (evaluation only)."""
    result = {"source": "prototype", "method_version": "weight_side_view_v2", "review_required": False,
              "review_reason": None, "flags": []}
    mask = segment_cow(image_bgr, model)
    if mask is None:
        return {**result, "review_required": True, "review_reason": "no_cow_detected"}
    lm = find_landmarks(mask)
    result["flags"] = lm.flags
    result["landmarks_px"] = {"withers": lm.withers, "ground_y": lm.ground_y, "chest_floor_y": lm.chest_floor_y,
                              "trunk_x": lm.trunk_x, "trunk_row": lm.trunk_row, "front_is_left": lm.front_is_left}

    scale = scale_override or marker_px_per_cm(image_bgr, marker_cm)
    if scale is None:
        return {**result, "review_required": True, "review_reason": "marker_not_detected"}
    result["scale_reference"] = scale
    if lm.flags:
        return {**result, "review_required": True, "review_reason": lm.flags[0]}

    ppc = scale["px_per_cm"]
    wh = lm.withers_height_px / ppc
    cd = lm.chest_depth_px / ppc
    hg_image = HG_FROM_ELLIPSE * ellipse_girth(cd, WIDTH_RATIO)
    result["measurements"] = [
        {"name": "withers_height", "value": round(wh, 1), "unit": "cm", "source": "image_estimate"},
        {"name": "chest_depth", "value": round(cd, 1), "unit": "cm", "source": "image_estimate"},
        {"name": "heart_girth", "value": round(tape_heart_girth_cm or hg_image, 1), "unit": "cm",
         "source": "measured" if tape_heart_girth_cm else "image_estimate_not_used_for_weight"},
    ]
    if not WH_PLAUSIBLE_CM[0] <= wh <= WH_PLAUSIBLE_CM[1]:
        return {**result, "review_required": True, "review_reason": "withers_height_implausible"}

    weight = weight_from_tape_girth(tape_heart_girth_cm, wh) if tape_heart_girth_cm else weight_from_image(wh)
    result.update(weight)
    return result
