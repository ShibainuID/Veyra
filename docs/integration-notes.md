# Integration notes: feat/veyra-ml-pipeline → feat/veyra-app

For the ML team, about merge `c69fd1b` (2026-10-20).

## What happened

`feat/veyra-app` holds the integrated app: the backend for the full PRD scope (enrollment, passport and passbook, valuation, insurance advisory, agent wallet approvals, monitoring replays, alerts, assistant, and claims) plus the web app in `apps/web`. It started from `feat/veyra-ml-pipeline` at `9222836` and had about 430 API tests when the merge landed.

At the same time, `feat/veyra-ml-pipeline` gained a second backend: PostgreSQL, UUID ids, a skip-locked job queue, and foundation, enrollment, passport and valuation routes. The two overlap in 18 core files.

The merge keeps the integrated backend. Your ML code (`adapters/{muzzle,weight,age}`, `workers/video_enrollment.py`, `models/`, `ml/`) is untouched and is called through `adapters/perception.py`.

## Carried over from your branch

- `VEYRA_YOLO_WEIGHTS`: segmentation weights, either an Ultralytics name or a local path for offline machines.
- The weight step reuses the video worker's ArUco `scale_reference` for the body frame (`scale_override`).
- The numpy-to-JSON conversion before storage. The integrated backend already had it as `_jsonable`.

## Not carried over (superseded)

- `domain/{jobs,perception,security}.py`, `persistence/storage.py`, `routes/foundation.py`, `seed.py`, `workers/runner.py`, and the root `tests/`. Their equivalents are `workers/jobs.py`, `adapters/perception.py`, `persistence/media.py`, `persistence/seed.py` and `services/api/tests/`.
- PostgreSQL (docker-compose, `scripts/local_postgres.sh`). The integrated backend runs on SQLite with explicit `BEGIN IMMEDIATE` writing sessions; the rules are in the `persistence/db.py` docstring. A Postgres move is possible after the demo but means replacing those SQLite-specific session rules.
- The demo price setting of 4.00 USD/kg. The demo fixtures use 5.20 USD/kg (`demo/fixtures/herd.json`).
- Persisted SIFT features (`.npz`) for the gallery. The integrated facade caches references in memory per media id. Persisting them would be a good next step if gallery start-up gets slow.

## How to work from here

Branch from `feat/veyra-app`. Run `cd services/api && uv sync --extra perception && uv run pytest -q`. New perception capabilities go behind `adapters/perception.Perception`, which must:

- tag every result with `source` and `method_version`;
- fall back to the labeled fixture on any failure;
- never be imported at the top of fixture-mode code paths.

## Second merge: origin/main → feat/veyra-app (`3b454fa`, 2026-10-20)

`origin/main` added the partner's camera-tracking work. The ML assets were carried over: the calf detector notebooks, scripts, and results under `ml/`, `services/api/models/calf_detector_v1.pt` (Git LFS) with its model card, and the BoT-SORT adapter `services/api/adapters/tracking.py`. Its backend modules were not, for the same reason as the first merge: they duplicate the integrated backend on a different stack (PostgreSQL, a separate job queue). That covers `domain/{jobs,monitoring,perception,replays,security,tracks}.py`, `persistence/storage.py`, `routes/{cameras,foundation}.py`, `seed.py`, `workers/runner.py`, the root `tests/`, `pytest.ini`, `docker-compose.yml`, and the Postgres scripts. Monitoring in the app still runs the recorded scenario replays through `workers/replay.py`; wiring `adapters/tracking.py` in would mean producing scenario-shaped tracks from footage behind the same association and movement rules.

## Third merge: origin/main → feat/veyra-app (2026-10-20)

`origin/main` added the Veo video demo (PR #2). Carried over:

- `demo/media/veo/`: the Veo prompts, reference images (from 8-Calves, R11, Li 2022, all CC BY 4.0, and frames of the phone video), the two AI-generated videos, the tracked CCTV output, and its run report. Videos and demo images are Git LFS (`.gitattributes`). All of it is simulated footage and must be labelled that way.
- `adapters/tracking.py` now also accepts a COCO detector and then keeps only animal classes, so people are never tracked. Nothing in the integrated backend imports the adapter yet, so app behaviour is unchanged. On the Veo CCTV video, COCO YOLOv8x gave one box per calf; `calf_detector_v1` split the scanned calf and tracked the worker.

Not carried over, for the same reason as the earlier merges:

- `domain/monitoring.py` and `domain/passport.py` changes (last sighting from confirmed track links) and their root test: they belong to the superseded camera backend.
- `services/api/scripts/run_video_demo.py`: it drives the superseded `/cameras` routes, `seed.py`, and `workers/runner.py` on PostgreSQL. Its results are kept in `demo/media/veo/out/run_report.json`: the phone video enrolled as a new animal (teeth view and ArUco marker missing, so weight needs review), and the scan on the yellow mat handed the identity to exactly one CCTV track, which held it to the end of the clip while 12 other calves stayed unidentified.

Wiring the Veo CCTV footage into the app's monitoring means turning `adapters/tracking.py` output into scenario-shaped tracks for `workers/replay.py`, behind the existing association and movement rules.
