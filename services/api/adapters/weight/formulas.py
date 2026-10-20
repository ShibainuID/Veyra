"""Weight models for PRD Section 4.3, calibrated on the R11 cattle (72 animals, Inner Mongolia).

Two paths, chosen by the evidence available:
- Tape-measured heart girth: Schaeffer and Crevat formulas (6-fold CV MAPE 5.4%).
- Image only: log-linear model on withers height (CV MAPE 8.7%). On the calibration cattle, heart
  girth estimated from chest depth in the photo added no accuracy once withers height was known.
Ranges come from the 80th percentile of out-of-fold relative error, not from stacked assumptions.
See ml/results/weight_adapter_eval.md.
"""

import math

TAPE_HG_BAND = 0.097
IMAGE_BAND = 0.121
DISAGREEMENT_TOLERANCE = 0.15

# Body length is not read reliably from the photo (CV correlation 0.39), so it is predicted from withers height.
BL_FROM_WH = (0.9133, 43.36)
# log(W) = a + b * log(WH)
WH_LOGLIN = (-4.4177, 2.2109)


def schaeffer_metric_v1(hg_cm: float, bl_cm: float) -> float:
    return hg_cm**2 * bl_cm / 10838


def crevat_r11_v1(hg_cm: float, bl_cm: float) -> float:
    return 75.8 * (hg_cm / 100) ** 3


def wh_loglin_r11_v1(wh_cm: float) -> float:
    return math.exp(WH_LOGLIN[0] + WH_LOGLIN[1] * math.log(wh_cm))


def body_length_from_withers(wh_cm: float) -> float:
    return BL_FROM_WH[0] * wh_cm + BL_FROM_WH[1]


def ellipse_girth(depth_cm: float, width_ratio: float) -> float:
    a, b = depth_cm / 2, width_ratio * depth_cm / 2
    h = ((a - b) / (a + b)) ** 2
    # Ramanujan's second approximation of an ellipse perimeter
    return math.pi * (a + b) * (1 + 3 * h / (10 + math.sqrt(4 - 3 * h)))


def _range(mid: float, band: float) -> tuple[float, float]:
    return round(mid * (1 - band), 1), round(mid * (1 + band), 1)


def weight_from_tape_girth(hg_cm: float, wh_cm: float) -> dict:
    bl = body_length_from_withers(wh_cm)
    outputs = [
        {"model_id": "schaeffer_metric_v1", "expression": "HG^2 x BL / 10838 (kg, cm)", "kg": round(schaeffer_metric_v1(hg_cm, bl), 1)},
        {"model_id": "crevat_r11_v1", "expression": "75.8 x HG^3 (kg, m)", "kg": round(crevat_r11_v1(hg_cm, bl), 1)},
    ]
    kgs = [o["kg"] for o in outputs]
    mid = sum(kgs) / len(kgs)
    disagreement = (max(kgs) - min(kgs)) / mid
    review = disagreement > DISAGREEMENT_TOLERANCE
    lo, hi = _range(mid, TAPE_HG_BAND)
    return {"path": "tape_heart_girth", "model_outputs": outputs, "point_kg": round(mid, 1),
            "range_low": None if review else lo, "range_high": None if review else hi, "unit": "kg",
            "band": TAPE_HG_BAND, "body_length_cm": round(bl, 1), "formula_disagreement": round(disagreement, 3),
            "review_required": review, "review_reason": "formulas_disagree" if review else None}


def weight_from_image(wh_cm: float) -> dict:
    kg = wh_loglin_r11_v1(wh_cm)
    lo, hi = _range(kg, IMAGE_BAND)
    return {"path": "image_withers_height",
            "model_outputs": [{"model_id": "wh_loglin_r11_v1", "expression": "exp(-4.4177 + 2.2109 ln WH) (kg, cm)", "kg": round(kg, 1)}],
            "point_kg": round(kg, 1), "range_low": lo, "range_high": hi, "unit": "kg", "band": IMAGE_BAND,
            "review_required": False, "review_reason": None}
