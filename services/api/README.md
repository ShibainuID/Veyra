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

## Backend (Phase 1)

FastAPI + SQLAlchemy on PostgreSQL. `persistence/models.py` holds every core record from PRD Section 4.4 (passport anchor, enrollment, media, estimates, valuation, observations, alerts, policies, incidents, claims, agent actions, executions, wallet ledger, jobs, audit events).

| Piece | Where | Notes |
| --- | --- | --- |
| Auth and roles | `routes/deps.py` | Bearer tokens (only SHA-256 stored); roles `manager`, `operator`, `veterinarian`, `assessor`; other farms' rows return 404 |
| Errors | `domain/errors.py` | `{"error": {"code", "message", "details"}}` with the PRD codes |
| Media | `persistence/storage.py` | Local files under `var/media`, SHA-256 and size recorded, upload limit |
| Jobs | `domain/jobs.py`, `workers/runner.py` | `SELECT ... FOR UPDATE SKIP LOCKED`, retries, handler registry |
| Audit | `domain/audit.py` | Append-only events written in the same transaction as the change |
| Wallet safety | `persistence/models.py` | Unique idempotency key per farm; at most one live execution per action (partial unique index) |

Endpoints (all under `/api/v1`):

| Area | Endpoints |
| --- | --- |
| Foundation | `GET /health`, `GET /me`, `POST /media`, `GET /media/{id}`, `GET /jobs/{id}`, `GET /audit-events` |
| Enrollment (Phase 2) | `POST /enrollments`, `GET /enrollments`, `GET /enrollments/{id}`, `POST /enrollments/{id}/video`, `POST /enrollments/{id}/process` (202 + job), `POST /enrollments/{id}/confirm`, `POST /enrollments/{id}/reject` |
| Passport (Phase 2) | `GET /animals`, `GET /animals/{id}/passport`, `POST /animals/{id}/estimates/{estimate_id}/confirm`, `POST /animals/{id}/valuations` |

Enrollment flow: `created -> uploaded -> processing -> ready | needs_review -> confirmed | rejected` (`failed` when processing exhausts its retries). The worker runs the video, muzzle, weight, and age adapters and computes the muzzle reference features, so the API process never loads models. Confirmation is a human decision: uncertain identity, a possible duplicate, or any review reason needs `acknowledge_review: true`; a missing muzzle view blocks confirmation. Only managers confirm estimates and create valuations, and valuations need a confirmed identity and a confirmed weight. Domain code depends on `domain/perception.py`; tests use a deterministic fake (`tests/fakes.py`).

## Setup

```bash
cd services/api
uv venv --python 3.12
uv pip install -e ".[dev]"            # add ",perception" for the enrollment worker and adapters
```

PostgreSQL, either with Docker from the repo root (`docker compose up -d postgres`) or with Homebrew binaries and no Docker:

```bash
scripts/local_postgres.sh init        # first time; later: start / stop / status
```

Run:

```bash
python seed.py                        # tables + demo farm + one user per role; tokens in var/dev_tokens.json
python seed.py --reset                # development only: drop and recreate all tables
uvicorn main:app --reload             # API on :8000
python -m workers.runner              # job worker
```

Tests (from the repo root, against the `veyra_test` database):

```bash
services/api/.venv/bin/python -m pytest
```
