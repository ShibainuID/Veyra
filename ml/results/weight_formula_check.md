# Weight formula check on R11 (72 Inner Mongolia cattle)

Formulas from PRD Section 4.5, applied to the dataset's **tape-measured** heart girth (HG) and oblique body length (BL), compared with recorded scale weight (341–644 kg).

| Formula | MAE (kg) | MAPE | Bias (kg) | Within 10% |
| --- | --- | --- | --- | --- |
| `schaeffer_metric_v1` (HG² × BL / 10838) | 27.4 | 5.7% | +5.5 | 90% |
| `crevat_v1` (80 × HG³, m) | 37.8 | 7.9% | +29.1 | 71% |
| Mean of both | 30.7 | 6.4% | +17.3 | 86% |

Correlation with weight: HG 0.914, BL 0.845.

## Reading

- Schaeffer fits these Chinese cattle well when HG and BL are measured with a tape; Crevat overestimates by about 29 kg on average.
- This is the best case for the formulas. Image-based HG and BL (marker-scaled side view) add measurement error on top, so field accuracy will be lower and must be measured separately.
- The PRD's ensemble rule (retain both, flag disagreement) is reasonable, but Crevat's systematic bias suggests weighting Schaeffer more or recalibrating Crevat's constant on local data.

## Local calibration (6-fold cross-validation, seed 42)

| Formula | Fitted constant | CV MAPE | CV bias | Within 10% |
| --- | --- | --- | --- | --- |
| Schaeffer, refitted divisor | 11034 (original 10838) | 5.9% | -0.3% | 86% |
| `crevat_r11_v1` | 75.8 (original 80) | 6.0% | +0.6% | 88% |

Schaeffer keeps its original divisor in the PRD (`schaeffer_metric_v1`), because refitting barely changes it. Crevat uses the refitted constant. Schaeffer residuals span about -8.6% to +8.2% between the 10th and 90th percentiles, which the PRD uses as each formula's own uncertainty band.
