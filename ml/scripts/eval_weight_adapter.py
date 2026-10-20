"""Evaluate the side-view weight adapter on the R11 calibration cattle (71 side photos, scale weights).

R11 has no scale marker, so each photo is scaled with its tape-measured withers height. The evaluation
therefore measures what the photo adds beyond a correct scale, not the marker step itself. All errors are
out-of-fold (6-fold cross-validation, seed 42); ranges use the 80th percentile of absolute relative error.

usage: python scripts/eval_weight_adapter.py
"""

import json
import sys
from pathlib import Path

import cv2
import numpy as np
import pandas as pd
from ultralytics import YOLO

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "services" / "api"))
from adapters.weight import ellipse_girth, estimate_weight, find_landmarks, segment_cow  # noqa: E402
from adapters.weight.formulas import crevat_r11_v1, schaeffer_metric_v1  # noqa: E402

R11 = ROOT / "ml/data/raw/mendeley_weight/Cattle side view and back view dataset/Cattle side and back view images"
MASKS = ROOT / "ml/runs/weight_masks.npz"
YOLO_WEIGHTS = ROOT / "ml/runs/yolo/yolov8x-seg.pt"


def load_masks(model) -> dict[int, np.ndarray]:
    if MASKS.exists():
        z = np.load(MASKS)
        return {int(k): z[k] for k in z.files}
    masks = {}
    for p in sorted((R11 / "side view").glob("*.png"), key=lambda p: int(p.stem)):
        masks[int(p.stem)] = segment_cow(cv2.imread(str(p)), model)[::2, ::2]
    np.savez_compressed(MASKS, **{str(k): v for k, v in masks.items()})
    return masks


def cv_predict(d: pd.DataFrame, fit_predict) -> np.ndarray:
    idx = np.random.default_rng(42).permutation(len(d))
    pred = np.zeros(len(d))
    for fold in np.array_split(idx, 6):
        pred[fold] = fit_predict(d.iloc[np.setdiff1d(idx, fold)], d.iloc[fold])
    return pred


def loglin(cols):
    def fp(train, test):
        X = lambda D: np.c_[np.ones(len(D)), np.log(D[cols].values)]
        b = np.linalg.lstsq(X(train), np.log(train["w"].values), rcond=None)[0]
        return np.exp(X(test) @ b)
    return fp


def tape_formulas(train, test):
    b = np.polyfit(train["wh"], train["bl"], 1)
    bl = np.polyval(b, test["wh"].values)
    hg = test["hg"].values
    return (schaeffer_metric_v1(hg, bl) + crevat_r11_v1(hg, bl)) / 2


def summary(pred: np.ndarray, truth: pd.Series) -> dict:
    e = (pred - truth.values) / truth.values
    return {"mape": round(float(np.abs(e).mean()), 4), "bias": round(float(e.mean()), 4),
            "within_10pct": round(float((np.abs(e) < 0.1).mean()), 3),
            "band_80pct": round(float(np.percentile(np.abs(e), 80)), 4)}


def main() -> None:
    model = YOLO(str(YOLO_WEIGHTS))
    masks = load_masks(model)
    tape = pd.read_excel(R11 / "measurements.xlsx")
    tape.columns = ["num", "bl", "wh", "hg", "hip", "w"]

    rows = []
    for num, mask in masks.items():
        lm = find_landmarks(mask)
        rows.append({"num": num, "wh_px": lm.withers_height_px, "cd_px": lm.chest_depth_px, "flags": ";".join(lm.flags)})
    d = pd.DataFrame(rows).merge(tape, on="num")
    ppc = d["wh_px"] / d["wh"]
    d["hg_img"] = [ellipse_girth(c, 0.725) for c in d["cd_px"] / ppc]
    k = float(np.median(d["hg"] / d["hg_img"]))
    d["hg_img"] *= k

    variants = {
        "baseline_predict_mean": cv_predict(d, lambda tr, te: np.full(len(te), tr["w"].mean())),
        "image_heart_girth_only": cv_predict(d, loglin(["hg_img"])),
        "image_heart_girth_plus_withers_height": cv_predict(d, loglin(["hg_img", "wh"])),
        "withers_height_only (image path)": cv_predict(d, loglin(["wh"])),
        "tape_heart_girth_formulas (tape path)": cv_predict(d, tape_formulas),
    }
    report = {"photos": len(d), "heart_girth_from_photo_mape": round(float(np.abs(d["hg_img"] - d["hg"]).div(d["hg"]).mean()), 4),
              "weight": {name: summary(p, d["w"]) for name, p in variants.items()}}

    # End-to-end smoke run of the adapter on full-resolution photos (scale from tape withers height).
    reviews = []
    for num in sorted(masks)[:12]:
        img = cv2.imread(str(R11 / "side view" / f"{num}.png"))
        row = d[d["num"] == num].iloc[0]
        r = estimate_weight(img, model, scale_override={"marker_id": None, "px_per_cm": 2 * row["wh_px"] / row["wh"], "marker_cm": None})
        reviews.append({"num": num, "true_kg": int(row["w"]), "range": [r.get("range_low"), r.get("range_high")],
                        "review": r["review_reason"]})
    report["adapter_smoke"] = reviews
    print(json.dumps(report, indent=1))
    (ROOT / "ml/results/weight_adapter_eval.json").write_text(json.dumps(report, indent=1))


if __name__ == "__main__":
    main()
