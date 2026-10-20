import type { components } from "../../lib/api-types";

export type AssistantAnswer = components["schemas"]["AssistantAnswer"];
export type AssistantFact = components["schemas"]["AssistantFact"];

export const ASK_PLACEHOLDER = "Ask about an animal, a location, coverage, or alerts";

export const SUGGESTED_QUERIES = [
  "Where was animal-demo-001 last seen, and what coverage is active?",
  "Show me animal-demo-002",
  "Which animals have open alerts?",
] as const;

interface AnimalRecord {
  id?: unknown;
  name?: unknown;
}

/** The animal the answer is about, if it names exactly one. */
export function answerAnimal(answer: AssistantAnswer): { id: string; name: string } | null {
  const animals = (answer.records?.animals ?? []) as AnimalRecord[];
  if (animals.length !== 1) return null;
  const a = animals[0]!;
  if (typeof a.id !== "string") return null;
  return { id: a.id, name: typeof a.name === "string" ? a.name : a.id };
}

/**
 * Missing evidence, stated plainly ("No camera observation is on record for Dewi"). The codes come from
 * domain/assistant.py; unknown codes still read as missing rather than disappearing.
 */
export function missingCopy(code: string, animalName: string | null): string {
  const subject = animalName ?? "this animal";
  switch (code) {
    case "last_observation":
      return `No camera observation is on record for ${subject}.`;
    case "active_policy":
      return `No active policy is on record for ${subject}.`;
    case "coverage":
      return `No coverage record is on file for ${subject}.`;
    case "valuation":
      return `No confirmed valuation is on record for ${subject}.`;
    case "animal":
      return "No animal on this farm matches the question.";
    case "alerts":
      return "No open alerts are on record.";
    default: {
      const text = code.replace(/[_-]+/g, " ");
      return `Not on record: ${text}${animalName ? ` for ${animalName}` : ""}.`;
    }
  }
}

export type FactLink = { to: string; label: string } | null;

/** Where a fact's record lives in the app. Cameras open Monitor focused on the animal the answer is about. */
export function factLink(fact: AssistantFact, animalId: string | null): FactLink {
  const id = fact.record_id;
  switch (fact.record_type) {
    case "animal":
      return { to: `/animals/${encodeURIComponent(id)}`, label: "Open passport" };
    case "alert":
      return { to: `/alerts/${encodeURIComponent(id)}`, label: "Open alert" };
    case "camera":
    case "observation": {
      const params = new URLSearchParams();
      if (fact.record_type === "camera") params.set("camera", id);
      if (animalId) params.set("animal", animalId);
      const query = params.toString();
      return { to: `/monitor${query ? `?${query}` : ""}`, label: "Open in Monitor" };
    }
    default:
      return null;
  }
}

const ISO_INSTANT = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2}(\.\d+)?)?(Z|[+-]\d{2}:?\d{2})$/;

export function isInstant(value: unknown): value is string {
  return typeof value === "string" && ISO_INSTANT.test(value);
}

export function factText(value: unknown): string {
  if (value === null || value === undefined) return "Not on record";
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  return JSON.stringify(value);
}
