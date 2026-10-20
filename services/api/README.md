# Veyra API service

Perception adapters and workers behind the enrollment flow. Every result carries a source label (`prototype`, `simulated`, or `documented`) and a `review_required` flag; none of them is an automatic decision.

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

## Backend

FastAPI + SQLAlchemy on SQLite (single process, `BEGIN IMMEDIATE` writing sessions, deferred read sessions; see the `persistence/db.py` docstring for the session rules). The full contract is exported to `shared/schemas/openapi.json`; the web app generates its types from it.

| Area | Modules | Notes |
| --- | --- | --- |
| Auth and roles | `domain/auth.py`, `routes/deps.py` | Demo bearer tokens (`demo-manager`, `demo-operator`, `demo-vet`, `demo-assessor`); farm-scoped, other farms' rows return 404 |
| Errors | `domain/errors.py`, `main.py` | One envelope everywhere: `{"error": {"code", "message", "details"}}` |
| Records and media | `persistence/models.py`, `persistence/media.py` | Signed media URLs, allow-listed content types, SHA-256 per file |
| Audit and passbook | `domain/audit.py`, `domain/passbook.py`, `domain/passport.py` | Every change is audited; each animal's passbook is built from its audit trail plus awaiting actions |
| Enrollment and perception | `domain/enrollment.py`, `adapters/perception.py`, `workers/jobs.py`, `workers/enrollment_job.py` | Real muzzle matcher when its model is present; per-capability fallback to labeled fixtures (`VEYRA_PERCEPTION_MODE`) |
| Valuation and insurance | `domain/valuation.py`, `domain/eligibility.py`, `adapters/llm/explain.py` | Deterministic eligibility and premiums; Claude only explains them (offline template without a key) |
| Agent wallet | `domain/actions.py`, `domain/wallet.py`, `adapters/sandbox/` | Approval bound to payload hash + version; idempotent execution; sandbox insurer and payment providers |
| Monitoring | `domain/association.py`, `domain/movement.py`, `workers/replay.py` | Recorded scenario replays, strict identity association, reduced-movement and observation-quality alerts |
| Assistant | `domain/assistant.py`, `adapters/llm/query.py` | Claude parses the question; the backend writes every answer from records |
| Claims | `domain/claims.py` | Policy-specific evidence checklist; submission blocked while items are missing |

## Setup

```bash
cd services/api
uv sync                                        # API service (perception falls back to fixtures)
uv sync --extra perception                     # adds torch, ultralytics, open_clip for the prototype ML pipeline
uv run uvicorn main:app --reload --port 8000   # http://localhost:8000/api/v1/health
uv run pytest -q
```

A plain `uv sync` removes the perception extra again, so on machines that run the ML pipeline always use `uv sync --extra perception`.
