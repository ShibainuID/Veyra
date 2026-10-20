# Veyra API service

Perception adapters and workers behind the enrollment flow (PRD Sections 4.1–4.3). Every result carries a source label (`prototype`, `simulated`, or `documented`) and a `review_required` flag; none of them is an automatic decision.

| Module | Input | Output | Evidence |
| --- | --- | --- | --- |
| `workers/video_enrollment.py` | One enrollment video | Manifest with the best muzzle, teeth, and body frames, a muzzle crop, scale marker, scene cuts, and review reasons | Synthetic test videos (`ml/scripts/make_sample_videos.py`): a spliced video is flagged at the cut, a continuous one is not |
| `adapters/muzzle/` | Muzzle crop + gallery | `candidate`, `new`, or `uncertain`, plus a possible-duplicate check | Test animals: 92.5% correct candidate, 1.1% of unknown animals returned as a candidate (`ml/scripts/eval_muzzle_adapter.py`) |
| `adapters/weight/` | Body frame + marker (optional tape heart girth) | Kilogram range and measurements | 71 R11 cattle: 8.7% MAPE image path, 5.4% tape path (`ml/results/weight_adapter_eval.md`) |
| `adapters/age/` | Sample key + teeth frame IDs (optional birth date) | Simulated or documented age range | Fixture in `demo/fixtures/age_estimates.json`; no age model |

## Models

- `models/muzzle_embed_v1.onnx` (Git LFS) with `models/MODEL_CARD.md` and `models/LICENSE-DINOv3.md`.
- YOLOv8x-seg (COCO `cow` class) and OpenCLIP ViT-B-32 (LAION-2B) are downloaded on first use. Ultralytics is AGPL-3.0; review before any closed-source deployment.

## Capture assumptions

- The capture screen draws a muzzle guide box 90% of the frame width with a 1.18 aspect ratio, and the crop uses exactly that box.
- The body view needs the printed ArUco marker (`DICT_4X4_50`, 15 cm by default) in the plane of the flank.
- Teeth-view detection uses a CLIP prompt that has not been tested on real teeth footage yet.

## Setup

```bash
cd services/api
uv sync                                        # API service (perception falls back to fixtures)
uv sync --extra perception                     # adds torch, ultralytics, open_clip for the prototype ML pipeline
uv run uvicorn main:app --reload --port 8000   # http://localhost:8000/api/v1/health
uv run pytest -q
```
