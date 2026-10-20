# Veyra API service

Perception adapters and workers behind the enrollment flow (PRD Sections 4.1–4.3). Every result carries a source label (`prototype`, `simulated`, or `documented`) and a `review_required` flag; none of them is an automatic decision.

| Module | Input | Output | Evidence |
| --- | --- | --- | --- |
| `workers/video_enrollment.py` | One enrollment video | Manifest with the best muzzle, teeth, and body frames, a muzzle crop, scale marker, scene cuts, and review reasons | Synthetic test videos (`ml/scripts/make_sample_videos.py`): a spliced video is flagged at the cut, a continuous one is not |
| `adapters/muzzle/` | Muzzle crop + gallery | `candidate`, `new`, or `uncertain`, plus a possible-duplicate check | Test animals: 92.5% correct candidate, 1.1% of unknown animals returned as a candidate (`ml/scripts/eval_muzzle_adapter.py`) |
| `adapters/weight/` | Body frame + marker (optional tape heart girth) | Kilogram range and measurements | 71 R11 cattle: 8.7% MAPE image path, 5.4% tape path (`ml/results/weight_adapter_eval.md`) |
| `adapters/age/` | Sample key + teeth frame IDs (optional birth date) | Simulated or documented age range | Fixture in `demo/fixtures/age_estimates.json`; no age model |
| `adapters/tracking.py` | Barn camera video | Tracks (calf_detector_v1 + BoT-SORT re-ID, boxes at 5 Hz) and evidence clips | 8-Calves test video: recall 0.997, MOTA 0.976, IDF1 0.709 (`ml/results/tracking_8calves.md`) |

## Models

- `models/muzzle_embed_v1.onnx` (Git LFS) with `models/MODEL_CARD.md` and `models/LICENSE-DINOv3.md`.
- `models/calf_detector_v1.pt` (Git LFS): fine-tuned barn camera detector, described in the same model card.
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

| Cameras (Phase 3) | `POST /cameras`, `GET /cameras`, `POST /cameras/{id}/zones`, `GET /cameras/{id}/zones`, `POST /cameras/{id}/scans`, `POST /cameras/{id}/recordings` (202 + job), `GET /cameras/{id}/recordings/{rid}`, `POST /cameras/{id}/observations` (service role only, 202 + job) |
| Monitoring (Phase 3) | `GET /animals/{id}/observations`, `GET /alerts`, `GET /alerts/{id}`, `PATCH /alerts/{id}`, `GET /alerts/{id}/evidence` |
| Demo (Phase 3) | `POST /demo/replays/{scenario}/start` (202 + job; only with `VEYRA_DEMO_MODE=1`); scenarios `healthy`, `anomaly`, `lost_identity` in `demo/fixtures/replays.json` |

Enrollment flow: `created -> uploaded -> processing -> ready | needs_review -> confirmed | rejected` (`failed` when processing exhausts its retries). The worker runs the video, muzzle, weight, and age adapters and computes the muzzle reference features, so the API process never loads models. Confirmation is a human decision: uncertain identity, a possible duplicate, or any review reason needs `acknowledge_review: true`; a missing muzzle view blocks confirmation. Only managers confirm estimates and create valuations, and valuations need a confirmed identity and a confirmed weight. Domain code depends on `domain/perception.py`; tests use a deterministic fake (`tests/fakes.py`).

## Camera monitoring (Phase 3)

```
recording (video upload, worker tracks, or demo replay)
  -> tracks                      adapters/tracking.py, or the posted/replayed tracks file
  -> scan-zone handoff           a confirmed animal scanned in a scan zone; exactly one track must dwell there
  -> continuity policy           handoff_v2: drop identity after 1 s missing or 0.25 s overlap at IoU > 0.6
  -> observations                one per track per minute: movement score, visibility, association status
  -> reduced-movement rule       median of the last 30 min < 0.5 x median of the previous 24 h (usable windows only)
  -> alert + evidence pack       versioned manifest with SHA-256; clip when the recording has video
  -> review                      acknowledge / resolve; only a veterinarian records an assessment
```

- `domain/tracks.py` holds the pure rules (handoff, continuity, movement). `ml/scripts/tune_handoff_policy.py` runs the same code on real footage (`ml/results/handoff_policy.md`).
- An observation is linked to an animal only when a confirmed link covers the whole window. An uncertain handoff, a shared track, or a released link leaves the observation without an animal. An unresolved track never inherits a passport.
- The movement score is body diagonals moved per visible minute, sampled at 1 Hz. Windows under 60% visibility do not count; if most of the last 30 minutes is unusable, the result is an `observation_quality` alert, not a health conclusion.
- The passport `health` section is `needs_inspection`, `under_review`, `observation_gap`, `veterinary_reviewed`, `normal`, or `not_monitored`. It reports observations, never a diagnosis.
- Evidence packs (`domain/evidence.py`) gain a version on every review change. Later phases bind approvals (agent wallet insurer notification) and claims to `(version, manifest_sha256)`. An alert alone cannot start a claim; a claim also needs an active policy and a farmer-confirmed incident.

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
python seed.py                        # tables + demo farm + one user per role (and the camera worker); tokens in var/dev_tokens.json
python seed.py --reset                # development only: drop and recreate all tables (needed after schema changes)
uvicorn main:app --reload             # API on :8000 (VEYRA_DEMO_MODE=1 enables /demo replays)
python -m workers.runner              # job worker
```

Tests (from the repo root, against the `veyra_test` database):

```bash
services/api/.venv/bin/python -m pytest
```
