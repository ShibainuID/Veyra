import type { StampKind } from "../../components/Stamp";

/**
 * The pitch page's material. Every figure here is from the repository: the screenshots are the
 * running app (simulated, labeled data), and the proof rows quote services/api/models/MODEL_CARD.md
 * and ml/results/ verbatim.
 */

export interface Raster {
  src: string;
  width: number;
  height: number;
}

export interface Evidence extends Raster {
  alt: string;
  caption: string;
  /** A focused crop of the same state, served below 640px so its labels stay readable. */
  mobile?: Raster;
}

export interface JourneyStep {
  id: "enrolled" | "valued" | "covered" | "watched" | "claimed";
  title: string;
  /** The stamp the traveling tag receives when this step enters, dated like the app's stamps. */
  stamp: string;
  kind: StampKind;
  body: string;
  image: Evidence;
  /** A smaller second capture: the guard that held before the step could go through. */
  guard?: Evidence;
}

export const JOURNEY: readonly JourneyStep[] = [
  {
    id: "enrolled",
    title: "Enrolled",
    stamp: "Enrolled · muzzle new · 20 Oct",
    kind: "posted",
    body:
      "One guided video gives the muzzle, the teeth, and the body. The muzzle matcher returns a candidate, a new identity, or uncertain, and a person confirms it before the animal exists. In the prepared sample (simulated), Sari matched no one on the farm: the closest animal had 3 verified points, below the 5 a match needs, so she was registered as new.",
    image: {
      src: "/pitch/enrolled.webp",
      width: 1440,
      height: 742,
      mobile: { src: "/pitch/enrolled-m.webp", width: 860, height: 640 },
      alt: "The enrollment review: an Identity panel from muzzle_hybrid_v1 reading “No match on the farm”, the closest animal Rama at 3 verified points, below the 5 a match needs, a Register as a new animal button, and the checks and estimates beside it, all labeled simulated.",
      caption: "Enroll · a person confirms the identity",
    },
  },
  {
    id: "valued",
    title: "Valued",
    stamp: "Valued · 2,496–2,912 USD · 20 Oct",
    kind: "approved",
    body:
      "Her value is a range: the weight estimate, 480–560 kg, times a dated reference price of 5.20 USD/kg, labeled simulated and confirmed by the manager. An indicative value is not an insured value and not a payout.",
    image: {
      src: "/pitch/valued.webp",
      width: 1440,
      height: 1080,
      mobile: { src: "/pitch/valued-m.webp", width: 860, height: 562 },
      alt: "Sari's passport at Indicative valuation: 480–560 kg × 5.20 USD/kg = 2,496.00–2,912.00 USD, version 1, demo reference price dated 2026-10-01, confirmed by W. Santoso, beside her ear tag 001 and her passbook.",
      caption: "Passport · indicative valuation",
    },
  },
  {
    id: "covered",
    title: "Covered",
    stamp: "Covered · cover active · 20 Oct",
    kind: "posted",
    body:
      "Three fictional sample policies are checked by deterministic rules against her passport: eligible, needs a document, or ineligible, each with its terms reference. Claude explains the rules; it never decides them. The application and the premium are approved separately, and cover is active only once the insurer confirms it.",
    image: {
      src: "/pitch/covered.webp",
      width: 1440,
      height: 1080,
      mobile: { src: "/pitch/covered-m.webp", width: 860, height: 1364 },
      alt: "Coverage for Sari: three sample products compared. Basic Mortality & Accident is eligible, Mortality + Theft is unknown pending an ownership document, Dairy Health Plus is ineligible, with premiums and deductibles in USD.",
      caption: "Coverage · three sample products, one rule set",
    },
  },
  {
    id: "watched",
    title: "Watched",
    stamp: "Watched · pen A alert · 20 Oct",
    kind: "approved",
    body:
      "Recorded camera replays are tracked, and a track carries Sari's identity only while the association is strict; otherwise it stays uncertain, never guessed. In the recorded replay (simulated), her movement fell 79% below her earlier window, and VEYRA raised an inspection prompt, not a diagnosis.",
    image: {
      src: "/pitch/watched.webp",
      width: 1440,
      height: 1080,
      mobile: { src: "/pitch/watched-m.webp", width: 860, height: 1590 },
      alt: "The Monitor replay with Sari's reduced-movement alert open: movement 79% below her earlier window, the observation and baseline windows, and the line “Inspection recommended; this is not a diagnosis.”",
      caption: "Monitor · an alert asks for an inspection",
    },
  },
  {
    id: "claimed",
    title: "Claimed",
    stamp: "Claimed · submitted · 20 Oct",
    kind: "approved",
    body:
      "A claim starts from the incident and its evidence checklist. Until every item is on file, here the farmer's declaration and a vet's assessment, the agent refuses to prepare the submission. Once both were added and the manager stamped it, the sandbox insurer returned a receipt and the claim reads Assessment pending: submitted, not accepted or paid.",
    image: {
      src: "/pitch/claimed.webp",
      width: 1440,
      height: 1442,
      mobile: { src: "/pitch/claimed-m.webp", width: 860, height: 628 },
      alt: "Sari's claim after submission: every evidence checklist item present, an illustrative payout of 950.40 USD, and the Submission section with a green POSTED · SANDBOX MUTUAL stamp, Assessment pending, and the sandbox receipt number.",
      caption: "Claim · submitted with a sandbox receipt",
    },
    guard: {
      src: "/pitch/claimed-guard.webp",
      width: 690,
      height: 355,
      alt: "The same claim earlier: the agent refused to prepare the submission, still missing the farmer declaration and the veterinary assessment, code EVIDENCE_INCOMPLETE.",
      caption: "Before that, the guard held",
    },
  },
];

export const STEP_IDS: readonly string[] = JOURNEY.map((step) => `step-${step.id}`);

export interface ProofRow {
  claim: string;
  model: string;
  results: { figure: string; label: string }[];
  dataset: string;
  limit: string;
}

export const PROOF: readonly ProofRow[] = [
  {
    claim: "Muzzle identity",
    model: "muzzle_embed_v1 + SIFT verification (hybrid)",
    results: [
      { figure: "0.925", label: "correct match at threshold" },
      { figure: "0.014", label: "unknown-animal false match" },
      { figure: "0.967", label: "rank-1" },
    ],
    dataset:
      "Beef Cattle Muzzle database (Li, Erickson, and Xiong 2022): 268 US feedlot cattle, 4,923 photos, animal-level split. Test animals were not used for training or the threshold.",
    limit:
      "Not tested on other breeds, other herds, or phone video frames. Scores are not calibrated probabilities: a match is a candidate for a person to confirm.",
  },
  {
    claim: "Barn tracking",
    model: "calf_detector_v1 + BoT-SORT re-ID",
    results: [
      { figure: "0.997", label: "recall" },
      { figure: "0.976", label: "MOTA" },
      { figure: "0.709", label: "IDF1" },
    ],
    dataset: "8-Calves test video (Fang et al. 2025): 10 minutes, 12,000 frames, one pen.",
    limit: "One barn, one camera angle, eight calves. Other farms, adult cattle, and night footage are untested.",
  },
  {
    claim: "Identity handoff",
    model: "handoff_v2",
    results: [
      { figure: "0", label: "wrong identities in both 5-minute segments" },
      { figure: "0.676 / 0.545", label: "correct; the rest uncertain, never wrong" },
    ],
    dataset: "The same 8-Calves video, scored in two five-minute segments.",
    limit:
      "No held-out estimate: the policy was chosen on these two segments. A dropped identity is never re-attached automatically.",
  },
  {
    claim: "Weight",
    model: "wh_loglin_r11_v1 (photo) and tape formulas",
    results: [
      { figure: "8.7%", label: "MAPE on the photo path, withers height from a tape" },
      { figure: "5.4%", label: "MAPE with tape heart girth" },
    ],
    dataset: "R11: 71 cattle side photos, one breed group, 6-fold cross-validation.",
    limit:
      "Withers height came from a tape. Marker-scaled error is not measured yet, so field accuracy from a photo will be lower than 8.7%.",
  },
];

export const RULES: readonly { rule: string; detail: string }[] = [
  {
    rule: "Approval is bound to the exact line.",
    detail: "The stamp signs the payload hash and its version. Change any figure and the approval goes stale.",
  },
  {
    rule: "Retries never pay twice.",
    detail: "Execution is idempotent: an approved action runs once, however often it is retried.",
  },
  { rule: "Sandbox money only.", detail: "The wallet is a sandbox balance. No real funds move." },
  {
    rule: "Payment is not cover.",
    detail: "A posted premium waits for the insurer's confirmation before the cover is active.",
  },
  {
    rule: "Operators prepare; managers stamp.",
    detail: "The agent and operators can prepare an action. Only a manager can approve it.",
  },
];

export const AUDIENCES: readonly { who: string; line: string }[] = [
  {
    who: "Farm managers",
    line: "One passport per animal: identity, value, cover, and what the cameras saw, with every financial step waiting on your stamp.",
  },
  {
    who: "Livestock insurers",
    line: "Applications and claims that arrive with a muzzle reference, a dated valuation, and a complete evidence checklist, all tied to one animal ID.",
  },
  {
    who: "Vets and animal-health officers",
    line: "Camera observations framed as inspection prompts, and your professional finding kept separate from the farm's report.",
  },
];

export const LIMITS: readonly string[] = [
  "The herd, policies, prices (5.20 USD/kg), camera scenarios, and enrollment samples are fixtures, and every screen labels them simulated.",
  "Tracking was measured on one pen in one dataset (8-Calves). Other barns, adult cattle, and night footage are untested.",
  "No real money and no real insurer: the wallet, the payment provider, and Sandbox Mutual are sandboxes.",
  "Recording enrollment video from a device camera is untested on real devices; the prepared samples are the scripted path.",
  "Muzzle identity was tested on photos of US feedlot cattle, not on other breeds or phone video.",
  "Identity handoff has no held-out estimate yet.",
  "Claude is offline unless an ANTHROPIC_API_KEY is set; explanations then read “Template explanation (offline)”.",
];

export const ROLES: readonly { role: string; person: string; can: string }[] = [
  { role: "Manager", person: "W. Santoso", can: "approves and stamps, declines, and resets the demo" },
  { role: "Operator", person: "A. Pratama", can: "enrolls, investigates alerts, and prepares actions; cannot approve" },
  { role: "Vet", person: "dr. R. Lestari", can: "adds professional findings to incidents; no payment authority" },
];
