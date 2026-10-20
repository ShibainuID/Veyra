# VEYRA Full-Stack Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (this session) or superpowers:executing-plans (separate session) to implement this plan task by task.

**Goal:** Ship the PRD's demo journey end to end: enrollment → passport → valuation → policy comparison → approved application and premium → camera replay → movement alert → assistant lookup → incident → claim submission. The journey runs on a real API with a persisted state machine, an audit trail, and the in-progress AI adapters connected behind replaceable interfaces.

**Architecture:** One FastAPI service in `services/api` (top-level packages beside the ML team's `adapters/` and `workers/`) over SQLite with SQLAlchemy 2. Media is stored on local disk behind signed URLs. Processing runs as persisted jobs on an in-process thread pool. A perception facade picks the ML team's prototype adapters when their dependencies and models are present and falls back to labeled fixtures per capability otherwise. A language-model adapter calls Claude (`claude-opus-5-5`) for policy explanations and query parsing, with a deterministic offline fallback. The React/TypeScript app in `apps/web` consumes a typed client generated from the API's OpenAPI document.

**Tech stack:** Python 3.12, FastAPI, SQLAlchemy 2, Pydantic 2, `anthropic` SDK, pytest, uv. Vite 8, React 19, TypeScript, React Router 8, TanStack Query 5, Tailwind CSS 4, openapi-typescript + openapi-fetch, lucide-react, Atkinson Hyperlegible Next/Mono (Fontsource), Vitest.

**Design authority:** `PRODUCT.md`, the surface brief `.impeccable/surfaces/apps-web.md` (direction contract: Ear Tag world plus Passbook Ledger functions), and `C:\Users\ASUS\.claude\skills\impeccable\reference\craft-floor.md`, read before any UI edit. DESIGN.md is written at the end by the `impeccable-documenter` from the shipped build, not before.

---

## 0. Conventions (binding for every task)

- **Run the API** from `services/api`: `uv run uvicorn main:app --reload --port 8000`. Import root is `services/api`, so modules import as `from domain.actions import ...`, matching the ML code's `from adapters.weight import ...`.
- **Tests:** `cd services/api && uv run pytest -q`. Every task adds tests first (TDD). Tests use a temp data dir and synchronous jobs (`VEYRA_SYNC_JOBS=1`, `VEYRA_REPLAY_SPEED=0`) via `tests/conftest.py`.
- **IDs:** strings. Seeded and demo-created animals use `animal-demo-NNN`; other records use `<prefix>-<uuid4 hex[:12]>` (e.g. `act-1a2b3c4d5e6f`).
- **Time:** UTC, ISO 8601 with `Z`. `domain/clock.py` exposes `now()` so tests can freeze it.
- **Money:** integer minor units plus an ISO currency code (`USD` only). Never floats.
- **Units:** explicit fields (`unit: "kg"`, `"months"`).
- **Provenance:** every adapter output carries `source ∈ {live, prototype, simulated}` plus `method_version`.
- **Error envelope:** `{"error": {"code": "APPROVAL_STALE", "message": "...", "details": {...}}}`. Codes and HTTP status: `IDENTITY_UNCONFIRMED` 409, `EVIDENCE_INCOMPLETE` 409, `APPROVAL_REQUIRED` 409, `APPROVAL_STALE` 409, `ACTION_EXPIRED` 409, `INSUFFICIENT_SANDBOX_FUNDS` 409, `DUPLICATE_EXECUTION` 409, `INVALID_STATE` 409, `FORBIDDEN_ROLE` 403, `UNAUTHENTICATED` 401, `NOT_FOUND` 404, `VALIDATION_FAILED` 422, `IDEMPOTENCY_KEY_REQUIRED` 400.
- **Auth (demo):** `Authorization: Bearer <token>`. Seeded tokens: `demo-manager`, `demo-operator`, `demo-vet`, `demo-assessor`, and `other-farm-manager` (second farm, for scoping tests). The internal worker uses `X-Service-Token: $VEYRA_SERVICE_TOKEN` (default `demo-worker-token`). Every query is farm-scoped; another farm's record returns 404.
- **Roles:** `manager` (everything, the only approver and executor), `operator` (enroll, review tracks, acknowledge alerts, draft actions, record incidents), `vet` (assessment notes on alerts and incidents), `assessor` (read claims).
- **Audit:** every state change calls `domain.audit.record(session, actor, event_type, subject_type, subject_id, animal_id=None, data={})`. Actor types: `user`, `agent`, `system`, `provider`. Agent proposals, human decisions, and provider results are separate events.
- **Commits:** conventional, small, one per task step group, ending with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Never touch `ml/`, `services/api/adapters/{muzzle,weight,age}`, `services/api/workers/video_enrollment.py`, or `services/api/models/` (ML-team owned); import them only.

## 1. Repository layout

```text
apps/web/                         # Vite React app
services/api/
  main.py                         # FastAPI app factory, router registration, error handlers
  config.py                       # Settings from env (dataclass)
  persistence/db.py               # engine, SessionLocal, Base, init_db
  persistence/models.py           # ALL ORM tables (Task B2)
  persistence/media.py            # store/hash/sign media files
  persistence/seed.py             # demo seed + reset
  domain/                         # pure-ish business rules (no FastAPI imports)
    clock.py ids.py errors.py audit.py auth.py
    valuation.py eligibility.py premiums.py
    actions.py wallet.py claims.py
    association.py movement.py assistant.py
  adapters/                       # ML-owned muzzle/weight/age + ours:
    perception.py                 # capability facade (prototype vs fixture)
    llm/__init__.py llm/claude.py llm/offline.py llm/schemas.py
    sandbox/insurer.py sandbox/payment.py
  workers/
    jobs.py                       # job runner (thread pool, persisted)
    enrollment_job.py             # orchestrates perception for an enrollment
    replay.py                     # camera replay runner
  routes/                         # one module per area, thin
    health.py auth_routes.py animals.py enrollments.py jobs.py media.py
    insurance.py agent.py wallet.py monitoring.py alerts.py assistant.py
    incidents.py claims.py audit.py demo.py
  schemas.py                      # Pydantic request/response models (OpenAPI source)
  scripts/export_openapi.py
  tests/ (conftest.py, domain/, integration/)
shared/schemas/openapi.json       # exported contract (committed)
demo/fixtures/                    # age_estimates.json (ML), policies.json, herd.json,
                                  # enrollment_samples.json, incidents.json
demo/scenarios/                   # healthy.json, anomaly.json, lost_identity.json, build_scenarios.py
demo/media/README.md              # which footage files to drop in
docs/demo-script.md docs/assumptions.md docs/plans/
.env.example
```

## 2. Data model (Task B2 creates all of it)

| Table | Key columns |
| --- | --- |
| `farms` | id, name |
| `users` | id, farm_id, name, role, token (unique) |
| `animals` | id, farm_id, name, breed, sex, birth_date?, identity_status (`confirmed`/`pending_review`), confirmed_by, confirmed_at, ownership_doc_refs JSON, enrollment_id?, created_at |
| `media` | id, farm_id, kind (`video`/`frame`/`crop`/`clip`/`document`), path, sha256, content_type, bytes, created_at |
| `animal_references` | id, animal_id, view (`muzzle`/`teeth`/`body`), media_id, crop_media_id?, enrollment_id, frame_time_s, quality JSON |
| `enrollments` | id, farm_id, status (`created`/`uploaded`/`processing`/`review`/`confirmed`/`rejected`/`failed`), sample_key?, video_media_id?, processing_mode, manifest JSON, identity JSON, estimates JSON, review_reasons JSON, decision JSON, reviewer_id?, animal_id?, created_by, created_at, updated_at |
| `jobs` | id, farm_id, kind, subject_id, status (`queued`/`running`/`succeeded`/`failed`), result JSON, error JSON, created_at, updated_at |
| `estimates` | id, animal_id, kind (`age`/`weight`), range_low, range_high, point?, unit, source, method_version, evidence JSON, review_required, review_reason, created_at |
| `valuations` | id, animal_id, version, weight_low_kg, weight_high_kg, weight_basis (`estimate`/`override`), estimate_id?, unit_price_minor_per_kg, currency, price_source, price_date, value_low_minor, value_high_minor, confirmed_by, created_at |
| `policy_applications` | id, farm_id, animal_id, product_id, provider_id, terms_version, insured_value_minor, premium_minor, deductible_minor, currency, coverage_start, coverage_end, status (`draft`/`submitted`/`accepted`/`rejected`), provider_ref?, created_at |
| `policies` | id, farm_id, animal_id, application_id, product_id, provider_id, terms_version, insured_value_minor, deductible_minor, currency, status (`awaiting_payment`/`paid_pending_activation`/`active`/`lapsed`), effective_date?, expiry_date?, activation_receipt JSON?, created_at |
| `evidence_manifests` | id, farm_id, subject_type, subject_id, version, items JSON `[{type, ref, sha256?, label}]`, manifest_hash, created_at; unique(subject_type, subject_id, version) |
| `agent_actions` | id, farm_id, action_type, animal_id, version, supersedes_id?, payload JSON, payload_hash, evidence_manifest_id?, evidence_manifest_version?, status, rationale, proposed_by_type (`agent`/`user`), proposed_by_id, expires_at, decided_by?, decided_at?, decision?, decision_note?, cancel_reason?, created_at |
| `action_executions` | id, action_id (unique), idempotency_key (unique), status (`executing`/`succeeded`/`failed`/`unknown`), provider_id, provider_receipt JSON?, error JSON?, started_at, completed_at? |
| `wallet_entries` | id, farm_id, entry_type (`credit`/`debit`/`hold`/`release`), amount_minor, currency, action_id?, description, created_at |
| `provider_records` | id, provider (`sandbox-insurer`/`sandbox-pay`), operation, idempotency_key, request JSON, response JSON, created_at; unique(provider, operation, idempotency_key) |
| `demo_settings` | farm_id PK, payment_mode (`succeed`/`fail`/`timeout`), insurer_activation (`confirm`/`withhold`), updated_at |
| `cameras` | id, farm_id, name, location, map_x, map_y (pen-map coordinates, shared with herd map) |
| `replays` | id, farm_id, scenario_id, camera_id, status (`running`/`finished`/`failed`), started_at, speed, finished_at? |
| `tracks` | id, replay_id, camera_id, track_key, animal_id?, association_status (`unassigned`/`associated`/`uncertain`), association_method?, association_evidence JSON?, first_seen, last_seen |
| `observations` | id, farm_id, camera_id, track_id, animal_id?, association_status, observed_at, bbox JSON [x,y,w,h] (0–1), visibility, event (`frame`/`muzzle_match`/`track_lost`), media_ref?, source |
| `alerts` | id, farm_id, kind (`reduced_movement`/`observation_quality`), animal_id?, track_id?, camera_id, window_start, window_end, baseline_start?, baseline_end?, rule JSON, clip JSON, status (`open`/`acknowledged`/`resolved`), notes JSON list, created_at |
| `incidents` | id, farm_id, animal_id, policy_id?, kind (`accidental_injury`/`death`/`theft`/`illness`), occurred_at, description, estimated_loss_minor, currency, reported_by, facts JSON, documents JSON, professional_findings JSON list, linked_alert_ids JSON, created_at |
| `claims` | id, farm_id, policy_id, incident_id, animal_id, status (`draft`/`ready`/`submitted`/`assessment_pending`), checklist JSON, declaration_confirmed, declaration_by?, claimed_amount_minor, currency, evidence_manifest_id?, receipt JSON?, assessment_status?, created_at, updated_at |
| `audit_events` | id, farm_id, actor_type, actor_id, event_type, subject_type, subject_id, animal_id?, data JSON, created_at |

## 3. Fixtures (Task B2)

**`demo/fixtures/herd.json`**: farm `farm-wahyu` ("Wahyu Farms"); users with the tokens above (manager "W. Santoso", operator "A. Pratama", vet "dr. R. Lestari", assessor "Sandbox Mutual Assessor"). Five confirmed animals: `animal-demo-002` Bima (Ongole, M), `-003` Melati (Brahman cross, F), `-004` Gatot (Limousin cross, M), `-005` Dewi (Friesian Holstein, F), `-006` Rama (Bali cattle, M). Each has weight and age estimates (`simulated`), a valuation at 520 minor/kg (5.20 USD/kg, price source "Demo reference price (fictional)", 2026-10-01), and references without media. Two policies are active (002 on `basic-mortality`, 003 on `mortality-theft`), and 003 has an ownership document reference. Three cameras: `cam-pen-a`, `cam-pen-b`, `cam-pen-c` with map coordinates. One `observation_quality` alert is open on 004. The wallet holds a 1,000,000 minor credit ("Sandbox top-up"). Second farm `farm-other` has one animal `animal-other-001` and the `other-farm-manager` user.

**`demo/fixtures/policies.json`** (catalog version `sample-v1`, provider `sandbox-insurer` "Sandbox Mutual", fictional):

| product_id | Name | Eligibility rules (`field op value`, unknown when the field is missing) | Premium | Deductible | Covered perils | Payout formula | Claim requirements |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `basic-mortality` | Basic Mortality & Accident | identity_status == confirmed; age_months 6–120; valuation_confirmed == true | 3.5% of insured value per year | 10% of insured value | accidental_injury, death | `max(0, min(eligible_loss, remaining_limit) - deductible)` | identity_reference, active_policy, incident_facts, farmer_declaration, observation_evidence, vet_assessment |
| `mortality-theft` | Mortality + Theft | as above, plus ownership_document == present | 5.2% per year | flat 15000 minor | accidental_injury, death, theft | none (illustration not offered) | above + ownership_document |
| `dairy-health-plus` | Dairy Health Plus | breed_category == dairy; age_months ≤ 96; vet_health_check_days ≤ 30 | 6.8% per year | 5% | illness, accidental_injury | none | above + vet_health_record |

Insured value = the lower bound of the latest confirmed valuation ("insures up to the lower bound of the confirmed indicative range"), stated in the terms. Each rule and exclusion carries a `terms_ref` such as `sample-v1 §2.1`. Exclusions are listed per product (pre-existing conditions, neglect, war, unrecorded animals).

**`demo/fixtures/enrollment_samples.json`**: three keys.
- `sample-enrollment-001`: views at 1.5 s / 3.2 s / 6.0 s; identity `new` (`no_verified_match`, two low-inlier candidates); weight 480–560 kg (image path, band 0.121); age from the ML `age_estimates.json`. Becomes Sari (`animal-demo-001`, Bali cattle, F).
- `sample-enrollment-dup`: identity `candidate` `animal-demo-002` (inliers 31) → possible duplicate.
- `sample-enrollment-unclear`: muzzle view missing; identity `uncertain` `insufficient_quality`.

**`demo/fixtures/incidents.json`**: the demo incident for animal-demo-001: `accidental_injury`, "Left hind lameness found at morning check after reduced-movement alert", estimated loss 60000 minor.

**`demo/scenarios/*.json`**, generated by `build_scenarios.py` (seeded, deterministic, committed): `{id, label, camera_id, source: "simulated", duration_s: 180, fps: 2, window_s: 30, clip: "demo/media/<camera>.mp4" | null, tracks: [{track_key, frames: [{t, bbox, visibility}], events: [{t, type: "muzzle_match", candidate_animal_id, inliers, quality} | {t, type: "track_lost", reason}]}]}`.
- `healthy`: tracks for 001 and 002 with muzzle matches at t=4 and t=9 and steady movement. No alert.
- `anomaly`: 001 moves normally for 0–60 s (baseline), then its speed drops more than 70% for 90–180 s. One `reduced_movement` alert. 002 stays normal.
- `lost_identity`: 002 is matched at t=5 and lost to occlusion at t=70; a new track `t-14` appears at t=75 with no muzzle event and stays `unassigned`. Its low-visibility window yields an `observation_quality` warning, never a passport association.

## 4. Core rules (exact behavior)

**Valuation:** `value_low = weight_low_kg × unit_price_minor_per_kg`, same for high, with floor rounding to minor units. An override replaces the weight range, and both the original estimate and the override are shown. Each confirmation creates a new `version`.

**Eligibility:** for each product, evaluate every rule against facts `{identity_status, age_months_low/high, valuation_confirmed, ownership_document, breed_category, vet_health_check_days}`. Any false rule makes the product `ineligible` (reasons listed). Otherwise, any missing fact makes it `unknown` (lists what review is needed). Otherwise `eligible`. Age rules use the full range: eligible only when the whole range is inside, ineligible when the whole range is outside, unknown when it straddles. The premium is computed only for `eligible`/`unknown`: `premium = round_half_up(insured_value × rate_bps / 10000)`. The LLM explains these results; it never decides them.

**Agent actions** (`domain/actions.py`):
- Types and payload fields (canonical JSON, keys sorted, `separators=(",",":")`, then SHA-256):
  - `POLICY_APPLICATION`: animal_id, product_id, provider_id, terms_version, insured_value_minor, premium_minor, deductible_minor, currency, coverage_start, coverage_end, disclosed_fields, evidence_manifest_version.
  - `PREMIUM_PAYMENT`: animal_id, policy_application_id, policy_id, provider_id, amount_minor, currency, terms_version, evidence_manifest_version, mode="sandbox".
  - `INSURER_NOTIFICATION`: animal_id, alert_id, policy_id, provider_id, summary, evidence_manifest_version.
  - `CLAIM_SUBMISSION`: claim_id, policy_id, incident_id, animal_id, provider_id, claimed_amount_minor, currency, evidence_manifest_version, declaration_confirmed.
- **Propose** (manager or operator, or agent on their behalf): the animal must be `confirmed`, else `IDENTITY_UNCONFIRMED`. The payload is built server-side by a per-type builder from current records; the client never supplies amounts. A matching evidence manifest version is created or reused. Status goes `draft → pending_approval` immediately (`draft` exists only while invalid). `expires_at = now + 30 min`. Proposing a type for the same subject while one is pending cancels the old one (`cancel_reason="superseded"`, `supersedes_id` set on the new one).
- **Decide** (manager only, else `FORBIDDEN_ROLE`): the body is `{decision: approve|decline, payload_hash, version, note?}`. A hash or version mismatch gives `APPROVAL_STALE`, and expiry gives `ACTION_EXPIRED` (status becomes `expired`). Approve leads to `approved`, decline to `declined`. Both are audited.
- **Execute** (manager only; `Idempotency-Key` header required):
  1. If an execution with this key exists for this action, return it. If it is `unknown`, reconcile first by looking up the provider record by key.
  2. If an execution exists for the action under a different key, return `DUPLICATE_EXECUTION`.
  3. The status must be `approved`, else `APPROVAL_REQUIRED` (or `INVALID_STATE`). Expired gives `ACTION_EXPIRED`.
  4. **Stale check:** rebuild the payload from current records. If its hash differs from the approved hash, set the action to `cancelled` (`approval_stale`) and return `APPROVAL_STALE`.
  5. For payments, the available balance (credits − debits − holds + releases) must be at least the amount, else `INSUFFICIENT_SANDBOX_FUNDS`.
  6. In one transaction: insert the execution (`executing`; the unique action_id and key guard concurrency, and an `IntegrityError` maps to `DUPLICATE_EXECUTION`), set the action to `executing`, and write the ledger `hold`. Commit.
  7. Call the provider adapter with the idempotency key.
  8. In one transaction: on success, mark the execution and action `succeeded` with the receipt, convert the hold (`release` + `debit`), and apply the domain effects. On failure, mark both `failed` and `release`. On timeout, mark both `unknown`.
  9. Audit `provider_result` separately from the decision.
- **Domain effects:**
  - Application success → application `accepted`, policy created `awaiting_payment`.
  - Payment success → policy `paid_pending_activation` and an insurer activation job enqueued. That job asks the sandbox insurer, which, when `insurer_activation=confirm`, returns `{activated: true, effective_date}` → policy `active` plus an audit `provider` event. **Payment alone never sets `active`.**
  - Notification success → receipt only.
  - Claim success → claim `submitted`, then `assessment_pending` from the insurer receipt.

**Sandbox providers:** deterministic, with an idempotent store in `provider_records` (the same key returns the same response). The payment mode comes from `demo_settings`: `fail` returns `{status: "declined", code: "SANDBOX_DECLINED"}`, and `timeout` raises `ProviderTimeout` after recording the request, so reconciliation later finds a `succeeded` record (simulating a charge that landed).

**Identity association** (`domain/association.py`): a track becomes `associated` only from a `muzzle_match` with inliers above 5 and quality of at least 0.6, for an animal that exists, is `confirmed`, and is in the same farm, or through explicit human review (`PATCH /tracks/{id}` by an operator or manager). `track_lost` sets the track to `uncertain`; later observations on that track carry `animal_id = null`. A new `track_key` starts `unassigned`. Observations copy the track's association at ingest time and never retroactively.

**Movement rule** (`domain/movement.py`), per associated track window (`window_s`): speed = mean centroid displacement per second (normalized units). Usable = mean visibility ≥ 0.6 and frame coverage ≥ 70%. Baseline = the first usable window for the same animal and camera in the replay. Alert when `speed < baseline × (1 − 0.6)`. A window that is not usable yields an `observation_quality` warning for the animal if associated, otherwise for the track. Cooldown: 10 minutes per (animal or track, camera, kind). The rule JSON stores `{name:"reduced_movement_v1", threshold:0.6, score, baseline, window_s, source:"simulated"}`. Thresholds come from config.

**Assistant** (`domain/assistant.py`): `parse(text)` returns `QueryIntent{intent: animal_lookup|location_lookup|alert_lookup|coverage_lookup|unknown, animal_refs: [str], wants: [passport|location|coverage|alerts]}` from the LLM adapter (live) or a regex parser (offline). The resolver loads farm-scoped records and builds a deterministic answer plus `facts[]` (each with `record_type`, `record_id`) plus `missing[]`. Location answers always state camera and last-observed time, never a current location. With no observation: "No camera observation is on record for X." The LLM never writes the factual answer text.

**Claims:** the draft builds a checklist from the product's `claim_requirements`. Each item is `{key, label, status: present|missing, ref?}`, sourced from: passport muzzle reference → `identity_reference`; active policy → `active_policy`; incident → `incident_facts`; `claim.declaration_confirmed` → `farmer_declaration`; a linked alert with a clip → `observation_evidence`; `incident.professional_findings` from a vet → `vet_assessment`; `ownership_doc_refs` → `ownership_document`. Proposing `CLAIM_SUBMISSION` while anything is missing returns `EVIDENCE_INCOMPLETE` with the missing keys, and the reason is preserved on the claim. An alert alone cannot create a claim: the incident is required.

## 5. API surface (`/api/v1`)

All PRD endpoints, plus: `POST /auth/whoami`, `PUT /enrollments/{id}/video` (multipart), `GET /enrollments/{id}`, `GET /media/{id}?exp&sig`, `GET /policies` (farm policies, optional `animal_id`), `GET /agent/actions?status=`, `POST /agent/actions/{id}/revise`, `GET /cameras`, `GET /demo/replays` (scenario list plus track data for the overlay), `GET /replays/{id}`, `PATCH /tracks/{id}` (human association), `GET /incidents/{id}`, `POST /incidents/{id}/findings` (vet), `PATCH /claims/{id}` (declaration), `POST /demo/reset?scenario=fresh|post-enrollment`, `PUT /demo/settings`, `GET /health` (reports perception capability availability and LLM mode). Processing endpoints return `202 {job_id}`.

## 6. AI connection

**Perception facade** (`adapters/perception.py`): `capabilities()` returns `{video: bool, muzzle: bool, weight: bool, age: True}` from import probes (`torch`, `open_clip`, `ultralytics`, `cv2`, `onnxruntime`) plus a check that `models/muzzle_embed_v1.onnx` is larger than 1 MB (not an LFS pointer). `VEYRA_PERCEPTION_MODE` is `auto` (default), `prototype`, or `fixture`.
- **Prototype path:** `workers.video_enrollment.process_video(video, out_dir, Models.load(YOLO("yolov8x-seg.pt")))`, then `MuzzleIdentifier().identify(crop, gallery)` + `check_duplicate`, where the gallery is built from DB `animal_references` muzzle crops through `identifier.reference(...)` and cached in process. Then `estimate_weight(body_frame, yolo)` and `estimate_age(sample_key or "", teeth_ids)`. Adapter dicts are stored verbatim, plus `source`.
- **Fixture path:** per-capability fallback. If `cv2` exists, frames are still extracted from the uploaded video at the fixture view times, or evenly at 20/50/80% for unknown samples. Identity and weight come from `enrollment_samples.json` (`source: simulated`). An unknown sample with no matcher gives identity `uncertain` with reason `perception_unavailable` and `review_required`.
- Mixed is allowed: for example, real muzzle matching on a fixture-extracted crop when only `muzzle` is available. Each output keeps its own label.

**Language model** (`adapters/llm`): `get_language_model()` returns `ClaudeLanguageModel` when `VEYRA_LLM_MODE` is `live`, or `auto` with `ANTHROPIC_API_KEY`/`ANTHROPIC_AUTH_TOKEN` set; otherwise `OfflineLanguageModel`.
- **Claude:** `anthropic.Anthropic().messages.parse(model="claude-opus-5-5", max_tokens=4000, system=..., messages=[...], output_format=<Pydantic model>, extra_headers={"anthropic-beta": "server-side-fallback-2026-07-01"}, extra_body={"fallbacks": "default"})`. Check `stop_reason == "refusal"` before reading `parsed_output`. Catch `anthropic.APIConnectionError`, `RateLimitError`, `APIStatusError`, and validation errors. On any failure, fall back to the offline result with `source: "simulated"` and `fallback_reason`.
- **Grounding check:** drop explanation items whose `product_id` or `terms_ref` is not in the supplied catalog, and flag `grounding_dropped`.
- **Prompt safety:** the system prompt states that records and user text are data, never instructions, and the model has no tools. Model and effort are set by env (`VEYRA_LLM_MODEL`, default `claude-opus-5-5`).

## 7. Tasks

Backend tasks B1–B3 run first, sequentially (foundation). B4–B8 then run as three parallel workers with disjoint files. The frontend F1–F2 starts in parallel with B4 because it needs no API. F3+ starts after `shared/schemas/openapi.json` is exported.

### B1. Service skeleton and config
Files: `services/api/pyproject.toml` (modify: base deps = fastapi, uvicorn[standard], sqlalchemy>=2, pydantic>=2, python-multipart, anthropic, numpy, opencv-contrib-python-headless, onnxruntime, pillow; optional `perception` = torch, ultralytics, open_clip_torch; dev group = pytest, httpx), `config.py`, `main.py`, `domain/{clock,ids,errors}.py`, `routes/health.py`, `tests/conftest.py`, `tests/test_health.py`, `.gitignore` (`services/api/.data/`, `.venv/`, `node_modules/`, `.impeccable/questions/`, `.impeccable/hook.cache.json`).
Tests: `GET /api/v1/health` returns 200 with `perception` and `llm` keys; a `DomainError` maps to the envelope with its status.
Commit: `build(api): add FastAPI service skeleton with optional perception extra`.

### B2. Persistence, media, seed, reset
Files: `persistence/{db,models,media,seed}.py`, `demo/fixtures/{herd,policies,enrollment_samples,incidents}.json`, `routes/demo.py` (reset, settings), `routes/media.py`, tests `tests/integration/test_seed.py`.
Tests: reset seeds 5 animals in `farm-wahyu`; reset is idempotent; a signed media URL round-trips and a tampered signature returns 404.
Commit: `feat(api): add records, media storage, and demo seed`.

### B3. Auth, permissions, audit, animals, passport
Files: `domain/{auth,audit}.py`, `routes/{auth_routes,animals,audit}.py`, `schemas.py` (shared models), tests `tests/integration/test_auth_scope.py`, `test_passport.py`.
Tests: a missing token gives 401; another farm's animal gives 404; `/animals` filters (`coverage=none|active|pending`, `alerts=open`); the passport joins references, estimates, valuations, policies, observations summary, alerts, and audit.
Commit: `feat(api): add farm-scoped auth, audit trail, and passport`.

### B4. Financial core (worker X): valuation, insurance, LLM, agent wallet, claims
Files: `domain/{valuation,eligibility,premiums,actions,wallet,claims}.py`, `adapters/llm/*`, `adapters/sandbox/*`, `routes/{insurance,agent,wallet,incidents,claims}.py`, tests `tests/domain/test_{valuation,eligibility,actions,wallet,claims}.py`, `tests/integration/test_financial_flow.py`.
Required tests (PRD critical verification):
- An operator decision returns 403.
- A declined, expired, or hash-mismatched action cannot execute.
- The same idempotency key returns the same execution, and a new key after success returns `DUPLICATE_EXECUTION`.
- Payment success leaves the policy `paid_pending_activation` until activation; `withhold` keeps it there.
- A timeout gives `unknown`, then a retry reconciles to `succeeded` with exactly one debit.
- Insufficient funds is refused.
- Changing the valuation after approving the application makes the payment `APPROVAL_STALE`.
- A claim missing `vet_assessment` returns `EVIDENCE_INCOMPLETE` with the reason preserved.
- An unconfirmed animal returns `IDENTITY_UNCONFIRMED`.
- The LLM: a fake client's output is grounded (a bogus terms_ref is dropped), a refusal falls back offline, and a missing key uses offline mode.
Commits: one per area (valuation, eligibility+recommendations, actions+wallet+sandbox, claims).

### B5. Enrollment and perception (worker Y), the AI connection
Files: `adapters/perception.py`, `workers/{jobs,enrollment_job}.py`, `routes/{enrollments,jobs}.py`, tests `tests/domain/test_perception_select.py`, `tests/integration/test_enrollment_flow.py` (synthetic video written with cv2: three colored segments).
Required tests:
- Fixture mode creates three view frames for `sample-enrollment-001`, and confirm-as-new creates `animal-demo-001` with references, estimates, and audit.
- The duplicate sample flags `possible_duplicate` and confirm requires `link_to` or `force_new` with a reason.
- The unclear sample stays `review` with reasons; confirming without the muzzle view requires an explicit override note, and the animal stays `pending_review` (no financial actions).
- Reject and retry create a new enrollment linked to the old one.
- The prototype path is selected only when capabilities are true (monkeypatched), and the adapters receive the expected arguments (fakes).
Commit per step.

### B6. Monitoring, alerts, assistant (worker Z)
Files: `demo/scenarios/{build_scenarios.py,healthy,anomaly,lost_identity}.json`, `domain/{association,movement,assistant}.py`, `workers/replay.py`, `routes/{monitoring,alerts,assistant}.py`, tests `tests/domain/test_{association,movement,assistant}.py`, `tests/integration/test_replay.py`.
Required tests:
- The anomaly replay creates exactly one `reduced_movement` alert for 001 with the window and clip.
- The lost-identity track never gets an animal_id.
- Cooldown dedupes.
- Alert PATCH: an operator can acknowledge; a vet can add notes; status transitions are validated.
- The three scripted queries plus a missing-evidence query return expected facts offline, and the live parser output is used when a fake client returns it.
- `/cameras/{id}/observations` requires the service token.

### B7. Contract export and integration journey
Files: `scripts/export_openapi.py`, `shared/schemas/openapi.json`, `tests/integration/test_demo_journey.py` (the whole PRD journey, about 40 steps, in fixture mode).
Commit: `test(api): cover the full demo journey`.

### F1. Web scaffold and world tokens
`apps/web` via Vite React TS. Tailwind 4 through `@tailwindcss/vite`. Fontsource variable Atkinson Next + Mono. `src/styles/tokens.css` holds the Ear Tag world tokens in OKLCH. Shell: black top bar with the tag logo, nav, role switcher (demo tokens), sandbox balance, and a bottom tab bar under 1024px. Router routes for every screen with placeholders. TanStack Query client. Vite proxy `/api → :8000`.

### F2. Components (world vocabulary)
`EarTag` (solid/outline/none, sizes sm/md/xl), `PassbookLine` (numbered, dated, amount, stamp/slot states), `Stamp` (posted/declined/failed/unknown), `StatusPill`, `Provenance`, `Money`, `Mono`, `Timestamp` (relative + absolute), `EvidenceFrame` (registered fixed-aspect frame plus missing state), `Button` (all states), `FilterChips`, `DataTable`, `Drawer`, `Skeleton`, `EmptyState`, `ErrorNotice` (maps error codes to plain copy), `Toast`. Vitest for `Money` formatting and error-copy mapping.

### F3–F10. Screens
Herd (with the passbook side panel), Enroll (camera capture with the muzzle guide box at 90% width and 1.18 aspect, plus upload; job progress; review with three registered frames, reasons, identity outcome, confirm/link/reject/retry), Passport (`/animals/:id`: big tag, evidence, estimates with uncertainty and provenance, valuation calculator, coverage, full passbook with all entries), Insurance (`/animals/:id/insurance`: three products with eligible/ineligible/unknown, premium basis, exclusions, terms refs, explanation with provenance; "Prepare application"), Approvals (`/approvals`: pending lines with the full review, approve-and-stamp, decline, execute, receipts; wallet ledger), Monitor (`/monitor`: scenario picker, canvas overlay drawn from track data, video when present, identity per track, pen map sharing coordinates with herd, live alert feed), Alerts drawer (window, clip, acknowledge, notes), Ask (command panel from the top bar and `/ask`, answers with facts linking to records), Claims (`/claims/:id`: incident, checklist, declaration, prepare submission, receipt), Audit (`/audit`).

### F11. Verification and finish
Run the browser through the full demo script at 1440×900, 1024×768, and 390×844. Run `impeccable detect --json apps/web/src`, then the `impeccable-finish-reviewer` and `impeccable-documenter` (writes DESIGN.md + `.impeccable/design.json`). Write `docs/demo-script.md`, `docs/assumptions.md`, README run instructions, and `.env.example`.

## 8. Definition of done

- `uv run pytest -q` passes, and `pnpm -C apps/web build` and `pnpm -C apps/web test` pass.
- The full five-minute demo runs offline in fixture mode, and with `ANTHROPIC_API_KEY` set the explanation and parsing show `live`.
- Every PRD critical-verification bullet has a named test.
- The finish review disposition is recorded, and DESIGN.md is documented from the build.
