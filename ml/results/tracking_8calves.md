# 8-Calves detection, tracking, and identity handoff

Real barn CCTV (8-Calves, Fang et al. 2025, CC BY 4.0), test video `pmfeed_4_3_16`, first 12,000 frames (10 minutes at 20 fps, 800x600). Script: `ml/scripts/eval_tracking_8calves.py`. Raw numbers: `tracking_8calves_yolov8m_12000.json` (COCO detector) and `tracking_8calves_calf_detector_v1_12000.json` (fine-tuned detector).

## Detector

`calf_detector_v1` is YOLOv8m fine-tuned on 500 hand-labelled frames, trained on Kaggle 2x T4 (notebook `ml/notebooks/detector_8calves.ipynb`, 102 epochs with early stopping, best at epoch 72). The training and validation days do not overlap with the test session.

| Validation day (100 frames, 782 calves) | Precision | Recall | mAP50 | mAP50-95 |
| --- | --- | --- | --- | --- |
| COCO YOLOv8m, animal classes | 0.777 | 0.254 | - | - |
| calf_detector_v1 | 0.936 | 0.978 | 0.987 | 0.604 |

## Tracking on the test video

| Detector + tracker | Recall | MOTA | IDF1 | ID switches |
| --- | --- | --- | --- | --- |
| COCO + ByteTrack | 0.405 | 0.319 | 0.136 | 751 |
| COCO + BoT-SORT | 0.407 | 0.323 | 0.134 | 719 |
| COCO + BoT-SORT re-ID | 0.410 | 0.323 | 0.160 | 735 |
| calf_detector_v1 + ByteTrack | 0.997 | 0.977 | 0.666 | 143 |
| calf_detector_v1 + BoT-SORT | 0.997 | 0.977 | 0.668 | 116 |
| **calf_detector_v1 + BoT-SORT re-ID** | **0.997** | **0.976** | **0.709** | 120 |

## Identity handoff

Identities are locked to tracks at the first frame, as the scan zone would do, and every later labelled calf is scored as correct, wrong, uncertain (track carries no identity), or not detected.

| calf_detector_v1 + | Rule | Correct | Wrong | Uncertain |
| --- | --- | --- | --- | --- |
| ByteTrack | naive | 0.395 | 0.000 | 0.602 |
| BoT-SORT | naive | 0.473 | 0.000 | 0.524 |
| BoT-SORT re-ID | naive | 0.543 | 0.012 | 0.442 |
| BoT-SORT re-ID | policy (gap 10 frames, overlap IoU 0.3) | 0.049 | 0.000 | 0.948 |

## Findings

- The COCO detector missed about 60% of calves; fine-tuning removed the detector as the bottleneck.
- BoT-SORT with re-ID keeps the most identities, but its generic appearance model assigns a wrong identity to 1.2% of boxes. The PRD treats a wrong identity as worse than an uncertain one, so this must be gated.
- The current policy drops an identity whenever two boxes overlap above IoU 0.3. Calves touch constantly, so the rule discards almost every identity. It needs a duration and appearance check instead of a single-frame overlap test.
- The remaining uncertain share comes from new track IDs after crowding. Reattaching them safely needs a cattle-specific re-ID embedding (planned: MultiCamCows2024).
