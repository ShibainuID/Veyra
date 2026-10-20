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

Use **Manager** or **Operator**. Vets can't open agent conversations (403).

1. **Expect:** a passport summary with "Not insured". The agent asks only questions whose answer is missing from the records, at most three. For Sari, the one question is whether you hold an ownership document; dairy breeds also get asked about a recent vet check. If you already uploaded the ownership PDF in step 4, it skips straight to the comparison.
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

## 8. Claim with the VEYRA agent: sick on camera, then death, then the muzzle re-scan

This is the full story: the CCTV recorded the sickness, the cow died, the muzzle re-scan confirms it's the right cow, and the agent files the claim. Do it for **Sari** after step 5 (insured) and step 6 (the reduced-movement replay gave her a camera alert).

Every sample plan requires a **linked camera observation**. Only Sari has one after step 6, so file the claim for her. Bima and Melati are insured but have no camera alert; see the negative test below.

Open `/agent?animal=animal-demo-001&intent=file_claim`, or **File a claim with the VEYRA agent** on Sari's passport. The Claims list has no agent button.

1. **Expect:** the agent checks Sari's active policy and its cover window, then asks what happened. Covered perils are highlighted.
2. Answer **Death**, the date (**today**, so it falls inside the cover window), a short description, and an estimated loss (e.g. `2400`). **Expect:** the incident is recorded, the claim is drafted, and Sari's reduced-movement alert is linked automatically as camera evidence.
3. **Expect:** a checklist with present and missing items, each missing one with its fix:
   - **Vet assessment:** switch to **Vet**, open the claim (`/claims/<id>`), and use **Add assessment**. Only a vet can add it.
   - **Farmer declaration:** as **Manager**, confirm it with the button in the chat or on the claim page.
   - **Identity verified** (death claims only): see step 9. For the quick path, use **Use the sample re-scan (demo)**.
4. Back in the agent, as Manager, click **Check again**. Once the checklist is complete, the agent prepares the claim submission by itself (pending approval). **Approve and stamp** it as Manager, then **Check status**. **Expect:** "Submitted — Pending assessment" with a sandbox `SBX-CLM-…` receipt.
5. **Track the claim** (`intent=track_claim`):
   - **Expect:** only insurer-reported status.
   - Use the demo insurer update (manager): under review, then approved with an insurer-stated amount. Disbursement shows as "scheduled by insurer" and is never shown as paid automatically.
6. **Negative test:** start a claim for **Bima** (`/agent?animal=animal-demo-002&intent=file_claim`, accidental injury). **Expect:** "Linked camera observation" stays **missing**, with a link to Monitor, and submission stays blocked. The agent never invents evidence.

## 9. Death claim: the real muzzle re-scan anti-fraud check

Instead of the sample re-scan in step 8.3, open the claim page (`/claims/<id>#verify-identity`):

1. Upload `demo/uploads/05_muzzle_closeup.jpg`, a different cow. **Expect:** **Mismatch**. Submission is blocked and the reason is kept.
2. Upload `demo/uploads/09_hp_muzzle.png`. **Expect:** **Match**, from the real muzzle model (hundreds of inliers). The identity item turns present.

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
| Camera replays | Recorded scenarios. The Veo footage is AI-generated and labeled so in the app (the pitch film shows it unlabeled) |
| Insurance and payments | A sandbox insurer and ledger: fictional policies, no real money |
| Language model | GPT-6 Luna only explains and parses; every decision and number comes from the records |
