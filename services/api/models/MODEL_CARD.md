# muzzle_embed_v1

Muzzle embedding model for Veyra's identity candidate step (PRD Section 4.2). Trained on Kaggle (2x T4, run v1), notebook `ml/notebooks/muzzle_training.ipynb`.

## Use

- Task: open-set individual cattle identification from muzzle crops. This is retrieval against a gallery of registered animals, not classification.
- Input: RGB 224x224, normalised with mean (0.485, 0.456, 0.406) and std (0.229, 0.224, 0.225). Tensor name `image`, dynamic batch.
- Output: L2-normalised 512-d embedding, tensor name `embedding`.
- Backbone: `vit_small_patch16_dinov3.lvd1689m`, last 4 blocks fine-tuned with ArcFace (margin 0.30, scale 30, 20 epochs, best epoch 13).

## Decision rule (hybrid)

1. Shortlist the top 5 gallery animals by cosine similarity of embeddings.
2. Verify each shortlisted animal with SIFT + Lowe ratio test (0.75) + RANSAC homography on CLAHE-equalised grayscale images resized to a 480 px longest side.
3. Accept the candidate with the most RANSAC inliers if it has more than 5 inliers. Otherwise return no candidate.

Do not accept matches on cosine similarity alone. A cosine threshold chosen on validation animals (0.480) let through 32.4% of unknown test animals; the inlier threshold transferred from validation to test.

## Results (Beef Cattle Muzzle database, animal-level split `ml/splits/muzzle_v1.json`)

Test animals were not used for training, checkpoint selection, or the threshold.

| Method | Rank-1 | Correct match at threshold | Unknown-animal false-match rate |
| --- | --- | --- | --- |
| **Hybrid (this model + SIFT verification)** | **0.967** | **0.925** | **0.014** |
| This model, cosine threshold only | 0.966 | 0.952 | 0.324 |
| SIFT + RANSAC only | 0.925 | 0.924 | 0.017 |
| DINOv3 zero-shot | 0.939 | 0.843 | 0.145 |

Validation threshold for the hybrid: 5 inliers (validation unknown false-match rate 0.025).

## Data and licences

- Training and evaluation data: Beef Cattle Muzzle/Noseprint database, Li, Erickson, and Xiong (2022), Zenodo record 6324361, CC BY 4.0. 268 US feedlot cattle, 4,923 cropped muzzle photographs.
- The backbone weights are DINO Materials under the DINOv3 License; a copy is in `LICENSE-DINOv3.md` and must accompany any distribution of this model.

## Limits

- US feedlot cattle and cropped still photographs. Not tested on other breeds, on Chinese or Indonesian herds, or on phone video frames.
- All images come from one collection period, so identification across months is untested.
- Scores are similarities and inlier counts, not calibrated probabilities. A match is a candidate for human review, as the PRD requires.

# calf_detector_v1

Single-class cattle detector for the barn CCTV tracker (PRD M07). YOLOv8m (COCO pretrained) fine-tuned on Kaggle (2x T4), notebook `ml/notebooks/detector_8calves.ipynb`.

## Use

- Task: detect every animal in a barn camera frame; the tracker (BoT-SORT) links detections into tracks.
- Input: video frames, `imgsz=800`, confidence 0.25. Class 0 = calf.
- Format: Ultralytics `.pt` (Git LFS). Ultralytics is AGPL-3.0; review before any closed-source deployment.

## Results

Training data: 500 hand-labelled frames from 8-Calves (Fang et al., 2025, CC BY 4.0), split by recording day. Full tables in `ml/results/tracking_8calves.md`.

| Evaluation | Precision | Recall | Other |
| --- | --- | --- | --- |
| Validation day, 100 frames | 0.936 | 0.978 | mAP50 0.987, mAP50-95 0.604 |
| Test video, 12,000 frames, with BoT-SORT re-ID | 0.980 | 0.997 | MOTA 0.976, IDF1 0.709 |

## Limitations

- One barn, one camera angle, eight calves. Other farms, adult cattle, and night footage are untested.
- The tracker's generic re-ID gave a wrong identity to 1.2% of boxes in the handoff test; identity handoff must stay gated.
