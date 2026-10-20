import { describe, expect, it } from "vitest";
import { MUZZLE_GUIDE_ASPECT, muzzleGuideBox, promptIndexAt } from "./guide-box";
import { overrideReasons } from "./rules";
import { humanizeCode, reasonCopy, reviewReasons } from "./review-copy";

describe("muzzleGuideBox", () => {
  it("is 90% of the width at 1.18 on a portrait frame, centred", () => {
    // Python: cw = int(0.9 * 1080) = 972; ch = min(1920, int(972 / 1.18)) = 823; cw = min(972, int(823 * 1.18)) = 971
    expect(muzzleGuideBox(1080, 1920)).toEqual({ x: 54, y: 548, width: 971, height: 823 });
  });

  it("is limited by the height on a landscape frame, exactly like the ML crop", () => {
    // Python: cw = int(0.9 * 1920) = 1728; ch = min(1080, int(1728 / 1.18)) = 1080; cw = min(1728, int(1080 * 1.18)) = 1274
    expect(muzzleGuideBox(1920, 1080)).toEqual({ x: 323, y: 0, width: 1274, height: 1080 });
    expect(muzzleGuideBox(1280, 720)).toEqual({ x: 215, y: 0, width: 849, height: 720 });
  });

  it("keeps the 1.18 aspect within a pixel and never leaves the frame", () => {
    for (const [w, h] of [
      [640, 480],
      [480, 640],
      [1920, 1080],
      [1000, 1000],
      [333, 777],
    ] as const) {
      const box = muzzleGuideBox(w, h);
      expect(box.x).toBeGreaterThanOrEqual(0);
      expect(box.y).toBeGreaterThanOrEqual(0);
      expect(box.x + box.width).toBeLessThanOrEqual(w);
      expect(box.y + box.height).toBeLessThanOrEqual(h);
      expect(Math.abs(box.width / box.height - MUZZLE_GUIDE_ASPECT)).toBeLessThan(0.01);
      expect(box.width).toBeLessThanOrEqual(Math.trunc(0.9 * w));
    }
  });

  it("returns an empty box for an empty frame", () => {
    expect(muzzleGuideBox(0, 0)).toEqual({ x: 0, y: 0, width: 0, height: 0 });
  });
});

describe("promptIndexAt", () => {
  it("walks muzzle, teeth, then body and holds on body", () => {
    expect(promptIndexAt(0)).toBe(0);
    expect(promptIndexAt(5.9)).toBe(0);
    expect(promptIndexAt(6)).toBe(1);
    expect(promptIndexAt(12)).toBe(2);
    expect(promptIndexAt(600)).toBe(2);
  });
});

describe("review reason copy", () => {
  it("maps the worker's codes to plain language", () => {
    expect(reasonCopy("muzzle_view_missing").title).toBe("Muzzle view missing — retake or confirm with a reason");
    expect(reasonCopy("muzzle_view_missing").override).toBe(true);
    expect(reasonCopy("scene_cut_detected").title).toBe("The video has a cut");
    expect(reasonCopy("marker_not_detected").title).toMatch(/ArUco marker/);
    expect(reasonCopy("fixture_view_assignment").title).toMatch(/not detected/);
    expect(reasonCopy("footage_not_attached")).toMatchObject({ title: "No footage attached", tone: "neutral", override: false });
    expect(reasonCopy("possible_duplicate")).toMatchObject({ title: "Possible duplicate", override: true });
    expect(reasonCopy("identity_uncertain").detail).toMatch(/financial actions are blocked/);
    expect(reasonCopy("age_teeth_view_missing").override).toBe(false);
  });

  it("still reads unknown codes as words, and new missing views as overrides", () => {
    expect(reasonCopy("weight_review_required").title).toBe("Weight review required");
    expect(reasonCopy("flank_view_missing")).toMatchObject({
      title: "Flank view missing — retake or confirm with a reason",
      override: true,
    });
    expect(humanizeCode("")).toBe("");
  });

  it("lists each reason once, blocking ones first", () => {
    const list = reviewReasons(["footage_not_attached", "possible_duplicate", "footage_not_attached", "video_unreadable"]);
    expect(list.map((r) => r.code)).toEqual(["video_unreadable", "possible_duplicate", "footage_not_attached"]);
  });
});

describe("override rules", () => {
  const base = { manifest: { views: { muzzle: {}, teeth: {}, body: {} } }, identity: { outcome: "new", possible_duplicate: false } };

  it("needs no note for a clean new animal", () => {
    expect(overrideReasons(base as never, "register_new", null)).toEqual([]);
  });

  it("mirrors the server for duplicates, missing views, and uncertain identity", () => {
    const dup = { ...base, identity: { outcome: "candidate", animal_id: "animal-demo-002", possible_duplicate: true } };
    expect(overrideReasons(dup as never, "register_new", null)).toEqual(["possible_duplicate"]);
    expect(overrideReasons(dup as never, "link_existing", "animal-demo-002")).toEqual([]);
    expect(overrideReasons(dup as never, "link_existing", "animal-demo-003")).toEqual(["not_matching_candidate"]);
    const unclear = { manifest: { views: { teeth: {}, body: {} } }, identity: { outcome: "uncertain", possible_duplicate: false } };
    expect(overrideReasons(unclear as never, "register_new", null)).toEqual(["required_views_missing", "identity_uncertain"]);
  });
});
