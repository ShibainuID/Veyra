import type { components } from "../../lib/api-types";

export type Enrollment = components["schemas"]["EnrollmentOut"];
export type EnrollmentCreated = components["schemas"]["EnrollmentCreated"];
export type Identity = components["schemas"]["Identity"];
export type Candidate = components["schemas"]["Candidate"];
export type ViewOut = components["schemas"]["ViewOut"];
export type AnimalIn = components["schemas"]["AnimalIn"];
export type Decision = components["schemas"]["ConfirmBody"]["decision"];

export const REQUIRED_VIEWS = ["muzzle", "teeth", "body"] as const;
export type RequiredView = (typeof REQUIRED_VIEWS)[number];

export type OverrideReason =
  | "possible_duplicate"
  | "required_views_missing"
  | "identity_uncertain"
  | "not_matching_candidate";

type Decidable = Pick<Enrollment, "manifest" | "identity">;

export function missingViews(enrollment: Decidable): RequiredView[] {
  const views = enrollment.manifest?.views ?? {};
  return REQUIRED_VIEWS.filter((view) => !(view in views));
}

export function isPossibleDuplicate(identity: Identity | null | undefined): boolean {
  return identity?.outcome === "candidate" || Boolean(identity?.possible_duplicate);
}

/**
 * Why a decision needs a written note. Registering as new mirrors the server (domain/enrollment.py
 * `_register_new`); linking to an animal that is not the proposed candidate is held to the same standard here.
 */
export function overrideReasons(enrollment: Decidable, decision: Decision, linkTo: string | null): OverrideReason[] {
  const identity = enrollment.identity;
  if (decision === "register_new") {
    const reasons: OverrideReason[] = [];
    if (isPossibleDuplicate(identity)) reasons.push("possible_duplicate");
    if (missingViews(enrollment).length > 0) reasons.push("required_views_missing");
    if (identity?.outcome === "uncertain") reasons.push("identity_uncertain");
    return reasons;
  }
  if (decision === "link_existing") {
    const suggested = identity?.outcome === "candidate" ? identity.animal_id : null;
    return linkTo && suggested !== linkTo ? ["not_matching_candidate"] : [];
  }
  return [];
}

export const OVERRIDE_COPY: Record<OverrideReason, string> = {
  possible_duplicate: "the muzzle matches an animal already on the farm",
  required_views_missing: "a required view is missing",
  identity_uncertain: "the identity is uncertain",
  not_matching_candidate: "this isn't the animal the muzzle matched",
};

/** A new animal is created pending review (no financial actions) without a muzzle view or with an uncertain identity. */
export function registersPending(enrollment: Decidable): boolean {
  return missingViews(enrollment).includes("muzzle") || enrollment.identity?.outcome === "uncertain";
}

/** The best candidate to link to, if the outcome proposes one. */
export function proposedCandidate(identity: Identity | null | undefined): Candidate | null {
  if (!identity || identity.outcome !== "candidate" || !identity.animal_id) return null;
  return (
    identity.candidates.find((c) => c.animal_id === identity.animal_id) ?? {
      animal_id: identity.animal_id,
      animal_name: identity.animal_name ?? null,
    }
  );
}
