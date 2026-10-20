// BEATS: the single source of truth for timing. Every animation and every sound reads its times from here.
// The word cues come from the brief (scripts/gen-words.mjs -> words.json / script.json). A new take with the same
// script only needs `pnpm words`; a new script needs the `at(sentence, "word")` lookups below checked.
import WORDS_JSON from "./words.json";
import SCRIPT_JSON from "./script.json";

export type Word = { i: number; w: string; s: number; e: number };
export type Sentence = { i: number; text: string; s: number; e: number; w0: number; w1: number };

export const WORDS = WORDS_JSON as Word[];
export const SCRIPT = SCRIPT_JSON as Sentence[];
export const FPS = 30;
export const WIDTH = 1280;
export const HEIGHT = 720;
/** Visuals may lead their word by up to 0.2 s, never lag: every cue fires this much before the word starts. */
export const LEAD = 0.1;
export const LAST_WORD_END = WORDS[WORDS.length - 1].e;
/** Last word end + ~1 s, on whole frames (211 s). */
export const DURATION = Math.round((LAST_WORD_END + 1) * FPS) / FPS;
export const DURATION_FRAMES = Math.round(DURATION * FPS);

const norm = (s: string) => s.toLowerCase().replace(/[^a-z0-9]/g, "");

/** The `nth` word in sentence `si` that starts with `text`. */
export function wordIn(si: number, text: string, nth = 1): Word {
  const sent = SCRIPT[si];
  let k = 0;
  for (let i = sent.w0; i <= sent.w1; i++) {
    if (norm(WORDS[i].w).startsWith(norm(text)) && ++k === nth) return WORDS[i];
  }
  throw new Error(`No word "${text}" (#${nth}) in sentence ${si}: ${sent.text}`);
}
/** Cue time for a word: its start minus LEAD. */
export const at = (si: number, text: string, nth = 1) => +(wordIn(si, text, nth).s - LEAD).toFixed(3);
/** End time of a word (for holds and sounds that should finish with the word). */
export const endOf = (si: number, text: string, nth = 1) => wordIn(si, text, nth).e;
const S = (si: number) => SCRIPT[si];

export type Beat = {
  id: string;
  /** scene group that draws it */
  scene: SceneId;
  start: number;
  end: number;
  /** the words spoken */
  say: string;
  /** what is on screen */
  screen: string;
  /** exact reveal times (seconds, LEAD applied) */
  cue: Record<string, number>;
};

function beat(id: string, scene: SceneId, s0: number, s1: number, screen: string, cue: Record<string, number>): Beat {
  return {
    id,
    scene,
    start: S(s0).s,
    end: S(s1).e,
    say: SCRIPT.slice(s0, s1 + 1)
      .map((x) => x.text)
      .join(" "),
    screen,
    cue,
  };
}

export type SceneId =
  | "problem"
  | "reveal"
  | "herd"
  | "enroll"
  | "passport"
  | "insurance"
  | "approval"
  | "monitor"
  | "ask"
  | "claim"
  | "audit"
  | "close";

export const BEATS = {
  hook: beat("hook", "problem", 0, 0, "Real herd in the barn (CCTV wide, slow push) -> cut to the cow side-on; 'Every cow.' / 'A valuable asset.'", {
    everyCow: at(0, "every"),
    cow: at(0, "cow"),
    valuable: at(0, "valuable"),
    asset: at(0, "asset"),
  }),
  scattered: beat("scattered", "problem", 1, 1, "Footage shrinks into a card on the dark stage; three fragments drift apart: Paper records / Camera footage / Insurance documents", {
    info: at(1, "information"),
    scattered: at(1, "scattered"),
    records: at(1, "records"),
    camera: at(1, "camera"),
    insurance: at(1, "insurance"),
  }),
  tooLong: beat("tooLong", "problem", 2, 2, "Worker leading the cow (CCTV crop); broken hairline from 'Evidence' to 'Action'; 'Too long.' in red", {
    wrong: at(2, "wrong"),
    finding: at(2, "finding"),
    evidence: at(2, "evidence"),
    action: at(2, "action"),
    tooLong: at(2, "too"),
  }),
  meet: beat("meet", "reveal", 3, 3, "Rim light finds the phone in the dark, key light fades up, VEYRA wordmark; callouts Identity / Monitoring / Insurance; edge ring ignites on 'one place'", {
    meet: at(3, "Meet"),
    veyra: at(3, "VEYRA"),
    connects: at(3, "connects"),
    identity: at(3, "identity"),
    health: at(3, "health"),
    insurance: at(3, "insurance"),
    onePlace: at(3, "one"),
  }),
  goal: beat("goal", "reveal", 4, 4, "Camera orbits; 'Know every animal.' 'Understand its value.' 'Protect it.' land word by word beside the phone", {
    know: at(4, "know"),
    value: at(4, "understand"),
    financial: at(4, "financial"),
    protect: at(4, "protect"),
    workflows: at(4, "clearer"),
  }),
  herd: beat("herd", "herd", 5, 5, "Herd screen over the real barn: five seeded animals; callouts Ear tag ID / Indicative value / Coverage / Alerts", {
    herd: at(5, "herd"),
    manager: at(5, "manager"),
    registered: at(5, "registered"),
    values: at(5, "estimated"),
    status: at(5, "insurance"),
    alerts: at(5, "alerts"),
  }),
  capture: beat("capture", "enroll", 6, 6, "Scan Cow: phone camera shows the real muzzle inside the guide box; quality fills; guided steps Muzzle / Teeth / Body", {
    add: at(6, "add"),
    uploads: at(6, "uploads"),
    guided: at(6, "guided"),
    nose: at(6, "nose"),
    teeth: at(6, "teeth"),
    body: at(6, "full"),
  }),
  extract: beat("extract", "enroll", 7, 7, "Upload -> three reference frames extracted; 'Confirm identity' tapped by a person; CONFIRMED stamp", {
    extracts: at(7, "extracts"),
    images: at(7, "useful"),
    person: at(7, "person"),
    confirm: at(7, "confirm"),
    identity: at(7, "identity"),
  }),
  unclear: beat("unclear", "enroll", 8, 8, "Second phone: blurred muzzle, dashed tag, 'Unclear - review required'; 'No guessing.'", {
    unclear: at(8, "unclear"),
    record: at(8, "record"),
    stays: at(8, "unconfirmed"),
    guessing: at(8, "guessing"),
  }),
  passport: beat("passport", "passport", 9, 9, "Light sweep; the passport is created in the app: ear tag 001 stamps in; 'Digital Livestock Passport'", {
    confirmed: at(9, "confirmed"),
    receives: at(9, "receives"),
    digital: at(9, "Digital"),
    livestock: at(9, "Livestock"),
    passport: at(9, "Passport"),
  }),
  passportPage: beat("passportPage", "passport", 10, 10, "Passport scrolls; callouts Identity images / Age 24-30 mo / Weight 480-560 kg / Observation history / Documents", {
    page: at(10, "page"),
    identityImages: at(10, "identity"),
    age: at(10, "age"),
    weight: at(10, "weight"),
    history: at(10, "observation"),
    docs: at(10, "supporting"),
  }),
  valuation: beat("valuation", "passport", 11, 11, "Valuation calculator: 480-560 kg x 5.20 USD/kg = 2,496-2,912 USD (gradient key number)", {
    calculates: at(11, "calculates"),
    range: at(11, "value"),
    weight: at(11, "confirmed"),
    price: at(11, "price"),
    perKg: at(11, "kilogram"),
  }),
  notGuaranteed: beat("notGuaranteed", "passport", 12, 12, "'Estimated, not guaranteed'; red strikes on 'Selling price' and 'Insurance payout'", {
    transparent: at(12, "transparent"),
    not: at(12, "not"),
    guaranteed: at(12, "guaranteed"),
    selling: at(12, "selling"),
    payout: at(12, "payout"),
  }),
  gap: beat("gap", "insurance", 13, 13, "'No active insurance' on the passport -> Find insurance -> VEYRA AI Agent opens and speaks first; three plans", {
    next: at(13, "Next"),
    assistant: at(13, "assistant"),
    compares: at(13, "compares"),
    three: at(13, "three"),
    policies: at(13, "policies"),
  }),
  plans: beat("plans", "insurance", 14, 14, "Three plan cards lift out of the phone: eligibility, premium, coverage, exclusions, gap", {
    checks: at(14, "checks"),
    eligibility: at(14, "eligibility"),
    premiums: at(14, "premiums"),
    coverage: at(14, "coverage"),
    exclusions: at(14, "exclusions"),
    gaps: at(14, "possible"),
  }),
  tradeoffs: beat("tradeoffs", "insurance", 15, 15, "Agent recommendation with reasons and the tradeoff; the manager taps 'Choose this plan'", {
    instead: at(15, "Instead"),
    cheapest: at(15, "cheapest"),
    explains: at(15, "explains"),
    tradeoffs: at(15, "tradeoffs"),
    informed: at(15, "informed"),
    choice: at(15, "choice"),
  }),
  prepare: beat("prepare", "approval", 16, 16, "'Prepare application': fields auto-fill from the passport, evidence checklist; two separate actions: Application / Premium 87.36 USD", {
    selects: at(16, "selects"),
    agent: at(16, "agent"),
    prepares: at(16, "prepares"),
    application: at(16, "application"),
    separate: at(16, "separate"),
    payment: at(16, "premium"),
  }),
  approvalRule: beat("approvalRule", "approval", 17, 17, "'Approval first.' headline; awaiting-stamp line", {
    nothing: at(17, "Nothing"),
    approval: at(17, "approval"),
  }),
  approve: beat("approve", "approval", 18, 18, "Farmer reviews details, 'Approve and stamp' twice (APPROVED stamps), sandbox provider receipt", {
    details: at(18, "details"),
    approves: at(18, "approves"),
    each: at(18, "action"),
    response: at(18, "provider"),
  }),
  sandbox: beat("sandbox", "approval", 19, 19, "'Sandbox' chip, 'No real money'; sandbox wallet 10,000.00 -> 9,912.64 USD", {
    sandbox: at(19, "sandbox"),
    money: at(19, "real"),
  }),
  activation: beat("activation", "approval", 20, 20, "Three distinct states: Submitted / Payment recorded (sandbox) / Coverage confirmed by insurer -> 'Coverage active'", {
    payment: at(20, "payment"),
    notMean: at(20, "not"),
    coverage: at(20, "coverage"),
    insurer: at(20, "insurer"),
    confirms: at(20, "confirms"),
  }),
  cameras: beat("cameras", "monitor", 21, 21, "Cut to real barn CCTV; HUD CAM-01 Pen A, timestamp; hairline from the passport to the camera", {
    connects: at(21, "connects"),
    passport: at(21, "passport"),
    camera: at(21, "camera"),
  }),
  tracks: beat("tracks", "monitor", 22, 22, "Detections draw on (unassigned, no tag); only the associated track carries tag 001; last seen 17:09", {
    recorded: at(22, "recorded"),
    feed: at(22, "feed"),
    tracks: at(22, "tracks"),
    lastKnown: at(22, "last"),
  }),
  alert: beat("alert", "monitor", 23, 23, "Movement trend drops below baseline; 'Unusual reduced movement - Review required' with time window and clip", {
    identified: at(23, "identified"),
    less: at(23, "less"),
    expected: at(23, "expected"),
    alert: at(23, "alert"),
    timestamp: at(23, "timestamp"),
    footage: at(23, "supporting"),
  }),
  notDiagnosis: beat("notDiagnosis", "monitor", 24, 24, "Phone Monitor screen with the clip; 'Requires inspection' + red strike on 'Diagnosis'", {
    inspect: at(24, "inspect"),
    not: at(24, "not"),
    diagnosis: at(24, "diagnosis"),
  }),
  ask: beat("ask", "ask", 25, 25, "Ask: typed 'Where was Sari last seen?' -> answer card: CAM-01 Pen A - feed line, 17:09, evidence frame", {
    ask: at(25, "ask"),
    question: at(25, "Where"),
    seen: at(25, "seen"),
    answer: at(25, "answer"),
    recorded: at(25, "recorded"),
  }),
  incident: beat("incident", "claim", 26, 26, "Bima (002, Coverage active) in the barn; incident recorded; 'Help me file an insurance claim.'", {
    later: at(26, "later"),
    incident: at(26, "incident"),
    agent: at(26, "insurance"),
    claim: at(26, "claim"),
  }),
  checklist: beat("checklist", "claim", 27, 27, "Evidence checklist builds: passport identity, camera observations, policy, incident facts", {
    gathers: at(27, "gathers"),
    passport: at(27, "passport"),
    observations: at(27, "relevant"),
    policy: at(27, "policy"),
    evidence: at(27, "available"),
    checklist: at(27, "checklist"),
  }),
  missing: beat("missing", "claim", 28, 28, "Vet assessment flagged Missing; submission blocked until it is added", {
    missing: at(28, "Missing"),
    flagged: at(28, "flagged"),
    submission: at(28, "submission"),
  }),
  submit: beat("submit", "claim", 29, 29, "Declaration checked, Approve and stamp, sent to the simulated insurer, 'Submitted - Pending assessment', Track claim status", {
    facts: at(29, "facts"),
    approves: at(29, "approves"),
    send: at(29, "send"),
    insurer: at(29, "simulated"),
    pending: at(29, "pending"),
  }),
  audit: beat("audit", "audit", 30, 30, "Audit trail lines post: identity confirmed / action approved / provider receipt", {
    every: at(30, "Every"),
    trail: at(30, "audit"),
    identity: at(30, "confirmed"),
    approved: at(30, "approved"),
    provider: at(30, "provider"),
  }),
  blocks: beat("blocks", "audit", 31, 31, "Blocked lines: IDENTITY_UNCONFIRMED and APPROVAL_REQUIRED; red BLOCKED stamp", {
    uncertain: at(31, "uncertain"),
    missing: at(31, "missing"),
    blocks: at(31, "blocks"),
  }),
  connects: beat("connects", "close", 32, 32, "Real cow + phone with the unified passport (identity, monitoring, coverage)", {
    veyra: at(32, "VEYRA"),
    identity: at(32, "identity"),
    protection: at(32, "financial"),
  }),
  tagline: beat("tagline", "close", 33, 34, "Light sweep to the white stage; 'Know every animal.' 'Protect every asset.'", {
    know: at(33, "Know"),
    every1: at(33, "every"),
    animal: at(33, "animal"),
    protect: at(34, "Protect"),
    every2: at(34, "every"),
    asset: at(34, "asset"),
  }),
} as const satisfies Record<string, Beat>;

export type BeatId = keyof typeof BEATS;
export const B = BEATS; // short alias for scenes

/** Scene groups: [start, end) in seconds. Overlaps are cross-fades / wipes handled inside the scenes. */
export const SCENES: Record<SceneId, { start: number; end: number }> = {
  problem: { start: 0, end: B.meet.start + 0.3 },
  reveal: { start: B.meet.start - 0.4, end: B.herd.start + 0.6 },
  herd: { start: B.herd.start - 0.4, end: B.capture.start + 0.5 },
  enroll: { start: B.capture.start - 0.4, end: B.passport.start + 0.6 },
  passport: { start: B.passport.start - 0.4, end: B.gap.start + 0.4 },
  insurance: { start: B.gap.start - 0.3, end: B.prepare.start + 0.4 },
  approval: { start: B.prepare.start - 0.3, end: B.cameras.start + 0.5 },
  monitor: { start: B.cameras.start - 0.4, end: B.ask.start + 0.5 },
  ask: { start: B.ask.start - 0.4, end: B.incident.start + 0.5 },
  claim: { start: B.incident.start - 0.4, end: B.audit.start + 0.5 },
  audit: { start: B.audit.start - 0.4, end: B.connects.start + 0.5 },
  close: { start: B.connects.start - 0.4, end: DURATION },
};
