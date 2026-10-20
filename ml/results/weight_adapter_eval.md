# Weight adapter evaluation on R11 (71 side photos)

Script: `ml/scripts/eval_weight_adapter.py`. Raw numbers: `weight_adapter_eval.json`.

R11 has no scale marker, so each photo is scaled with its tape-measured withers height (WH). The test therefore measures what the photo adds once the scale is correct; it does not measure marker detection or marker-scaled WH error. All numbers are out-of-fold (6-fold cross-validation, seed 42). The 80% band is the 80th percentile of absolute relative error.

## Measurements read from the photo

| Measurement | Method | Result |
| --- | --- | --- |
| Heart girth | Chest depth from the mask, elliptical chest (width ratio 0.725), scale factor 0.979 | MAPE 5.5% vs tape, correlation 0.66 |
| Body length | Trunk extent from the mask, several definitions tried | Best correlation 0.39 (MAPE 9.3%); worse than predicting it from WH (correlation 0.64) |

## Weight

| Variant | MAPE | Bias | Within 10% | 80% band |
| --- | --- | --- | --- | --- |
| Predict the mean (baseline) | 15.8% | +3.4% | 44% | ±22.6% |
| Photo heart girth only | 11.0% | +0.9% | 54% | ±17.5% |
| Photo heart girth + WH | 8.8% | +0.3% | 58% | ±12.6% |
| **WH only (adapter image path, `wh_loglin_r11_v1`)** | **8.7%** | +0.2% | 59% | **±12.1%** |
| **Tape heart girth + Schaeffer/Crevat (adapter tape path)** | **5.4%** | +0.9% | 86% | **±9.7%** |

Formulas with photo-estimated heart girth were worse than the photo-only regression (14.3% MAPE in the first run), because squaring or cubing heart girth amplifies its error.

## Decisions

- Image path uses withers height only. Photo heart girth added no accuracy once WH was known, so it is shown for review but not used for weight.
- Tape path keeps the Schaeffer and Crevat formulas, with body length predicted from WH (`BL = 0.9133 x WH + 43.36`).
- Ranges use the out-of-fold 80% bands above instead of stacking assumed uncertainties (the first version produced ranges about 470 kg wide).

## Limits

- One breed group (Horqin/Simmental crosses), one region, 341-644 kg, 72 animals.
- WH here comes from the tape. In deployment it comes from the marker, which adds error that is not yet measured. Image-path accuracy in the field will be lower than 8.7%.
- No test on phone video frames yet.
