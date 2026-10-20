# MVP assumptions

- **Monitoring: live observations are ingested, not movement-assessed.** Observations posted to
  `POST /api/v1/cameras/{id}/observations` (service token) go through the same identity-association rules as a
  replay and update tracks and last-seen, but the movement rule (`reduced_movement`, `observation_quality`) only runs
  inside camera replays (`POST /api/v1/demo/replays/{scenario}/start`), where windows close on scenario time.
- **Monitoring: replays are recorded footage ending by now.** A replay's observation time is
  `anchor + t`, with the anchor set so no observation is stamped after it is ingested (`anchor_at` on the replay).
- **Monitoring: a live track key silent for more than 30 s starts a new, unassigned track**, so a reused key never
  carries an earlier animal's identity.
- **Monitoring: identity comes from a scan zone or a muzzle match, and only while it is continuous.** A camera may
  have one calibrated scan zone (`camera_scan_zones`; cam-pen-a's is the ML teammate's zone from the Veo run,
  x 0.4781–0.7021, y 0.6611–0.8463). A `zone_scan` (a scenario camera event, or `POST /cameras/{id}/observations`
  with `event: "zone_scan"`) hands the scanned animal's identity to the track whose box centre is inside the zone at
  the scan time, if it is the only one (method `zone_handoff`); a track counts as present if its latest observation
  is at most 1 s old. No track: nothing happens. Two or more: nothing is handed over, and every one of them becomes
  `uncertain` ("scan one animal at a time"). The scan must pass the muzzle bar (more than 5 inliers, quality at least
  0.6, a confirmed animal of this farm). The teammate's offline worker asks a track to dwell 2 s in the zone within
  ±10 s of the scan; this rule runs online, so it uses the instant of the scan.
- **Monitoring: continuity is handoff_v2** (`ml/results/handoff_policy.md`), for every associated track whatever
  the method: the identity is released (`uncertain`) when the track is missing for more than 1.0 s, or overlaps
  another track at IoU above 0.6 for at least 0.25 s. An overlap release counts from the overlap's start, so the
  observations already stored since then are downgraded to `uncertain` (the only rewrite of an observation, and only
  ever away from an animal). A released identity is never re-attached automatically; a person can assign the track.
  Gaps are checked when the track reports again and whenever another track on the camera reports (within a replay,
  or among live tracks seen in the last 30 s). The policy was tuned on 10 minutes of one real barn and is not
  validated elsewhere; it assumes dense frames (a live feed sampled slower than one frame a second always releases).
- **Claims: a death claim needs a muzzle re-scan that matches** (`identity_verified`). The requirement is added in
  code for every `death` incident (`domain/claims.py` `IDENTITY_CHECK_KINDS`), not listed in `policies.json`, so no
  death-covering product can skip it; theft has no animal to scan and is refused. `POST /claims/{id}/identity-checks`
  crops a photo to the capture guide box (90% width, 1.18 aspect) or takes a video's muzzle crop from the perception
  facade, then runs the real muzzle matcher against this animal's enrolled references plus every other confirmed
  animal's. The matcher's candidate is the claimed animal → `match`; another animal → `mismatch` naming it; no verified
  match → `mismatch`; ambiguous or low-detail → `uncertain` (retake). When the claimed animal has no enrolled muzzle
  image on disk (seeded animals), "no match" reads `uncertain`, since there was nothing to compare with. Only the
  latest check counts; `mismatch` and `uncertain` keep `CLAIM_SUBMISSION` at `EVIDENCE_INCOMPLETE`, and a newer check
  after approval makes the approved submission stale. Without the muzzle capability an upload is `uncertain`
  (`simulated`); the demo samples (`match` / `mismatch`) are fixture outcomes labeled `simulated`.
- **Cameras: the gallery version is computed, not stored.** `version` = the gallery's animals (`confirmed`, plus
  `pending_review` flagged) + their muzzle references. Animals and references are only ever added, so it only grows
  and every enrollment that adds an animal or a muzzle reference bumps it (the fresh herd is v10; enrolling Sari makes
  v12). A camera is in sync when its last acknowledged version (`POST /cameras/{id}/gallery/ack`, service token)
  equals the current one. A status change with no new animal or reference would not change the version; no such
  transition exists today. **Push to cameras** (`POST /cameras/gallery/publish`, manager) records the published
  version and, in demo mode, simulates every farm camera's acknowledgement (labeled `simulated`); seeded references
  have no footage, so their gallery entries carry no image.

## Data and fixture provenance

Everything the demo shows comes from fixtures in `demo/` unless a screen says `live` or `prototype`.

| Fixture | What it is | Label on screen |
| --- | --- | --- |
| `demo/fixtures/herd.json` | One farm (Wahyu Farms), five seeded cattle (Bima, Melati, Gatot, Dewi, Rama), three pen cameras, four demo users, the opening sandbox wallet top-up (10,000.00 USD), two seeded policies, and the reference price | Seeded estimates `simulated`; ages from records `documented` |
| `demo/fixtures/policies.json` | The fictional catalog `sample-v1` from the fictional insurer Sandbox Mutual: Basic Mortality & Accident, Mortality + Theft, Dairy Health Plus, with eligibility rules, premium and deductible bases, exclusions, claim requirements, and terms references (`sample-v1 §…`) | "Fictional sample terms, not a market quote" |
| `demo/fixtures/enrollment_samples.json` | Three prepared enrollment samples: Sari (new animal), a duplicate of Bima, and an unclear muzzle. View timings, identity outcome, and weight are scripted; there is no footage | `simulated` |
| `demo/fixtures/age_estimates.json` | Sari's age range (24–30 months) from a dentition rule of thumb, not a model | `simulated` |
| `demo/fixtures/incidents.json` | The sample incident for Sari (left hind lameness, 600.00 USD estimated loss) behind the form's "Use the sample incident" | The farm's own report |
| `demo/scenarios/*.json` | Four synthetic camera scenarios (healthy, reduced movement, lost identity, crowded scan) at 2 fps, generated by `build_scenarios.py` with a fixed seed, and `veo_barn`: the ML teammate's real tracker output (`demo/media/veo/out/tracks.json`, yolov8x + BoT-SORT re-ID) on the AI-generated CCTV clip, converted with its timing kept (detector confidence stands in for visibility) | `simulated` |
| `demo/media/veo/*.mp4` | AI-generated (Google Veo) clips in Git LFS: `video_cctv.mp4` (the CCTV clip `veo_barn` overlays), `out/video_cctv_tracked.mp4` (the teammate's tracker render), `video_hp.mp4` (the phone enrollment video). Prompts in `VEO_PROMPTS.md`. Not a real farm | `simulated`, captioned "AI-generated footage (Veo) — not a real farm" |

The only footage is the AI-generated Veo clips, served read-only by `GET /api/v1/demo/footage/{name}` (demo mode only, three allow-listed names, `video/mp4` with Range; no sign-in, since a `<video>` element cannot send a token and the clips hold no farm data). It is never presented as real: the Monitor stage captions it, and the enrollment option says so. The heifer scanned in the Veo clip was enrolled on the teammate's own backend, not on this farm, so the `veo_barn` scan names no animal and every track stays unassigned. Synthetic scenarios show "No footage attached" on the camera stage; a passport frame from a prepared sample reads "on record, but no footage is attached to show".

## Thresholds

| Rule | Value | Where |
| --- | --- | --- |
| Reduced movement | Alert when tracked movement is at least 60% below the animal's earlier window on the same camera (threshold 0.6, so below 40% of baseline), over 30 s windows | `domain/movement.py` (`MovementConfig.threshold`) |
| Observation quality | A window with mean visibility below 0.6 or frame coverage below 0.7 raises an observation-quality warning instead of a movement judgment | `MovementConfig.min_visibility`, `min_coverage` |
| Alert cooldown | One alert per animal, camera, and kind within 10 minutes | `MovementConfig.cooldown` |
| Live track gap | A live track key silent for more than 30 s starts a new, unassigned track | `domain/association.py` (`LIVE_TRACK_GAP`) |
| Scan-zone handoff | Exactly one track whose box centre is in the zone at the scan (latest observation at most 1 s old); the scan itself passes the muzzle bar | `domain/association.py` (`zone_scan`, `ZONE_PRESENCE_S`) |
| Identity continuity (handoff_v2) | Release when missing more than 1.0 s, or overlapping another track at IoU above 0.6 for at least 0.25 s, counted from the overlap's start; observations within 0.02 s are one camera frame | `domain/association.py` (`MAX_GAP_S`, `CROWD_IOU`, `CROWD_S`, `SAME_FRAME_S`); `ml/results/handoff_policy.md` |
| Muzzle match | A candidate needs more than 5 verified (geometrically consistent) points and a muzzle crop quality of at least 0.6; otherwise the outcome is `new` or `uncertain`, never a forced match | `adapters/muzzle/`, `enrollment_samples.json` (`accept_inliers`) |
| Approval expiry | A prepared action expires 30 minutes after it is proposed | `domain/actions.py` (`APPROVAL_TTL`) |
| Execution lease | A same-key retry may reconcile an `executing` row with no provider record after 2 minutes | `domain/actions.py` (`EXECUTION_LEASE`) |
| Stale approval | An approved action is rebuilt from current records before it runs; any change to amount, recipient, terms, animal, or evidence cancels it as `approval_stale` | `domain/actions.py` |

All thresholds are illustrative and camera-specific; none has been validated in the field.

## Pricing fiction

- Reference price: 5.20 USD/kg, source "Demo reference price (fictional)", dated 2026-10-01 (`herd.json`). Indicative value = weight range × price, so Sari's 480–560 kg is 2,496.00–2,912.00 USD.
- Cover is written up to the lower bound of the confirmed value range (`sample-v1 §1.2`).
- Premiums are an annual rate of the insured value: 3.50% (Basic Mortality), 5.20% (Mortality + Theft), 6.80% (Dairy Health Plus), rounded half up. Deductibles: 10% of insured value, a flat 150.00 USD, and 5% respectively.
- The illustrative payout `max(0, min(eligible_loss, remaining_limit) − deductible)` is defined only for Basic Mortality (`sample-v1 §5.1`). It is not a promise of payment.
- One currency (USD). The wallet is a sandbox ledger: a premium is held when its payment starts, debited when the sandbox payment provider confirms, and released if it fails.

## Live, prototype, simulated

| Output | Label | Notes |
| --- | --- | --- |
| Policy explanations and question parsing | `live` with an `ANTHROPIC_API_KEY`, otherwise "Template explanation (offline)" / "Parsed offline" | Claude only explains or parses; eligibility, prices, identity, and every answer's facts come from the records |
| Muzzle identity, weight | `prototype` when the ML extra (`uv sync --extra perception`) and model files are present, otherwise `simulated` fixtures | Per-capability fallback in `adapters/perception.py` |
| Age | `simulated` (fixture) or `documented` (from a birth date) | No age model |
| Camera tracks, movement alerts | `simulated` | Recorded synthetic scenarios replayed through the real association and movement rules |
| Veo barn tracks and footage | `simulated`, captioned "AI-generated footage (Veo) — not a real farm" | A real tracker's output on AI-generated video, replayed through the same rules |
| Insurer, payment provider, claim receipt | Sandbox | Sandbox Mutual and the sandbox payment provider; switches at `PUT /api/v1/demo/settings` |
| Seeded herd records | `simulated` / `documented` | From `herd.json` |

## Roles

- Only a manager approves or declines an action, confirms a claim declaration, or resets the demo.
- Only a vet adds a professional finding (assessment or health record), so it stays distinct from the farm's report and the cameras' observations.
