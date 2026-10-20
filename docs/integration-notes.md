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
