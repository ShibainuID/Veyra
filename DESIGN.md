---
name: VEYRA
description: Every cow is its ear tag, and every tag keeps a passbook.
colors:
  bg: "oklch(1 0 0)"
  ink: "oklch(0.18 0.005 260)"
  muted: "oklch(0.42 0.01 260)"
  line: "oklch(0.82 0.006 260)"
  line-strong: "oklch(0.6 0.01 260)"
  surface: "oklch(0.975 0.002 260)"
  surface-2: "oklch(0.95 0.003 260)"
  shell: "oklch(0.17 0 0)"
  shell-2: "oklch(0.27 0 0)"
  on-shell: "oklch(1 0 0)"
  on-shell-muted: "oklch(0.82 0 0)"
  shell-line: "oklch(0.36 0 0)"
  tag: "oklch(0.86 0.17 92)"
  tag-pressed: "oklch(0.8 0.16 88)"
  tag-edge: "oklch(0.6 0.12 80)"
  tag-soft: "oklch(0.97 0.06 95)"
  await-ink: "oklch(0.42 0.09 75)"
  ok: "oklch(0.47 0.12 155)"
  ok-soft: "oklch(0.95 0.04 155)"
  danger: "oklch(0.5 0.19 28)"
  danger-soft: "oklch(0.95 0.03 25)"
  danger-pressed: "oklch(0.42 0.17 28)"
  uncertain: "oklch(0.56 0.15 50)"
  uncertain-ink: "oklch(0.48 0.13 50)"
  uncertain-soft: "oklch(0.95 0.04 65)"
typography:
  display:
    fontFamily: "Atkinson Hyperlegible Next Variable, Atkinson Hyperlegible Next, system-ui, sans-serif"
    fontSize: "clamp(2.5rem, 1rem + 4.4vw, 4.75rem)"
    fontWeight: 800
    lineHeight: 0.98
    letterSpacing: "-0.03em"
  pitch-heading:
    fontFamily: "Atkinson Hyperlegible Next Variable, Atkinson Hyperlegible Next, system-ui, sans-serif"
    fontSize: "2.203rem"
    fontWeight: 800
    lineHeight: 1.1
  lead:
    fontFamily: "Atkinson Hyperlegible Next Variable, Atkinson Hyperlegible Next, system-ui, sans-serif"
    fontSize: "1.375rem"
    fontWeight: 400
    lineHeight: 1.45
  headline:
    fontFamily: "Atkinson Hyperlegible Next Variable, Atkinson Hyperlegible Next, system-ui, sans-serif"
    fontSize: "1.836rem"
    fontWeight: 700
    lineHeight: 1.15
    letterSpacing: "-0.01em"
  title:
    fontFamily: "Atkinson Hyperlegible Next Variable, Atkinson Hyperlegible Next, system-ui, sans-serif"
    fontSize: "1.53rem"
    fontWeight: 700
    lineHeight: 1.25
    letterSpacing: "-0.01em"
  title-sm:
    fontFamily: "Atkinson Hyperlegible Next Variable, Atkinson Hyperlegible Next, system-ui, sans-serif"
    fontSize: "1.275rem"
    fontWeight: 700
    lineHeight: 1.35
  body:
    fontFamily: "Atkinson Hyperlegible Next Variable, Atkinson Hyperlegible Next, system-ui, sans-serif"
    fontSize: "1.0625rem"
    fontWeight: 400
    lineHeight: 1.5
  label:
    fontFamily: "Atkinson Hyperlegible Next Variable, Atkinson Hyperlegible Next, system-ui, sans-serif"
    fontSize: "0.875rem"
    fontWeight: 700
    lineHeight: 1.4
  figures:
    fontFamily: "Atkinson Hyperlegible Mono Variable, Atkinson Hyperlegible Mono, ui-monospace, monospace"
    fontSize: "1.0625rem"
    fontWeight: 400
    lineHeight: 1.5
    fontFeature: "\"tnum\" 1, \"zero\" 1"
  stamp:
    fontFamily: "Atkinson Hyperlegible Mono Variable, Atkinson Hyperlegible Mono, ui-monospace, monospace"
    fontSize: "0.8125rem"
    fontWeight: 700
    lineHeight: 1.25
    letterSpacing: "0.06em"
  tag-number:
    fontFamily: "Atkinson Hyperlegible Mono Variable, Atkinson Hyperlegible Mono, ui-monospace, monospace"
    fontSize: "2.5rem"
    fontWeight: 700
    lineHeight: 1
    letterSpacing: "0.02em"
rounded:
  stamp: "4px"
  control: "10px"
  panel: "14px"
  pill: "999px"
  hero-tag: "11% 11% 18% 18% / 10% 10% 16% 16%"
spacing:
  "1": "4px"
  "2": "8px"
  "3": "12px"
  "4": "16px"
  "6": "24px"
  "8": "32px"
  "12": "48px"
  "16": "64px"
components:
  button-primary:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.tag}"
    typography: "{typography.body}"
    rounded: "{rounded.control}"
    padding: "0 20px"
    height: "48px"
  button-primary-hover:
    backgroundColor: "{colors.shell-2}"
    textColor: "{colors.tag}"
  button-decision:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.tag}"
    rounded: "{rounded.control}"
    padding: "0 20px"
    height: "52px"
  button-secondary:
    backgroundColor: "{colors.bg}"
    textColor: "{colors.ink}"
    rounded: "{rounded.control}"
    padding: "0 16px"
    height: "44px"
  button-secondary-hover:
    backgroundColor: "{colors.surface-2}"
  button-danger:
    backgroundColor: "{colors.bg}"
    textColor: "{colors.danger}"
    rounded: "{rounded.control}"
    padding: "0 16px"
    height: "44px"
  button-danger-hover:
    backgroundColor: "{colors.danger-soft}"
  button-ghost:
    textColor: "{colors.ink}"
    rounded: "{rounded.control}"
    padding: "0 12px"
    height: "44px"
  chip-filter:
    backgroundColor: "{colors.bg}"
    textColor: "{colors.ink}"
    rounded: "{rounded.control}"
    padding: "0 16px"
    height: "44px"
  chip-filter-pressed:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.bg}"
  status-pill-ok:
    backgroundColor: "{colors.ok-soft}"
    textColor: "{colors.ok}"
    typography: "{typography.label}"
    rounded: "{rounded.pill}"
    padding: "0 12px"
    height: "32px"
  status-pill-awaiting:
    backgroundColor: "{colors.tag-soft}"
    textColor: "{colors.await-ink}"
    rounded: "{rounded.pill}"
    height: "32px"
  input-field:
    backgroundColor: "{colors.bg}"
    textColor: "{colors.ink}"
    rounded: "{rounded.control}"
    padding: "8px 12px"
    height: "44px"
  nav-item-active:
    backgroundColor: "{colors.tag}"
    textColor: "{colors.ink}"
    rounded: "{rounded.control}"
    height: "48px"
  stamp:
    backgroundColor: "{colors.bg}"
    textColor: "{colors.ink}"
    typography: "{typography.stamp}"
    rounded: "{rounded.stamp}"
    padding: "3px 9px"
  passbook-line-awaiting:
    backgroundColor: "{colors.tag-soft}"
    rounded: "{rounded.control}"
    padding: "16px"
  data-table-row:
    height: "64px"
    padding: "8px 12px"
  button-pitch:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.tag}"
    rounded: "{rounded.control}"
    padding: "0 24px"
    height: "60px"
  nav-cta-shell:
    backgroundColor: "{colors.tag}"
    textColor: "{colors.ink}"
    rounded: "{rounded.control}"
    padding: "0 20px"
    height: "44px"
  nav-cta-shell-hover:
    backgroundColor: "{colors.tag-pressed}"
  hero-tag:
    backgroundColor: "{colors.tag}"
    textColor: "{colors.ink}"
    typography: "{typography.display}"
    rounded: "{rounded.hero-tag}"
    padding: "150px 56px 56px"
  companion-tag:
    backgroundColor: "{colors.tag}"
    textColor: "{colors.ink}"
    rounded: "{rounded.hero-tag}"
    padding: "80px 20px 32px"
    width: "384px"
  evidence-mount:
    backgroundColor: "{colors.surface-2}"
    rounded: "{rounded.control}"
    padding: "20px"
---

# Design System: VEYRA

## Overview

**Creative North Star: "The Ear Tag and Its Passbook"**

VEYRA is a field instrument for a farm manager on a tablet in a bright barn aisle. Identity reads first: every animal is a tag-yellow ear tag printed with laser-black numerals, and everything that happens to that animal posts as a numbered, dated passbook line. Nothing financial posts without the manager's stamp, and the stamp is the one moment of motion the world dramatizes: it lands on its exact line.

The ground is white paper with near-black ink, framed by a black shell bar above (and black bottom tabs on smaller screens). Tag yellow is scarce and meaningful: brand, the current place, identity, and the line that waits on the manager. The rest of the color is state, always paired with an icon and a word. Density is ledger-like rather than dashboard-like: 64px table rows, figures in a monospace with tabular, slashed-zero numerals, and heavy ink rules that read like a register's printed lines. The system refuses KPI tiles over a grey table with one blue accent.

Light only. High contrast is a field requirement, not a style: every pairing in the token file is computed to WCAG and the smallest ratio for text is 4.9:1.

The same world has one Persuade surface: the pitch page at `/`, outside the app shell. It changes scale, not materials. One ear tag grows to half the first viewport and carries the h1, then travels beside the story as a sticky companion that collects a stamp per journey step; app screenshots sit on registered evidence mounts; lists stay ledgers with ink rules, never card grids. Tag yellow there is brand and identity at page scale (the hero tag, the companion, the closing "Run it" field), still carrying only ink. The display, lead, and heavy-weight extensions below belong to that surface alone; every Operate screen keeps the fixed ramp.

**Key Characteristics:**
- Ear tag as identity: solid yellow is confirmed, dashed ink outline is pending review, grey "no tag" is an unassigned track.
- Passbook as history: numbered, dated lines with a running amount column; the awaiting line is a yellow-soft slot with a dashed stamp outline.
- Black primary buttons with tag-yellow labels; Decline stands apart in red outline.
- Atkinson Hyperlegible Next for words, Atkinson Hyperlegible Mono for every figure, ID, and timestamp.
- Heavy 2-3px ink rules as structure; shadows only for floating layers.
- Large touch targets: 44px minimum, 48px primary, 52px for the passbook decision.
- On the pitch surface only: one page-scale traveling ear tag, a fluid display headline, and evidence mounts for real screenshots.

## Colors

A white-and-ink ledger with one loud identity color and three plain state colors.

### Primary
- **Tag Yellow** (tag): the molded livestock tag. Fills confirmed ear tags, the current nav item, the approvals count badge, text selection, the skip link, and the label of every primary button. It only ever carries ink on it (12.3:1), never white.
- **Pressed Tag** (tag-pressed): the darker yellow for a pressed tag-filled surface.
- **Tag Edge** (tag-edge): the molded rim; outlines confirmed tags, borders the awaiting passbook line and the awaiting pill (4.0:1 on white, non-text only).
- **Tag Wash** (tag-soft): the background of anything awaiting the manager: the awaiting passbook line, the awaiting status pill.
- **Awaiting Ink** (await-ink): text and dashed stamp-slot outline on Tag Wash (7.9:1).

### Secondary
- **Posted Green** (ok) on **Green Wash** (ok-soft): posted, active, confirmed, live. The live provenance chip is solid green with white text.
- **Declined Red** (danger) on **Red Wash** (danger-soft), deepening to **Pressed Red** (danger-pressed): failed, declined, not covered, uninsured exposure figures, the Decline button.

### Tertiary
- **Uncertain Orange** (uncertain) for icons and borders, **Uncertain Ink** (uncertain-ink) for text, on **Orange Wash** (uncertain-soft): outcome unknown, quality warnings, expired stamp slots, and errors that need a decision rather than a retry.

### Neutral
- **Paper White** (bg): the page and every panel.
- **Laser Ink** (ink): body text, heavy rules, primary button fill, focus ring.
- **Pencil Grey** (muted): secondary text, column headers, meta lines (8.5:1).
- **Ruled Line** (line): 1px row dividers and fact dividers.
- **Strong Rule** (line-strong): 2px control borders, dashed empty slots, scrollbar thumb.
- **Tint** (surface) and **Tint 2** (surface-2): row hover and selected row, hover fill on outline controls, skeletons, the "no tag" fill.
- **Shell Black** (shell), **Shell Raised** (shell-2), **Shell Rule** (shell-line), with **On-Shell** white and **On-Shell Muted**: the top bar, bottom tabs, and the phone's More sheet. Focus on the shell turns tag yellow.

### Named Rules
**The Tag Carries Ink Rule.** Tag yellow appears only for brand, the current place, identity, and awaiting; anything set on it is Laser Ink. A yellow surface that means none of those is a bug.

**The Never Color Alone Rule.** Every state is icon plus word plus color (status pills, provenance chips, error notices, stamps). Remove the color and the meaning must survive.

**The Provenance Rule.** Every adapter figure carries a visible source chip beside it: live (solid green), prototype (ink outline), simulated (dashed grey outline), documented (grey fill). Never hover-only.

## Typography

**Body Font:** Atkinson Hyperlegible Next Variable (with system-ui, sans-serif)
**Label/Mono Font:** Atkinson Hyperlegible Mono Variable (with ui-monospace, monospace)

**Character:** One legibility-first family in two voices. Words are set in the sans; anything a person might read back aloud as a number (tag numbers, animal IDs, money, weights, times, line numbers, codes) is set in the mono with tabular, slashed-zero numerals, so columns align and 0 never reads as O.

### Hierarchy
- **Headline** (700, 29.4px, 1.15): the page h1 and the passbook animal name. No kicker above it.
- **Title** (700, 24.5px, 1.25): section h2s, with 48px above and 16px below.
- **Title Small** (700, 20.4px, 1.35): sub-sections, empty-state headings, the "Passbook" heading, the balance-after figure.
- **Body** (400, 17px, 1.5): everything else. Prose caps at 62-70ch.
- **Label** (700, 14px, 1.4): column headers, fact labels (400 there), status pills, provenance chips.
- **Stamp** (mono 700, 13px, 0.06em, uppercase): stamps and the awaiting stamp slot only. 13px is reserved for these and dense mono; nothing else goes below 14px.
- **Tag Number** (mono 700, 17 / 24 / 40px for the sm / md / xl tag): printed on the ear tag.

The scale is fixed rem at a 1.2 ratio from a 17px base. Headings balance-wrap and tighten to -0.01em; paragraphs pretty-wrap.

### Pitch extension (Persuade surface only)
- **Display** (800, clamp 40-76px, 0.98, -0.03em): the pitch h1, set on the hero ear tag. One per page. The only fluid size in the system.
- **Pitch Heading** (800, 35.2px, 1.1): pitch section h2s, from the ramp's 2xl step at heavy weight.
- **Lead** (400, 22px, 1.45): the pitch lead sentence beside the hero tag and in "Run it", capped at 30-36ch; below 640px it drops to the 20.4px title-small size.
- **Heavy** (800) is reserved for the display headline, pitch headings, pitch buttons, the nav CTA, and the wordmark. Operate screens top out at 700.

### Named Rules
**The Fixed Ramp Rule.** Operate screens use the fixed rem ramp only. Display, lead, and the 800 weight are pitch tokens; bringing them into the app is a system change, not an extension.

**The Figures Are Mono Rule.** Every figure, ID, and timestamp uses the mono with tabular, slashed-zero numerals. Money keeps its number unbroken and may break only before the currency code.

**The Uppercase Belongs To The Stamp Rule.** Uppercase tracked text exists only on stamps and stamp slots, where it is the register's own voice. Headings and labels stay sentence case.

## Layout

A one-column page beside a 440px passbook. On wide screens the herd and passport put the content column left and the selected tag's passbook right, as a sticky full-height panel under the shell, divided by a 2px ink rule. Below 900px (the `tab` breakpoint) the passbook stacks under the content and its decision bar becomes sticky to the bottom.

The shell is 72px tall from 1024px up, carrying the logo, the full nav, Ask, the sandbox wallet, and the role switcher. Below 1024px the bar shrinks to 64px and navigation moves to 56px black bottom tabs (five tabs plus More, which opens a black bottom sheet). Page gutters are 16px, 24px from 640px, and 32px on wide passport layouts; the passport caps at 1600px.

Spacing is a 4px-based scale (4, 8, 12, 16, 24, 32, 48, 64). Sections sit 48px apart; heading groups are 16px above their content; page headers leave 24px below. Breakpoints: 640, 720 (tables stack), 900 (passbook decision bar sticky), 1024 (full top bar), 1280.

Touch targets are tokens, not suggestions: 44px minimum for every control, 48px for primary buttons and nav, 52px for Approve and Decline.

The pitch page has its own black nav bar (64px, 72px from 1024px, no bottom tabs) and caps at 1440px. From 1024px the hero splits 10fr:9fr (tag left; lead, CTAs, and measured stamps right) and the body becomes a 384px companion column beside the sections, which sit 96px apart (64px below 1024px). Below 1024px the companion column is hidden, each journey step carries its own stamp inline, and the hero CTAs move above the case; below 640px they go full width.

## Elevation & Depth

Flat by default. Structure comes from ink rules, not shadows: a 3px ink rule under table headers, 2px ink rules around the exposure summary, above decision bars, and between the content and the passbook panel. Shadows are soft (offset plus blur, never a hard block) and only for things that float over the page.

### Shadow Vocabulary
- **Raised** (`0 1px 2px oklch(0.18 0.005 260 / 0.08), 0 4px 12px oklch(0.18 0.005 260 / 0.08)`): toasts.
- **Drawer** (`-8px 0 32px oklch(0.18 0.005 260 / 0.18)`): the right-hand drawer, over a 50% shell-black backdrop.
- **Sheet** (`0 -8px 32px oklch(0.17 0 0 / 0.3)`): the phone's More sheet.
- **Sticky bar** (`0 -8px 16px -8px oklch(0.18 0.005 260 / 0.18)`): an upward edge under bottom-sticky decision bars, only while they float over scrolling content.
- **Press** (`0 6px 14px oklch(0.18 0.005 260 / 0.22)` to none): the stamp's lift during its 180ms landing; it ends flat.

### Named Rules
**The Rules Not Shadows Rule.** Group and separate with ink rules and whitespace. A shadow means the surface floats; nothing at rest gets one.

## Shapes

Two corner radii carry nearly everything: gently rounded controls (10px) for buttons, chips, inputs, nav items, the awaiting line, and evidence frames; softer panels (14px) for cards, empty states, toasts, the recorder, and the sheet's top corners. Pills (999px) are reserved for status pills, provenance chips, and count badges. Stamps and stamp slots use a tight 4px, a printed-ink corner.

Borders are thick and deliberate: 2px on every control, chip, card, and notice; 4px double rule on stamps; dashed for anything not yet real (pending tags at 6/4, stamp slots, empty states, simulated provenance, missing evidence). The ear tag silhouette (a 112:80 molded tag with a punched hole and rounded bottom corners) is the one custom shape and is drawn as SVG at component sizes (40, 56, 96px), never approximated with a rounded rectangle.

The one exception is the pitch page's page-scale tag, which must hold flowing text: a tag-yellow box with a 3px tag-edge rim and elliptical radii proportional to its own size, rounded shoulders and a heavier rounded bottom (hero-tag), with the punched hole drawn as a white disc in an 8-10px tag-edge ring at top center and the mono number top right. It is used only for the hero tag and its companion.

### Named Rules
**The Dashed Means Not Yet Rule.** A dashed outline marks something pending, waiting, simulated, or missing. Solid means real and confirmed. Do not use dashes decoratively.

## Components

### Buttons
Heavy, square-shouldered, and unmistakable.
- **Shape:** gently rounded (10px), 2px border, bold label, 20px Lucide icon at 2.25 stroke.
- **Primary:** ink fill with a tag-yellow label, 48px tall, 20px side padding. One primary per decision area.
- **Decision:** the passbook's "Approve and stamp", 52px, with a stamp icon. Decline is the danger variant set 32px beside it (24px below on a phone), never adjacent.
- **Secondary:** white with a 2px ink border, 44px. **Danger:** white with a 2px red border and red label. **Ghost:** borderless, 44px. **Shell:** white label with a shell-rule border on the black bar.
- **Hover / Active:** primary goes to shell-raised; outline variants fill with tint 2; press nudges down 1px. 160ms quart-out.
- **Loading:** keeps the variant's colors, swaps in a spinner and a verb ("Approving…"); disabled turns grey (tint 2 fill, muted text).
- **Focus:** a 3px ink outline offset 2px everywhere; tag yellow on the shell.

### Chips
- **Filter chips:** 44px, 10px corners, 2px ink border, bold label with a mono count. Pressed fills ink with white text and adds a check icon, so the state reads without color.
- **Status pills:** 32px pill, soft wash with its state ink, icon plus label (ok, danger, uncertain, neutral, awaiting).
- **Provenance chips:** 28px pill naming live / prototype / simulated / documented, always beside its figure.

### Cards / Containers
- **Corner Style:** 14px.
- **Background:** white; containers are defined by a 2px border (ink for content, dashed strong rule for empty).
- **Shadow Strategy:** none at rest (see Elevation).
- **Internal Padding:** 20px; empty states 32px vertical.

### Inputs / Fields
- **Style:** white, 2px strong-rule border, 10px corners, 44-48px tall, 12px side padding, bold labels at 14px above.
- **Focus:** the border turns ink, plus the global 3px focus outline. Radios and checkboxes use ink as their accent at 20px.
- **Error / Disabled:** errors show as an Error Notice; disabled fields take the tint fill and muted text.

### Navigation
- **Top bar:** black, sticky, 72px. Bold white nav links in 48px pills of 10px radius; the current page is tag yellow with ink text; hover is shell-raised. The approvals count is a yellow mono badge (ink with yellow when its tab is current).
- **Bottom tabs:** 56px black bar, five icon-over-label tabs plus More, with the same yellow current state.

### Ear Tag (signature)
The animal's identity, drawn as an SVG molded tag at 40, 56, or 96px tall with the number in bold mono. Confirmed: yellow fill, tag-edge rim. Pending: white fill, 2.5px dashed ink outline. None: tint-2 fill, strong-rule rim, "no tag" in muted sans. It leads every table row and the passbook header.

### Passbook Line (signature)
A three-column grid: a 60px mono gutter (bold line number over date and time), the entry, and a right-aligned mono amount. Lines divide with 1px rules. The awaiting line becomes a tag-wash slot with a 2px tag-edge border and a dashed await-ink stamp slot ("AWAITING STAMP · EXPIRES 29:57"); void lines strike through 2px in muted. Below the list, the decision bar prints the balance after the line before the buttons.

### Stamp (signature)
A crisp 4px double-ruled stamp in uppercase mono: "APPROVED · 20 OCT 08:31 · W.S.". Ink by default, green when posted, red when declined or failed, uncertain-ink when the outcome is unknown. Never rotated, never textured: it reads like a register entry. When a line moves from awaiting to posted it presses once: from 1.06 scale and 35% opacity with a lift shadow to flat, 180ms quart-out, skipped under reduced motion.

### Data Table
Tag column first, 64px rows, 3px ink rule under 44px muted bold headers, 1px rules between rows. Whole rows are links (hover tint, selected tint 2, focus as a 3px inset ink ring); sort buttons are 44px. Below 720px of container width (544px for tables that drop columns first) rows stack: the tag leads on the left and each value labels itself.

### Evidence Frame
A 4:3 frame with 10px corners and four drawn registration corner brackets, so every view sits in the same frame. Missing footage shows the tint fill, a 2px dashed strong-rule outline, and a plain label.

### Evidence Mount (pitch)
The Evidence Frame turned into a mount for real app screenshots. The capture keeps its own proportions (no fixed 4:3), sits 20px inside a tint-2 mount with a 2px inset ink outline, and the four registration marks print in ink on the mount, 3px from its corners, never over the screenshot. The image takes a 1px ruled outline. Phone widths get a purpose-cut crop through `<picture>` below 640px, not a scaled-down desktop capture. The caption row names the view in bold and, on the right, "App screenshot, demo data" with a simulated provenance chip.

### Traveling Tag (pitch signature)
One ear tag that carries the pitch from the first viewport to the end of the journey.
- **Hero tag:** the page-scale tag (see Shapes), about half the first viewport from 1024px (the smaller of 700px and the viewport less 200px), carrying the display h1, a 20.4px sub-line capped at 30ch, and a bold 14px audience line pinned to its bottom. Flat at rest; selection inside it inverts to ink with a yellow glyph.
- **Companion tag:** the same object at 384px, sticky 24px from the top in the left column from 1024px. It stays hidden while the hero tag is on screen, then hands off: it fades and grows in from 0.92 scale over 220ms quart-out. It names the animal ("Tag 001", then "Sari · 001" with its mono ID) and lists the journey steps as links: reached steps show their dated stamp, unreached ones a dashed 13px mono uppercase slot. The last slot, "Awaiting your stamp", is the demo link.
- **Stamping:** a step counts as reached once its top passes 60% of the viewport; reached steps stay stamped, and skipping ahead stamps every step before. Each new stamp uses the Stamp's press, staggered 140ms when several arrive at once. Under reduced motion, or without IntersectionObserver, every stamp shows statically from the start.
- **Measured stamps:** beside the hero, three large stamps (14px, 6px 12px padding) each lead a line of a real figure in mono with its dataset, followed by a dashed "Next stamp: covered · awaiting you" slot.

### Pitch Controls
- **Pitch button:** the world's primary and secondary buttons a size up: 60px tall, 24px side padding, 20.4px heavy label.
- **Nav CTA on the shell:** on the pitch's black bar the primary inverts to tag yellow with ink text (pressed tag on hover), 44px, because ink on the shell would vanish.
- **Ledger list:** a 3px ink rule on top, 1px rules between rows, a 2px ink rule over the total row; columns from 720px.

## Do's and Don'ts

### Do:
- **Do** lead every animal with its ear tag and print every ID, figure, and timestamp in the mono.
- **Do** make the primary action ink with a tag-yellow label, 48px tall (52px for Approve and stamp).
- **Do** set Decline apart from Approve (32px beside, 24px below on a phone) in the red outline variant.
- **Do** print the post-stamp balance before the stamp buttons.
- **Do** pair every state color with an icon and a word, and every adapter figure with a provenance chip.
- **Do** use dashed outlines only for pending, awaiting, simulated, empty, or missing things.
- **Do** separate with 1-3px ink rules and keep surfaces flat at rest.
- **Do** keep every control at least 44px tall.
- **Do** keep display, lead, and the 800 weight on the pitch surface; Operate screens stay on the fixed ramp.
- **Do** mount real screenshots on the evidence mount with their provenance chip, and show every pitch stamp statically under reduced motion.

### Don't:
- **Don't** put white text on tag yellow, or use yellow for anything other than brand, the current place, identity, or awaiting.
- **Don't** rotate, texture, or distress the stamp.
- **Don't** add kickers or eyebrow labels above headings; the heading carries its own weight.
- **Don't** use hard offset block shadows; depth is soft and only for floating layers.
- **Don't** build KPI tile rows or a grey table with a single blue accent.
- **Don't** introduce a dark theme; the world is light only.
- **Don't** set text below 14px except stamps and dense mono at 13px.
