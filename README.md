# VEYRA

VEYRA connects cattle identification, indicative valuation, health observations, and insurance workflows through one Digital Livestock Passport. A farm manager can follow one animal from a guided enrollment video to its passport, its indicative value, a sandbox insurance policy, a camera movement alert, and a sandbox claim, with every step tied to the same animal ID and recorded in an audit trail. Nothing financial happens without the manager's explicit approval.

This is a hackathon prototype. Every insurer, payment, and claim is a sandbox; the demo data is fixture data and is labeled that way on screen.

## Repository map

| Path | What it holds |
| --- | --- |
| `services/api/` | FastAPI backend on SQLite: passport and passbook, enrollment, valuation, insurance advisory, agent wallet (approvals and sandbox execution), monitoring replays and alerts, assistant, claims, audit. See `services/api/README.md`. |
| `apps/web/` | React 19 + Vite + Tailwind 4 web app: the pitch page at `/`, and the app from `/herd` (Herd, Enroll, Monitor, Approvals, Claims, Audit, Ask). |
| `demo/` | Fixtures (`demo/fixtures/`: herd, policies, enrollment samples, age estimates, sample incident) and recorded camera scenarios (`demo/scenarios/`). |
| `ml/` | Training and evaluation for the muzzle matcher and the weight estimate. The API calls it only through `services/api/adapters/perception.py`. |
| `shared/schemas/openapi.json` | The API contract. The web app generates its types from it. |
| `docs/` | `demo-script.md` (the five-minute demo), `assumptions.md` (fixtures, thresholds, what is simulated), integration notes. |

## Run with Docker

One image runs everything: the web app is built in a Node stage and served by the API process on the same port. You need Docker and Git LFS (`git lfs pull`, so the muzzle model in `services/api/models/` is the real file).

```bash
docker compose up --build                # http://localhost:8000
```

`/` is the pitch page; the app itself opens at `/herd` (the page's **Open the live demo** goes there).

- **Language model:** put `OPENAI_API_KEY` in the root `.env` (copy `.env.example`) to turn on GPT-6 Luna's policy explanations and question parsing. Without a key, every answer is a labeled offline template.
- **Port:** `VEYRA_PORT=8090 docker compose up` serves on another port.
- **Data:** the database and media live in the `veyra-data` volume. `docker compose down -v` deletes them; the Demo button resets them without a restart.
- **Prototype ML path:** `VEYRA_PERCEPTION_BUILD=true docker compose up --build` adds torch, Ultralytics, and OpenCLIP. The image grows by several GB, and YOLO weights download on first use.
- **Without compose:** `docker build -t veyra .` then `docker run -p 8000:8000 -v veyra-data:/data veyra`.

The container runs one uvicorn worker on purpose: background jobs and camera replays live in the API process.

## Quick start (development)

Requirements: Python 3.12 with [uv](https://docs.astral.sh/uv/), Node 22 with pnpm 10. The commands are the same on Windows (PowerShell or Git Bash) and macOS.

Backend (terminal 1):

```bash
cd services/api
uv sync
uv run uvicorn main:app --port 8000      # http://localhost:8000/api/v1/health
```

`uv sync --extra perception` adds torch, Ultralytics, and OpenCLIP for the prototype ML path. Without it, enrollment uses the labeled fixtures. A plain `uv sync` removes the extra again.

Web (terminal 2):

```bash
pnpm -C apps/web install
pnpm -C apps/web dev                     # http://localhost:5173, proxies /api to port 8000
```

If port 8000 is taken, start the API on another port and point the web app at it: `VEYRA_API_TARGET=http://127.0.0.1:8010 pnpm -C apps/web dev` (PowerShell: `$env:VEYRA_API_TARGET="http://127.0.0.1:8010"; pnpm -C apps/web dev`).

The database is created and seeded on first start under `services/api/.data/`.

## Demo accounts

There is no login. The role switcher in the top bar (in **More** on a phone) changes the demo bearer token:

| Role | Token | Can do |
| --- | --- | --- |
| Manager (W. Santoso) | `demo-manager` | Everything, including approving and declining actions and resetting the demo |
| Operator (A. Pratama) | `demo-operator` | Enroll, start replays, review tracks and alerts, record incidents, prepare actions; cannot approve |
| Vet (dr. R. Lestari) | `demo-vet` | Add professional findings to incidents; no payment authority |
| Assessor | `demo-assessor` | Read sandbox submissions (API only) |

## Demo reset

From the app: as Manager, open the flask button in the top bar (**Demo**), pick **Fresh herd** or **After enrollment**, then confirm. From a terminal:

```bash
curl -X POST "http://localhost:8000/api/v1/demo/reset?scenario=fresh" -H "Authorization: Bearer demo-manager"
```

`fresh` seeds five cattle; `post-enrollment` also seeds Sari (`animal-demo-001`) with a confirmed valuation. The sandbox provider switches (payment succeeds, fails, or times out; the insurer confirms or withholds activation) are at `PUT /api/v1/demo/settings`. The click-by-click script is in [`docs/demo-script.md`](docs/demo-script.md).

## Configuration

Every variable is optional; the defaults run the demo. `.env.example` lists them with safe values. Copy `.env.example` to `.env` at the repo root: `uv run uvicorn main:app` and `docker compose` both read it, and a variable already set in the shell wins.

| Variable | Default | Effect |
| --- | --- | --- |
| `VEYRA_DATA_DIR` | `services/api/.data` | Where the SQLite database and uploaded media live |
| `VEYRA_DATABASE_URL` | `sqlite:///<data dir>/veyra.db` | Database URL (SQLite only; the session rules are SQLite-specific) |
| `VEYRA_MEDIA_SECRET` | random per process | Signs media URLs; set it so links survive a restart |
| `VEYRA_SERVICE_TOKEN` | `demo-worker-token` | Token for the internal worker endpoints (`X-Service-Token`) |
| `VEYRA_SYNC_JOBS` | `false` | Run background jobs inline (tests use this) |
| `VEYRA_REPLAY_SPEED` | `10` | Camera replay speed multiplier; `0` ingests a whole replay at once |
| `VEYRA_PERCEPTION_MODE` | `auto` | `auto` uses each ML capability that is installed, `prototype` asks for all of them and logs what is missing, `fixture` uses labeled fixtures only |
| `VEYRA_LLM_MODE` | `auto` | `auto` goes live when the selected provider's key is set, `live` always tries it, `offline` uses the template explanation and offline parser |
| `VEYRA_LLM_PROVIDER` | `openai` | `openai` or `anthropic` |
| `VEYRA_LLM_MODEL` | `gpt-6-luna` | Model for policy explanations and question parsing (`claude-opus-5-5` when the provider is `anthropic`) |
| `VEYRA_DEMO_MODE` | `true` | Exposes `/api/v1/demo/*` (reset, replays, sandbox switches); off hides them |
| `VEYRA_YOLO_WEIGHTS` | `yolov8x-seg.pt` | Segmentation weights for the weight step: an Ultralytics name or a local path |
| `OPENAI_API_KEY` | unset | Enables the live model with the `openai` provider; without it every explanation is labeled "Template explanation (offline)" |
| `ANTHROPIC_API_KEY` | unset | The same for the `anthropic` provider |
| `VEYRA_API_TARGET` (web) | `http://127.0.0.1:8000` | Where the Vite dev and preview servers proxy `/api` |

## Tests

```bash
cd services/api && uv run pytest -q          # backend
pnpm -C apps/web typecheck
pnpm -C apps/web test
pnpm -C apps/web build
```

## Regenerating the API contract

After changing a route or schema in `services/api`:

```bash
cd services/api
uv run python -c "import json,main; open('../../shared/schemas/openapi.json','w').write(json.dumps(main.app.openapi(), indent=2))"
cd ../..
pnpm -C apps/web gen:api                     # rewrites apps/web/src/lib/api-types.ts
```

## Limits

- Sandbox only. No real money moves, no policy is bound, and no claim is filed. The wallet is a sandbox ledger; the insurer (Sandbox Mutual) and payment provider are simulated.
- The policies, prices (5.20 USD/kg), herd, camera scenarios, and enrollment samples are fixtures. Screens label every output `live`, `prototype`, `simulated`, or `documented`.
- No enrollment or camera footage ships with the repo. Media tiles say "No footage attached" and the replays draw recorded track data only.
- Alerts are observations for inspection, not diagnoses. An indicative value is not an insurer-agreed value or a payout, and the illustrative payout is not a promise.
- The muzzle matcher and weight estimate are prototypes with no production accuracy claim; age comes from a fixture.

Details: [`docs/assumptions.md`](docs/assumptions.md).
