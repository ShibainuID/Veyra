---
version: 1
slug: "apps-web-src-features-landing"
primary_target: "apps/web/src/features/landing"
related_targets: []
---

# VEYRA pitch landing page (apps/web, route "/")

## Scope and mode

The pitch landing page, in **Persuade** mode. It lives at `/` in apps/web, outside the app shell, and the herd dashboard moves to `/herd`. Code-led build.

## Audience, action, proof

- **Primary audience:** hackathon judges, who decide in minutes.
- **Secondary audiences:** farm managers, livestock insurers, and the vets between them.
- **Primary action:** "Open the live demo", which goes to `/herd`.
- **Secondary action:** follow the five-minute journey on the page.
- **Proof:** real material only.
  - The ML evaluation results: the muzzle hybrid is 92.5% correct at threshold with a 1.4% unknown-animal false match on held-out test animals; calf_detector_v1 + BoT-SORT re-ID gives recall 0.997 and MOTA 0.976 on the 8-Calves test video; the handoff_v2 policy produced zero wrong identities on 8-Calves but has no held-out estimate; weight error is 8.7% MAPE on the image path and 5.4% on the tape path across 71 cattle. Each figure is shown with its dataset and limits.
  - Real app screenshots.
  - Engineering facts: 462 backend tests and 108 web tests, the PRD critical-verification suite, sandbox-only money, and one Docker command.
- **Never invented:** customers, logos, market claims, or accuracy beyond these datasets.

## Direction contract

THESIS: One ear tag carries the pitch. Its face holds the hook, and as the visitor scrolls, the tag collects a stamp for each step VEYRA proves. This refuses the category's headline-over-cards hero and its row of identical feature tiles.

OWN-WORLD: The shipped Ear Tag world, unchanged. White ground, near-black ink, and a black nav bar. Tag yellow is a committed field: the tag owns half the first viewport and returns as the sticky companion. Stamps use the double-rule mono uppercase from the app: green means posted, ink means approved, and a dashed outline means not yet. Atkinson Hyperlegible Next for words, Mono for every figure. Real app screenshots sit in framed evidence panels.

STORY: Judges see the problem (four records in four places), then the journey on one cow (enroll, value, cover, watch, claim). They believe it because every claim carries its number, dataset, and limit, and because nothing financial moves without the manager's stamp. Then they open the live demo or run it with Docker. Managers, insurers, and vets each get one line on what changes for them.

FIRST VIEWPORT: A black nav holds the tag logo, How it works, Proof, Limits, Run it, and a yellow "Open the live demo" button. Left, a ~640px tag-yellow ear tag with a punched hole and the mono number 001, carrying the h1 "Know every animal. Protect every asset.", a sub-line, and an audience line. Right: the lead sentence about the agent and the stamp, the black/yellow "Open the live demo" button with "Watch the 5-minute journey" beside it, the sandbox note, and three stamps with real figures (identity, tracked, weighed), then a dashed "Next stamp: covered · awaiting you".

FORM: Dealt lead, structure #4 of 7 (the traveling tag). Signature interaction: below the hero the tag shrinks into a sticky companion in the left column. As each journey section enters, the tag receives that section's stamp with the app's press motion (Enrolled, Valued, Covered, Watched, Claimed). The final dashed slot, "Awaiting your stamp", is the demo button. Under reduced motion all stamps show statically. seed:d56b0ae9fabde72d

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance

## Unresolved

There is no footage of real cows and no partner logos. The screenshots show the app with simulated, labeled data.
