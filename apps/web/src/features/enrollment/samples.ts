import type { AnimalIn } from "./rules";

/**
 * The prepared demo samples (demo/fixtures/enrollment_samples.json). They carry view timings and a simulated
 * identity, but no footage. The proposed animal pre-fills the confirm form; the server would fall back to the
 * same values if the form were sent empty.
 */
export interface DemoSample {
  key: string;
  label: string;
  expect: string;
  proposed: AnimalIn;
}

export const DEMO_SAMPLES: readonly DemoSample[] = [
  {
    key: "sample-enrollment-001",
    label: "Sari · guided video",
    expect: "A new animal with all three views.",
    proposed: { name: "Sari", breed: "Bali cattle", breed_category: "beef", sex: "F" },
  },
  {
    key: "sample-enrollment-dup",
    label: "Duplicate check · Bima again",
    expect: "The muzzle matches an animal already on the farm.",
    proposed: { name: "Unnamed", breed: "Ongole", breed_category: "beef", sex: "M" },
  },
  {
    key: "sample-enrollment-unclear",
    label: "Unclear muzzle · retry needed",
    expect: "No usable muzzle view, so the identity stays uncertain.",
    proposed: { name: "Unnamed", breed: "Bali cattle", breed_category: "beef", sex: "F" },
  },
];

export function sampleFor(key: string | null | undefined): DemoSample | undefined {
  return DEMO_SAMPLES.find((s) => s.key === key);
}
