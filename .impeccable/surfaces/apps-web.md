---
version: 1
slug: "apps-web"
primary_target: "apps/web"
related_targets: []
---

# VEYRA web app (apps/web)

## Scope and mode

Whole product surface, **Operate** mode: herd dashboard, guided enrollment, passport, insurance comparison, monitor, alerts, approvals and wallet, claims, assistant, audit. Code-led build.

## Audience and job

A farm manager on a tablet in a bright barn aisle investigates one animal, checks its exposure, and approves or declines insurance actions. Operators enroll and locate cattle (no approval authority). Vets add assessment notes. Success: one traceable journey from enrollment to a sandbox claim, every line resolving to one animal ID.

## Constraints

Field-ready high contrast, large touch targets (44px minimum, 48px for primary). Light theme. Every adapter output carries a `live` / `prototype` / `simulated` chip. No footage is committed yet; media tiles need an explicit missing state. The user pinned this direction as a fusion: the Ear Tag world for the UI, and the Passbook Ledger's functions.

## Direction contract

THESIS: Every cow is its ear tag, and every tag keeps a passbook. Identity reads first as a tag-yellow chip with laser-black numerals. Everything that happens to the animal posts as a numbered, dated passbook line, and nothing financial posts without the manager's stamp. This refuses the category default of KPI tiles over a grey table with one blue accent.

OWN-WORLD: White ground, near-black ink, and a black shell bar. Tag yellow carries brand, the current nav item, and identity: a solid tag means confirmed, a dashed outline tag means pending review, and a grey "no tag" means an unassigned track. Primary actions are black buttons with tag-yellow labels. States: green for posted/active, red for failed/declined, orange for uncertain. Atkinson Hyperlegible Next, with Hyperlegible Mono for every figure, ID, and timestamp.

STORY: The manager sees which animals carry exposure without cover and which lines wait on them. They open a tag's passbook, read the evidence behind each line, and stamp or decline the waiting line. They trust it because uncertainty is always named.

FIRST VIEWPORT: The black top bar carries the tag logo, nav (Herd, Enroll, Monitor, Approvals with a count, Claims, Audit), and the role and sandbox balance on the right. Left: herd table, tag column first, 64px rows, filter chips above. Right (440px): the selected tag's passbook, with a big tag header, numbered lines, and a running balance column. The awaiting line is highlighted with a dashed stamp slot, the post-stamp balance, "Approve and stamp" in black and yellow, and Decline set apart.

FORM: Fusion of the user-pinned Ear Tag (my list #1) and Passbook Ledger (assigned #3). Signature move: the stamp posting onto its exact passbook line. Raises: registered evidence frames, herd and pen map sharing coordinates, isolated Decline, balance printed before stamping, one column grid, true-black figures. seed:aca42b866d406f96

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance

## Unresolved

Real enrollment and camera footage come from the ML team. Until then, media tiles render the labeled missing state.
