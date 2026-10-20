# VEYRA demo and test flow

A complete walkthrough from the landing page through every feature, in story order. Each step says where to click, what to upload, and what you should see. For the timed five-minute pitch version, see `docs/demo-script.md`.

Every file you upload is in `demo/uploads/` (see its README). Run `git lfs pull` once so the videos and images are real files, not LFS pointers.

## 0. Start

**Docker (one command):**

```bash
docker compose up --build          # http://localhost:8000
```

**Development (two terminals):**

```bash
cd services/api && uv sync && uv run uvicorn main:app --port 8000
pnpm -C apps/web install && pnpm -C apps/web dev      # http://localhost:5173
```

- **Language model:** put `OPENAI_API_KEY=` in the root `.env` to get live GPT-6 Luna explanations. Without it, everything still works and is labeled offline.
- **Fresh start:** use the manager-only Demo button (flask icon in the top bar, or More on a phone) and choose **Fresh herd**.
- **Roles:** the switcher in the top bar changes between Manager (approves), Operator (prepares, cannot approve), and Vet (assessments only).

## 1. Landing page: `/`

1. Read the hero: the ear tag with "Know every animal. Protect every asset." and the three proof stamps.
2. Scroll: the companion tag on the left collects five stamps (Enrolled, Valued, Covered, Watched, Claimed) as each step passes.
3. **Expect:** the proof table shows each figure with its dataset and limit, then the honest Limits section.
4. Click **Open the live demo**. It goes to `/herd`.

## 2. Herd: `/herd`

1. **Expect:** five seeded cattle (Bima, Melati, Gatot, Dewi, Rama) with exposure, coverage, health, and last observed.
2. Use the filter chips: Not covered, Open alerts, Awaiting approval.
3. Click a row. Its passbook opens on the right (a drawer on a tablet or phone).

## 3. Enroll a new cow with the phone video: `/enroll`

Upload: `demo/uploads/video_hp.mp4`. You can also pick **Use the phone enrollment video**, or **Use prepared demo sample**, then `sample-enrollment-001` for the fully seeded result.

1. **Capture:** on a phone or laptop with a camera, open **Record** to see the muzzle guide box and the live quality meter ("Hold steady · muzzle sharp enough"). For the test, **Upload a video** with `video_hp.mp4`.
2. **Processing:** the job runs. In fixture mode, frames are extracted with OpenCV; the muzzle crop goes through the real muzzle model.
3. **Review:**
   - **Expect:** three registered frames (muzzle, teeth, body), each with a provenance chip.
   - **Expect:** identity outcome **New**, because nothing on the farm matches.
   - **Expect:** honest review reasons. The video has no teeth view and no scale marker, so weight needs review.
4. **Confirm:** register as **Sari**, Bali cattle, female, and **enter a birth date**, e.g. 12/04/2024. Without one, age is unknown and Basic Mortality shows "needs review" instead of eligible. Missing views require a short override note.
   - **Raw video upload, no ML extras:** weight and age come back as "no range". The weight model needs `uv sync --extra perception`. In step 4, enter a weight range in the valuation calculator yourself, e.g. 480–560 kg.
   - **Fully seeded result (ranges included):** use **Use prepared demo sample**, then `sample-enrollment-001`. It gives 480–560 kg and 24–30 months.
5. **Expect:** "Sari is enrolled as animal-demo-001".
6. **Negative test:** enroll `sample-enrollment-dup`. It flags a possible duplicate of Bima, and registering it as new requires a reason. `sample-enrollment-unclear` stays "review required".

## 4. Passport: `/animals/animal-demo-001`

1. **Expect:** identity evidence (registered frames), age and weight ranges marked "Estimated, not guaranteed", and the passbook on the right.
2. **Valuation:** confirm one with the calculator (prefilled 5.20 USD/kg). **Expect:** a "Valued 2,496–2,912 USD" passbook line.
3. **Documents:** upload `demo/uploads/sari-ownership-sample.pdf` as **Ownership**. **Expect:** a "Document on file · Ownership" passbook line.
4. **Location:** shows "last observed" with camera and time, plus the **camera gallery** status. Click **Push to cameras** (manager): the pen cameras sync the enrolled herd (simulated acknowledgements).

## 5. Get insurance with the VEYRA agent: `/agent?animal=animal-demo-001&intent=find_insurance`

Open it from **Find insurance with the VEYRA agent** on the passport.

1. **Expect:** the agent notices "Not insured" and asks only what's missing, for example the cover start date.
2. **Expect:** the plan comparison card:
   - Basic Mortality & Accident: eligible;
   - Mortality + Theft: eligible once the ownership document is on file, otherwise needs review;
   - Dairy Health Plus: not eligible (dairy breeds only).
3. The agent recommends a plan with reasons and terms references.
4. **Prepare application.** **Expect:** an auto-filled application and evidence checklist.
5. **Approve and stamp:**
   - as **Operator** first: **expect** "Only a manager can approve";
   - then as **Manager**: the stamp presses onto the line.
6. Prepare and approve the **premium payment**. **Expect:** three distinct states, Submitted, then Payment recorded (sandbox), then Coverage confirmed by the insurer with an effective date.
7. **Same flow without the agent:** Passport, then **Compare coverage** (`/animals/animal-demo-001/insurance`), then Approvals (`/approvals`). The wallet ledger shows the hold and debit.
8. **Failure tests:** Demo settings: payment **fail** shows "Not charged". **timeout** gives unknown, then **Check again** reconciles with the same key. Insurer **withhold** keeps the policy paid but not active until **Check activation**.

## 6. Monitor and alerts: `/monitor`

1. **Reduced-movement replay:**
   - Sari is identified in the **scan zone** ("Identified in scan zone · N points").
   - Her track keeps that identity only while it stays continuous.
   - After about 15 s at 10× speed: **expect** an alert, "Movement … below this animal's earlier window … not a diagnosis".
2. Open the alert drawer:
   - acknowledge it as Operator;
   - add an assessment note as Vet;
   - resolve it, which needs a note.
3. **Veo barn replay:**
   - **Expect:** the CCTV video plays under the live overlay, and the scan-zone outline is drawn.
   - **Expect:** no identity is invented, because the scanned heifer isn't on this farm.
4. **Crowded scan:** two cows in the zone during the scan. **Expect:** "2 animals in zone — not identified".
5. **Lost identity:** a track switch leaves the new track **unassigned**. It never inherits a passport.

## 7. Ask: top-bar **Ask**

1. "Where was Sari last seen, and what coverage is active?" **Expect:** the camera, a past time (local zone), and the active cover.
2. "Show me animal-demo-002", then "Which animals have open alerts?"
3. "Where is Dewi?" **Expect:** "No camera observation is on record" and a recovery hint.

## 8. Claim for an already-insured cow with the VEYRA agent

Open `/agent?animal=animal-demo-002&intent=file_claim`, or **File a claim with the VEYRA agent** on Bima's passport.

1. Tell the agent what happened: an accidental injury, the date, and a short description. You can attach `demo/uploads/incident-photo.jpg`.
2. **Expect:** a checklist of present and missing items, with **vet assessment missing**, so submission is blocked.
3. Switch to **Vet**, open the claim (`/claims/<id>`), and **Add assessment**.
4. Switch to **Manager** and confirm the **declaration**.
5. Back in the agent: **Prepare claim submission**, then **Approve and stamp**. **Expect:** "Submitted — Pending assessment" with a sandbox receipt.
6. **Track the claim** (`intent=track_claim`):
   - **Expect:** only insurer-reported status.
   - Use the demo insurer update (manager): under review, then approved with an insurer-stated amount. Disbursement shows as "scheduled by insurer" and is never shown as paid automatically.

## 9. Death claim: the muzzle re-scan anti-fraud check

1. First make sure Sari has active cover (step 5).
2. Record a **death** incident for Sari (Claims, then Record incident, then **Use the sample death**), then draft the claim.
3. **Verify identity:**
   - Upload `demo/uploads/09_hp_muzzle.png`. **Expect:** **Match**, from the real muzzle model.
   - Upload `demo/uploads/05_muzzle_closeup.jpg`, which is a different cow. **Expect:** **Mismatch**, and submission is blocked with the reason kept.

## 10. Audit: `/audit`

1. Filter by animal **Sari**.
2. **Expect:** agent proposals, human decisions, and provider results as separate rows, each with its own actor badge.

## 11. Optional API checks

- `GET /api/v1/health`: `llm.mode` is `live` when the key is set, along with provider and model, plus perception capabilities.
- `GET /api/v1/cameras/cam-pen-a/gallery` with header `X-Service-Token: demo-worker-token`: the gallery a camera would fetch.
- Swagger UI: `http://localhost:8000/docs`.

## What is real, what is simulated

| Area | Status |
| --- | --- |
| Muzzle matching | The real ONNX model with SIFT verification |
| Enrollment frames | Real OpenCV extraction. Weight and age use labeled fixtures unless the perception extra is installed |
| Camera replays | Recorded scenarios. The Veo footage is AI-generated and labeled so in the app |
| Insurance and payments | A sandbox insurer and ledger: fictional policies, no real money |
| Language model | GPT-6 Luna only explains and parses; every decision and number comes from the records |
