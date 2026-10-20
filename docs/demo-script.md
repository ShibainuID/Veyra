# Five-minute demo script

One continuous journey from a fresh herd to a sandbox claim, following PRD section 8 ("Five-minute demonstration"). Clicks are in **bold**; the line in quotes is what to say. Rehearsed timings are for clicking and talking; the app itself needs about 25 seconds for the whole path, most of it the camera replay.

## Before you start

1. Start the API and the web app (see the README quick start). Leave `VEYRA_REPLAY_SPEED` at its default of 10, so the replay raises its alert about 15 seconds after it starts.
2. Open `http://localhost:5173/herd` at 1440 wide (a laptop at 100% zoom), acting as **Manager**. (`/` is the pitch page; its **Open the live demo** button opens the herd too.)
3. Reset: as Manager, **flask button (Demo)** in the top bar → **Fresh herd** → **Reset demo…** → **Reset the demo**. From a terminal instead:

   ```bash
   curl -X POST "http://localhost:8000/api/v1/demo/reset?scenario=fresh" -H "Authorization: Bearer demo-manager"
   ```

4. Make sure no earlier replay is selected on Monitor: the reset clears it.

## 1. Herd (0:00–0:40)

- Show the **Herd**: five tags, exposure, cover, last sighting, alerts. Point at "3 uncovered" and Gatot's **Quality** alert.
- Say: "Identity, health observations, and insurance usually sit in separate systems. Here every row is one ear tag, and the panel on the right is that animal's passbook."

## 2. Enroll Sari and value her (0:40–1:30)

- **Enroll** → under "Use prepared demo sample", **Use sample** on "Sari · guided video".
- Review: three registered views, checks, and "No match on the farm" (closest Rama, 3 verified points, below the 5 needed). Say: "One continuous video gives the muzzle, teeth, and body. The matcher found no existing animal, so this is a new identity, and a person confirms it."
- **Register as a new animal** → **Register Sari**. She is now `animal-demo-001`.
- **Confirm valuation** (opens the passport at the valuation) → **Confirm valuation**.
- Say: "The value is a range: 480 to 560 kg times a dated reference price of 5.20 USD per kg, labeled simulated, confirmed by the manager."

## 3. Coverage, application, premium (1:30–2:20)

- **Compare coverage**. Say: "Three sample products: Basic Mortality is eligible, Mortality + Theft needs an ownership document, Dairy Health Plus is ineligible because Sari is a beef breed, with the terms reference for each."
- **Prepare application** → **Review the application** → **Approve and stamp**. Say: "The agent prepared it; nothing goes out until I stamp it."
- **Next: prepare the premium payment** → **Prepare premium payment** → **Review the payment**. Point at "Sandbox balance after". **Approve and stamp**.
- The green box reads "Cover active · a separate insurer confirmation". Say: "The payment posted, but cover starts only when the insurer confirms it, and that is its own record." **See the cover** shows Active with the insurer's reference and the cover period.

## 4. Monitor and ask (2:20–3:15)

- **Monitor** → **Reduced-movement replay** → **Start replay**. Say: "A recorded camera scene. Each track is identified by muzzle only when the match is good enough."
- About 15 s later a toast says "New alert · Sari · Reduced movement" and the alert tops the **Alert feed**. Open it: observation window, the baseline window, the bars (79% below baseline), and the clip reference. Say: "This asks for an inspection. It is not a diagnosis."
- Close the drawer, **Ask** in the top bar → **Where was animal-demo-001 last seen, and what coverage is active?** The answer names Pen A · feed line, the local time, and the active Basic Mortality cover, each a link to its record.

## 5. Incident and claim (3:15–4:30)

- Open the alert again from the **Alert feed** → **Record incident**. **Use the sample incident** → **Record incident and draft claim**.
- The claim opens with "2 of 6 requirements are missing". **Prepare claim submission**: the agent refuses and names what is missing. Say: "An alert alone can't make a claim, and a claim can't go out incomplete."
- Tick **I confirm these incident facts are accurate**.
- Role switcher → **Vet**. Under "Professional", write the finding (for example "Examined on site. Soft-tissue injury of the left hind leg, no fracture.") → **Add assessment**. "Every requirement is on file."
- Role switcher → **Manager** → **Prepare claim submission** → **Approve and stamp**. The receipt shows "Assessment pending". Say: "Submitted to the sandbox insurer. Submission is not acceptance or payout."

## 6. A declined action, the audit, the labels (4:30–5:00)

- On the same claim, **Notify insurer about this alert** → **Review it** → **Decline** → **Decline** (optionally type a reason first). "Nothing was sent to Sandbox Mutual."
- **Audit**: agent proposals, the manager's decisions, and the providers' results are separate rows, each tied to `animal-demo-001`.
- Point at the `simulated` chips, "Template explanation (offline)", and "Sandbox · no real funds".

## Extra beats (if time allows)

- **Right cow at claim:** record a second incident with **Use the sample death** → on its claim, **Verify identity** → **Use sample: wrong cow** (Mismatch, submission blocked) → **Use sample: matching scan** (Match, the checklist item turns present); with the muzzle model installed, upload a muzzle photo instead for a `prototype` result.
- **Cameras learn the herd:** on Sari's passport, **Location → Camera gallery** names which pen cameras hold the current gallery version; as Manager, **Push to cameras** publishes it and the cameras' acknowledgements arrive, labeled `simulated`.

## Fallbacks

| If | Do |
| --- | --- |
| The camera or a video file isn't available | Use the prepared sample (step 2). It is the scripted path; it needs no camera. |
| The language model is offline or no key is set | Nothing to do: explanations read "Template explanation (offline)" and the assistant answers from records with the offline parser. |
| Enrollment goes wrong or time is short | Reset to **After enrollment** (Demo → After enrollment) and start at step 3: Sari is enrolled and valued. |
| The replay alert doesn't appear | Wait for "Replay finished"; if there is still no alert, **Start again**. The alert also appears on Sari's passport and in the herd. |
| A stamp fails with "records changed" | The approval went stale because a record changed. The screen says so; prepare it again and stamp the new version. |
| You need to show the uncertain identity path | Enroll → **Use sample** on "Duplicate check · Bima again": a possible duplicate the operator must link or justify. "Unclear muzzle · retry needed" shows the retry state. |
| You want to show a failed payment | `PUT /api/v1/demo/settings` with `{"payment_mode": "fail", "insurer_activation": "confirm"}` before the premium payment, then set it back to `succeed`. |
| Operator approval check | Switch to **Operator** on Approvals: "Only a manager can approve." |
