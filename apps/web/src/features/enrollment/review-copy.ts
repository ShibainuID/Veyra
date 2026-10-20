/**
 * Plain-language copy for the review reasons the enrollment worker returns (`review_reasons`). Codes come
 * from workers/video_enrollment.py, adapters/perception.py, and workers/enrollment_job.py (estimator reasons
 * arrive prefixed `weight_` / `age_`).
 *
 * `override` marks the reasons the server will only let past with a written override note when the animal
 * is registered as new (domain/enrollment.py `_register_new`).
 */

export type ReasonTone = "danger" | "uncertain" | "neutral";

export interface ReasonCopy {
  code: string;
  title: string;
  detail?: string;
  tone: ReasonTone;
  /** Registering as new needs an override note while this reason stands. */
  override: boolean;
}

type Entry = Omit<ReasonCopy, "code">;

const COPY: Record<string, Entry> = {
  footage_not_attached: {
    title: "No footage attached",
    detail: "The views come from the prepared sample's timings, so there are no frames to show.",
    tone: "neutral",
    override: false,
  },
  video_missing: {
    title: "No video on this enrollment",
    detail: "Record or upload the guided video, then process it again.",
    tone: "danger",
    override: false,
  },
  video_unreadable: {
    title: "The video couldn't be read",
    detail: "Record it again, or upload an MP4, WebM, or MOV file.",
    tone: "danger",
    override: false,
  },
  muzzle_view_missing: {
    title: "Muzzle view missing — retake or confirm with a reason",
    detail: "Without a muzzle frame there is nothing to match. A new animal stays pending review.",
    tone: "uncertain",
    override: true,
  },
  teeth_view_missing: {
    title: "Teeth view missing — retake or confirm with a reason",
    detail: "The age range can't be checked against the teeth.",
    tone: "uncertain",
    override: true,
  },
  body_view_missing: {
    title: "Body view missing — retake or confirm with a reason",
    detail: "No side view means no weight estimate from the image.",
    tone: "uncertain",
    override: true,
  },
  scene_cut_detected: {
    title: "The video has a cut",
    detail: "The views may not all be the same animal. Record one continuous video.",
    tone: "uncertain",
    override: false,
  },
  marker_not_detected: {
    title: "ArUco marker not found on the flank",
    detail: "The body view has no scale reference, so the weight range is wider.",
    tone: "uncertain",
    override: false,
  },
  multiple_cows_in_body_view: {
    title: "More than one animal in the body view",
    detail: "The weight may belong to the wrong animal. Retake with one animal in frame.",
    tone: "uncertain",
    override: false,
  },
  views_out_of_guided_order: {
    title: "Views out of the guided order",
    detail: "The guide runs muzzle, teeth, then body. Check each frame shows the right view.",
    tone: "uncertain",
    override: false,
  },
  fixture_view_assignment: {
    title: "Views placed by position in the video, not detected",
    detail: "The prototype model isn't running here, so frames were taken at fixed points. Check each one.",
    tone: "uncertain",
    override: false,
  },
  possible_duplicate: {
    title: "Possible duplicate",
    detail: "This muzzle matches an animal already on the farm. Link to it, or register as new with a reason.",
    tone: "uncertain",
    override: true,
  },
  identity_uncertain: {
    title: "Identity uncertain",
    detail:
      "The muzzle evidence is too weak to match or clear. A new animal stays pending review, and financial actions are blocked until it is confirmed.",
    tone: "uncertain",
    override: true,
  },
  processing_failed: {
    title: "Processing failed",
    detail: "Nothing could be read from this enrollment. Try again.",
    tone: "danger",
    override: false,
  },
  perception_unavailable: {
    title: "Perception unavailable",
    detail: "The video model didn't run, so the views come from fixtures.",
    tone: "uncertain",
    override: false,
  },
  weight_unavailable: {
    title: "No weight estimate",
    detail: "Enter or confirm the weight when you confirm the valuation.",
    tone: "uncertain",
    override: false,
  },
  weight_marker_not_detected: {
    title: "Weight: no marker on the flank",
    detail: "Without the printed marker the image has no scale.",
    tone: "uncertain",
    override: false,
  },
  weight_no_cow_detected: {
    title: "Weight: no animal found in the body view",
    tone: "uncertain",
    override: false,
  },
  weight_withers_height_implausible: {
    title: "Weight: the measured height looks wrong",
    detail: "Check the body frame and the marker before using the weight.",
    tone: "uncertain",
    override: false,
  },
  weight_formulas_disagree: {
    title: "Weight: the estimating formulas disagree",
    detail: "Treat the range as rough until the weight is measured.",
    tone: "uncertain",
    override: false,
  },
  weight_animal_touches_frame_edge: {
    title: "Weight: the animal runs off the edge of the frame",
    tone: "uncertain",
    override: false,
  },
  weight_pose_check_failed: {
    title: "Weight: the animal isn't standing square to the camera",
    tone: "uncertain",
    override: false,
  },
  age_teeth_view_missing: {
    title: "Age: no teeth frame",
    detail: "The age range wasn't checked against the teeth.",
    tone: "uncertain",
    override: false,
  },
  age_no_fixture_for_sample: {
    title: "Age: no estimate for this sample",
    detail: "Enter the birth date if you know it.",
    tone: "uncertain",
    override: false,
  },
};

/** "weight_review_required" → "Weight review required". */
export function humanizeCode(code: string): string {
  const text = code.replace(/[_-]+/g, " ").trim();
  return text ? text[0]!.toUpperCase() + text.slice(1) : code;
}

export function reasonCopy(code: string): ReasonCopy {
  const entry = COPY[code];
  if (entry) return { code, ...entry };
  if (code.endsWith("_view_missing")) {
    const view = code.slice(0, -"_view_missing".length);
    return {
      code,
      title: `${humanizeCode(view)} view missing — retake or confirm with a reason`,
      tone: "uncertain",
      override: true,
    };
  }
  return { code, title: humanizeCode(code), tone: "uncertain", override: false };
}

/** Each reason once, the ones that block a plain registration first. */
export function reviewReasons(codes: readonly string[]): ReasonCopy[] {
  const unique = [...new Set(codes)].map(reasonCopy);
  const rank = (r: ReasonCopy) => (r.tone === "danger" ? 0 : r.override ? 1 : r.tone === "uncertain" ? 2 : 3);
  return unique.sort((a, b) => rank(a) - rank(b));
}

/** Server-side identity reasons (Identity.reason). */
export function identityReasonCopy(reason: string | null | undefined): string | null {
  switch (reason) {
    case null:
    case undefined:
      return null;
    case "no_verified_match":
      return "No animal on the farm matched with enough verified points.";
    case "insufficient_quality":
      return "The muzzle frame was too unclear to compare.";
    case "no_muzzle_view":
      return "There was no muzzle frame to compare.";
    default:
      return humanizeCode(reason);
  }
}
