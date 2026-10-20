// scoreSound(k): the film's sound design on the brief's SOUND kit (src/audio/sound.js), voiceover mode.
// Every time comes from BEATS (the same cues the picture uses), so a sound starts on the frame its event appears.
// Keynote-film palette, after the reference's explainerSound(): deep soft "bwooms" on reveals, airy risers into
// big moments, clean low clicks for labels and words, smooth low glides for camera moves, a muted low two-note
// for wrong/blocked moments, warm chords for confirmations, stamps for approvals, keys while the app types.
// Small frequent sounds are { minor: true } (about 60 % in voiceover mode).
import { B, DURATION } from "../beats";

/* eslint-disable @typescript-eslint/no-explicit-any */
type Kit = any;

export function scoreSound(k: Kit) {
  const D = DURATION;
  const bwoom = (t: number, g: number, dur = 1.4, f = 58) => {
    k.tone(t, { f: [[0, f * 1.7], [0.1, f], [dur, f * 0.72]], dur, gain: 0.5 * g, a: 0.012, hold: dur * 0.15 });
    k.tone(t, { f: f * 2, dur: dur * 0.45, gain: 0.07 * g, a: 0.012 });
    k.noise(t, { dur: 0.6, color: "brown", filter: "lowpass", f: [[0, 420], [0.6, 80]], gain: 0.22 * g, a: 0.008, verb: 0.25 });
  };
  const air = (t: number, dur: number, g: number) => {
    k.noise(t, { dur, color: "pink", filter: "bandpass", f: [[0, 450], [dur, 4200]], q: 0.7, gain: 0.13 * g, a: dur * 0.92, verb: 0.35 });
    k.tone(t, { f: [[0, "D3"], [dur, "D4"]], type: "triangle", dur, gain: 0.025 * g, a: dur * 0.9, filter: "lowpass", f2: 900 });
  };
  const click = (t: number, g = 1, pan = 0, minor = true) => {
    k.noise(t, { dur: 0.014, filter: "bandpass", f: 2300, q: 1.6, gain: 0.2 * g, pan, minor });
    k.tone(t, { f: [[0, 420], [0.03, 260]], dur: 0.04, gain: 0.07 * g, pan, minor });
  };
  const glide = (t: number, dur: number, g: number, pan = 0, minor = true) =>
    k.noise(t, { dur, color: "pink", filter: "lowpass", f: [[0, 160], [dur * 0.5, 720], [dur, 190]], q: 0.9, gain: 0.26 * g, a: dur * 0.45, pan, verb: 0.15, minor });
  const chord = (t: number, notes: string[], dur: number, g: number, minor = false) =>
    notes.forEach((n, i) => {
      const pan = (i - (notes.length - 1) / 2) * 0.22;
      k.tone(t, { f: n, type: "triangle", dur, gain: 0.05 * g, a: 0.03, hold: dur * 0.3, filter: "lowpass", f2: [[0, 2200], [dur, 700]], pan, verb: 0.4, minor });
      k.tone(t, { f: k.hz(n) * 1.003, dur, gain: 0.04 * g, a: 0.05, hold: dur * 0.3, pan: -pan, verb: 0.4, minor });
    });
  const lowTwo = (t: number, g = 0.8) => {
    // the reference's muted low two-note for a wrong moment
    k.tone(t, { f: "A2", type: "triangle", dur: 0.22, gain: 0.16 * g, hold: 0.1, filter: "lowpass", f2: 700 });
    k.tone(t + 0.16, { f: "F2", type: "triangle", dur: 0.34, gain: 0.16 * g, hold: 0.16, filter: "lowpass", f2: 600 });
  };
  const sweep = (t: number, g = 1) => {
    k.noise(t, { dur: 0.5, color: "pink", filter: "bandpass", f: [[0, 380], [0.25, 3000], [0.5, 900]], q: 0.8, gain: 0.26 * g, a: 0.22, pan: -0.4, verb: 0.3 });
    k.noise(t + 0.12, { dur: 0.4, color: "pink", filter: "bandpass", f: [[0, 600], [0.2, 2600], [0.4, 900]], q: 0.8, gain: 0.18 * g, a: 0.15, pan: 0.5, verb: 0.3 });
  };
  const words = (ts: number[], g = 0.7) => ts.forEach((t, i) => click(t, g, (i - (ts.length - 1) / 2) * 0.12));
  const tap = (t: number) => k.play("click", t, { gain: 0.9, minor: true });
  const typing = (t: number, dur: number, rate = 0.07, g = 0.55) => k.play("typing", t, { n: Math.max(2, Math.round(dur / rate)), rate, gain: g, minor: true });

  const CH = { home: ["D3", "A3", "E4", "F#4"], lift: ["G2", "D3", "B3", "F#4"], warm: ["B2", "F#3", "D4", "A4"], sus: ["A2", "E3", "B3", "D4"] };

  // ---------------- 00:00 problem ----------------
  const hk = B.hook.cue,
    sc = B.scattered.cue,
    tl = B.tooLong.cue;
  air(0.05, 0.9, 0.6);
  bwoom(0.15, 0.45, 1.6, 52);
  words([hk.everyCow, hk.cow]);
  words([hk.valuable, hk.asset]);
  chord(hk.asset + 0.05, ["D3", "A3", "E4"], 1.4, 0.5, true);
  glide(B.scattered.start - 0.1, 1.1, 0.9, 0, false); // footage shrinks into a card
  k.play("swish", sc.scattered, { gain: 0.7 });
  click(sc.scattered, 0.8);
  k.play("paper", sc.records, { dur: 0.3, gain: 0.8, minor: true });
  k.play("slap", sc.records + 0.18, { gain: 0.35, minor: true });
  k.play("blip", sc.camera, { f: "A5", gain: 0.6, minor: true });
  k.play("paper", sc.insurance, { dur: 0.32, gain: 0.8, minor: true, pan: 0.4 });
  k.play("slap", sc.insurance + 0.2, { gain: 0.35, minor: true, pan: 0.4 });
  k.play("tick", sc.insurance + 0.6, { gain: 0.6, minor: true, pan: -0.3 });
  k.play("tick", sc.insurance + 0.75, { gain: 0.6, minor: true, pan: 0.3 });
  glide(B.tooLong.start - 0.15, 0.9, 0.8, 0, false);
  lowTwo(tl.wrong, 0.7);
  for (let t = tl.wrong + 1.6; t < tl.tooLong; t += 1.6) k.play("tick", t, { f: 1800, gain: 0.35, minor: true });
  click(tl.evidence, 0.8);
  click(tl.action, 0.8);
  k.play("stroke", tl.evidence + 0.2, { material: "pen", dur: tl.tooLong + 0.6 - tl.evidence, gain: 0.5, minor: true });
  k.play("thud", tl.tooLong, { gain: 0.6 });
  click(tl.tooLong + 0.45, 0.7);
  air(B.meet.start - 0.85, 0.85, 0.9);

  // ---------------- 00:22 reveal ----------------
  const m = B.meet.cue,
    g = B.goal.cue;
  bwoom(m.meet + 0.05, 0.75, 1.8);
  words([m.meet, m.veyra]);
  k.play("sparkle", m.veyra + 0.05, { n: 6, gain: 0.7, minor: true });
  chord(m.veyra + 0.1, CH.home, 2.2, 0.55);
  [m.identity, m.health, m.insurance].forEach((t, i) => {
    glide(t, 0.6, 0.45, i === 2 ? 0.4 : -0.4);
    click(t + 0.55, 0.6, i === 2 ? 0.4 : -0.4);
  });
  chord(m.onePlace, ["A3", "E4"], 1.2, 0.5, true); // edge ring ignites
  bwoom(m.onePlace, 0.35, 1.0, 64);
  glide(m.onePlace + 0.7, 1.6, 0.9, 0, false); // wordmark to the corner, camera orbits left
  words([g.know, g.know + 0.36, g.know + 0.78]);
  words([g.value, g.value + 0.5, g.financial + 0.4]);
  words([g.protect, g.protect + 0.45]);
  chord(g.protect + 0.1, CH.warm, 1.6, 0.45, true);

  // ---------------- 00:38 herd ----------------
  const h = B.herd.cue;
  glide(B.herd.start - 0.3, 1.2, 0.8, 0, false);
  click(h.herd, 0.7);
  [h.registered, h.values, h.status, h.alerts].forEach((t, i) => {
    glide(t, 0.6, 0.35, 0.4);
    click(t + 0.55, 0.6, 0.3 + i * 0.05);
  });

  // ---------------- 00:46 enrollment ----------------
  const c = B.capture.cue,
    e = B.extract.cue,
    u = B.unclear.cue;
  tap(c.add - 0.05);
  glide(B.capture.start - 0.3, 0.9, 0.8, 0.3, false);
  k.play("blip", c.add + 0.25, { f: "E6", gain: 0.7, minor: true }); // recording starts
  words([c.guided - 0.35, c.guided, c.guided + 0.38], 0.6);
  for (let t = c.guided; t < c.nose + 0.3; t += 0.18) k.play("count", t, { gain: 0.45, minor: true }); // quality fills
  k.play("shutter", c.nose + 0.3, { gain: 0.9 });
  click(c.nose, 0.6);
  k.play("blip", c.teeth, { f: "A5", gain: 0.6, minor: true });
  click(c.teeth, 0.6);
  k.play("blip", c.body, { f: "C6", gain: 0.6, minor: true });
  click(c.body, 0.6);
  k.play("riser", e.extracts - 0.3, { dur: 0.7, gain: 0.5 }); // upload
  [0, 0.2, 0.4].forEach((d, i) => k.play("pop", e.images + d, { f: 560 + i * 90, gain: 0.6, minor: true }));
  words([e.person - 0.25, e.person, e.confirm], 0.6);
  tap(e.confirm - 0.05);
  k.play("stamp", e.confirm, { gain: 0.9 });
  chord(e.confirm + 0.15, CH.home, 1.4, 0.45, true);
  k.play("whoosh", u.unclear - 0.4, { dur: 0.8, gain: 0.6, pan: 0.5 }); // the second phone slides in
  k.play("buzz", u.unclear + 0.35, { f: 98, dur: 0.25, gain: 0.35 });
  click(u.stays, 0.6);
  words([u.guessing - 0.3, u.guessing], 0.8);
  k.play("thud", u.guessing, { gain: 0.35 });

  // ---------------- 01:03 passport ----------------
  const p = B.passport.cue,
    pp = B.passportPage.cue,
    v = B.valuation.cue,
    ng = B.notGuaranteed.cue;
  sweep(B.passport.start - 0.25, 0.7);
  k.play("stamp", p.confirmed, { gain: 0.7 }); // tag 001 lands
  bwoom(p.digital, 0.5, 1.4);
  words([p.digital, p.livestock, p.passport]);
  chord(p.passport + 0.05, CH.lift, 1.8, 0.5);
  glide(pp.page - 0.1, 1.0, 0.7, -0.3);
  [pp.identityImages, pp.age, pp.weight, pp.history, pp.docs].forEach((t) => {
    glide(t, 0.55, 0.3, 0.45);
    click(t + 0.55, 0.55, 0.45);
  });
  glide(v.calculates - 0.4, 1.0, 0.7, 0.3, false);
  click(v.calculates, 0.6);
  typing(v.weight, 0.6);
  bwoom(v.range, 0.45, 1.2); // the key number arrives
  words([v.weight, v.weight + 0.2]);
  words([v.price - 0.15, v.price, v.perKg]);
  chord(v.perKg + 0.1, CH.warm, 1.5, 0.55); // the value range locks
  k.noise(v.perKg + 0.2, { dur: 0.5, color: "pink", filter: "bandpass", f: [[0, 1400], [0.25, 2600], [0.5, 1500]], q: 1.5, gain: 0.05, a: 0.2, minor: true }); // gleam
  click(ng.transparent, 0.6);
  click(ng.selling, 0.6);
  k.play("swish", ng.selling + 0.25, { dur: 0.2, gain: 0.5 });
  lowTwo(ng.selling + 0.3, 0.5);
  click(ng.payout - 0.35, 0.6);
  k.play("swish", ng.payout, { dur: 0.2, gain: 0.5 });
  lowTwo(ng.payout + 0.05, 0.55);

  // ---------------- 01:28 insurance agent ----------------
  const gp = B.gap.cue,
    pl = B.plans.cue,
    tr = B.tradeoffs.cue;
  k.play("buzz", gp.next, { f: 92, dur: 0.35, gain: 0.45 }); // no active insurance
  words([gp.next, gp.next + 0.12, gp.next + 0.24], 0.7);
  tap(gp.next + 0.4);
  k.play("whoosh", gp.next + 0.7, { dur: 0.5, gain: 0.45 });
  k.play("blip", gp.assistant, { f: "E6", gain: 0.5, minor: true });
  typing(gp.assistant + 0.05, 1.4, 0.06, 0.4);
  typing(gp.compares + 0.05, 1.0, 0.06, 0.4);
  glide(gp.three - 0.2, 1.0, 0.8, 0.4, false);
  [0, 0.18, 0.36].forEach((d, i) => k.play("pop", gp.three + d, { f: 600 + i * 80, gain: 0.65, minor: true, pan: -0.1 + i * 0.25 }));
  [pl.eligibility, pl.premiums, pl.coverage, pl.exclusions, pl.gaps].forEach((t) => [0, 0.06, 0.12].forEach((d, i) => k.play("tick", t + d, { gain: 0.5, minor: true, pan: -0.1 + i * 0.25 })));
  click(pl.eligibility, 0.6);
  typing(tr.instead - 0.2, 0.9, 0.06, 0.4);
  words([tr.cheapest - 0.05, tr.cheapest + 0.1, tr.cheapest + 0.22, tr.cheapest + 0.34], 0.55);
  k.play("pop", tr.cheapest + 0.5, { f: 480, gain: 0.5, minor: true });
  chord(tr.explains, ["A3", "E4", "B4"], 1.3, 0.45, true);
  k.play("sparkle", tr.explains + 0.1, { n: 5, gain: 0.55, minor: true });
  words([tr.tradeoffs, tr.tradeoffs + 0.3], 0.6);
  tap(tr.informed);
  k.play("ding", tr.choice + 0.05, { f: "E6", gain: 0.55 });

  // ---------------- 01:51 application and approval ----------------
  const pr = B.prepare.cue,
    ar = B.approvalRule.cue,
    ap = B.approve.cue,
    sb = B.sandbox.cue,
    ac = B.activation.cue;
  tap(pr.agent);
  glide(pr.prepares - 0.2, 0.8, 0.6, 0, false);
  typing(pr.prepares + 0.2, 2.1, 0.06, 0.5);
  [0, 0.15, 0.3, 0.45].forEach((d) => k.play("tick", pr.application + 0.3 + d, { gain: 0.5, minor: true }));
  k.play("pop", pr.application, { f: 560, gain: 0.7, minor: true, pan: 0.4 });
  k.play("pop", pr.payment, { f: 680, gain: 0.7, minor: true, pan: 0.4 });
  k.play("thud", ar.approval, { gain: 0.35 });
  words([ar.approval, ar.approval + 0.3], 0.7);
  tap(ap.approves - 0.05);
  k.play("stamp", ap.approves, { gain: 1.0, pan: 0.2 });
  tap(ap.each - 0.05);
  k.play("stamp", ap.each, { gain: 1.0, pan: 0.2 });
  k.play("success", ap.response, { f: "C6", gain: 0.5 });
  k.play("tock", sb.sandbox, { f: 520, gain: 0.5 });
  words([sb.money - 0.15, sb.money, sb.money + 0.25], 0.6);
  for (let i = 0; i < 6; i++) k.play("count", sb.money + 0.3 + i * 0.05, { gain: 0.4, minor: true });
  k.play("tick", ac.payment - 0.25, { gain: 0.6 });
  k.play("tick", ac.payment, { gain: 0.6 });
  k.play("tock", ac.notMean, { f: 300, gain: 0.45 });
  bwoom(ac.confirms, 0.6, 1.5);
  k.play("success", ac.confirms + 0.02, { f: "D6", gain: 0.75 });
  chord(ac.confirms + 0.05, CH.home, 1.6, 0.6); // coverage active: the right moment

  // ---------------- 02:13 monitoring ----------------
  const cm = B.cameras.cue,
    tk = B.tracks.cue,
    al = B.alert.cue,
    nd = B.notDiagnosis.cue;
  sweep(B.cameras.start, 0.6);
  k.play("crtOn", B.cameras.start + 0.1, { gain: 0.6 });
  k.play("pop", cm.passport, { f: 520, gain: 0.55, minor: true });
  glide(cm.camera, 0.8, 0.4, -0.2);
  click(cm.camera + 0.8, 0.6);
  k.play("tick", tk.recorded, { f: 3000, gain: 0.5, minor: true });
  for (let i = 0; i < 12; i++) k.play("tick", tk.tracks + i * 0.05, { f: 3800 + (i % 3) * 300, gain: 0.35, minor: true, pan: -0.5 + (i % 6) * 0.2 });
  k.play("ding", tk.tracks + 0.6, { f: "A5", gain: 0.5 }); // identified in the scan zone
  click(tk.lastKnown, 0.6);
  k.play("stroke", al.identified, { material: "pen", dur: 1.2, gain: 0.4, minor: true });
  k.play("tock", al.less, { f: 340, gain: 0.45 });
  k.play("tock", al.less + 0.25, { f: 260, gain: 0.45 });
  k.play("bell", al.alert, { f: "E5", gain: 0.45 });
  click(al.timestamp, 0.7);
  k.play("pop", al.footage, { f: 600, gain: 0.55, minor: true });
  glide(nd.inspect - 1.0, 1.0, 0.8, 0.3, false); // phone returns
  words([nd.inspect - 0.25, nd.inspect], 0.6);
  click(nd.not, 0.6);
  k.play("swish", nd.diagnosis, { dur: 0.2, gain: 0.5 });
  lowTwo(nd.diagnosis + 0.05, 0.55);

  // ---------------- 02:35 ask ----------------
  const q = B.ask.cue;
  glide(B.ask.start - 0.3, 0.9, 0.6, 0, false);
  click(q.ask, 0.7);
  typing(q.question, q.seen + 0.4 - q.question, 0.07, 0.6);
  tap(q.seen + 0.45);
  k.play("pop", q.seen + 0.5, { f: 640, gain: 0.55, minor: true });
  bwoom(q.answer, 0.4, 1.1);
  k.play("ding", q.answer + 0.02, { f: "B5", gain: 0.5 });
  click(q.recorded, 0.6);

  // ---------------- 02:43 claim for the insured cow ----------------
  const inc = B.incident.cue,
    ch = B.checklist.cue,
    mi = B.missing.cue,
    su = B.submit.cue;
  glide(B.incident.start - 0.4, 1.1, 0.8, 0, false);
  click(inc.later, 0.6);
  tap(inc.incident - 0.2);
  typing(inc.incident + 0.1, 0.8, 0.05, 0.45);
  k.play("stamp", inc.agent - 0.15, { gain: 0.5 });
  k.play("pop", inc.agent + 0.2, { f: 560, gain: 0.5, minor: true });
  typing(inc.claim - 0.3, 1.2, 0.06, 0.4);
  words([inc.agent, inc.claim], 0.6);
  [ch.passport, ch.observations, ch.policy, ch.evidence].forEach((t) => {
    k.play("pop", t, { f: 620, gain: 0.55, minor: true, pan: 0.4 });
    k.play("tick", t + 0.08, { gain: 0.5, minor: true, pan: 0.4 });
  });
  k.play("ding", ch.passport + 0.5, { f: "G5", gain: 0.4 }); // muzzle re-scan: match
  chord(ch.checklist, ["D3", "A3", "F#4"], 1.1, 0.45, true);
  lowTwo(mi.missing, 0.75); // missing document
  k.play("buzz", mi.flagged, { f: 104, dur: 0.25, gain: 0.35 });
  k.play("success", mi.submission + 0.45, { f: "C6", gain: 0.45 });
  glide(su.facts - 1.6, 1.2, 0.7, 0.3, false);
  click(su.facts, 0.7);
  tap(su.approves - 0.05);
  k.play("stamp", su.approves, { gain: 1.0 });
  k.play("whoosh", su.send, { dur: 0.7, gain: 0.5, pan: -0.5 });
  click(su.insurer, 0.6);
  chord(su.pending, CH.sus, 1.8, 0.5); // pending: unresolved on purpose
  bwoom(su.pending, 0.35, 1.3, 55);

  // ---------------- 03:08 audit ----------------
  const au = B.audit.cue,
    bl = B.blocks.cue;
  glide(B.audit.start - 0.3, 0.9, 0.6, 0, false);
  words([au.trail, au.trail + 0.3]);
  [au.identity, au.approved, au.approved + 0.3, au.provider, au.provider + 0.35].forEach((t) => k.play("stamp", t, { gain: 0.35, minor: true, pan: -0.3 }));
  [au.identity, au.approved, au.provider].forEach((t) => click(t + 0.1, 0.6, 0.4));
  k.play("error", bl.uncertain, { f: "A3", gain: 0.6 });
  k.play("error", bl.missing, { f: "G3", gain: 0.6 });
  k.play("impact", bl.blocks, { gain: 0.6 });
  k.play("stamp", bl.blocks + 0.3, { gain: 0.6 });

  // ---------------- 03:22 close ----------------
  const cn = B.connects.cue,
    tg = B.tagline.cue;
  glide(B.connects.start - 0.4, 1.2, 0.8, 0, false);
  words([cn.identity - 0.3, cn.identity]);
  words([cn.protection - 0.4, cn.protection, cn.protection + 0.4]);
  chord(cn.protection + 0.1, CH.warm, 1.4, 0.5, true);
  air(B.tagline.start - 0.75, 0.4, 0.6);
  sweep(B.tagline.start - 0.35, 1.0); // light sweep to the white stage
  bwoom(B.tagline.start - 0.1, 0.55, 1.2, 60);
  words([tg.know, tg.every1, tg.animal, tg.protect, tg.every2, tg.asset]);
  chord(tg.asset, ["D2", "A2", "D3", "F#3", "A3", "E4"], 1.6, 1.0); // the resolve under the tagline
  bwoom(tg.asset, 0.6, 1.4, 55);
  click(Math.min(D - 0.3, tg.asset + 0.9), 0.5);
}
