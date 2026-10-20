import { render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { describe, expect, it } from "vitest";
import { factLink, missingCallout, missingCopy, restatesMissing, type AssistantAnswer } from "./answer";
import { AnswerCard } from "./AnswerCard";

const records = { animals: [], last_observations: [], coverage: [], alerts: [] };

function renderAnswer(answer: AssistantAnswer) {
  return render(
    <MemoryRouter>
      <AnswerCard answer={answer} />
    </MemoryRouter>,
  );
}

describe("AnswerCard", () => {
  it("shows the recovery instead of repeating a gap the answer already states", () => {
    renderAnswer({
      intent: "location_lookup",
      parsed_by: "simulated",
      answer: "No camera observation is on record for Dewi (animal-demo-005).",
      facts: [],
      records: { ...records, animals: [{ id: "animal-demo-005", name: "Dewi" }] },
      missing: ["last_observation"],
      fallback_reason: "llm_offline",
    });
    const missing = screen.getByRole("list", { name: "Missing evidence" });
    expect(within(missing).queryByText("No camera observation is on record for Dewi.")).not.toBeInTheDocument();
    expect(within(missing).getByText("Link a pen camera track to Dewi to place it.")).toBeInTheDocument();
    expect(within(missing).getByRole("link", { name: /Open Monitor/ })).toHaveAttribute("href", "/monitor?animal=animal-demo-005");
    expect(screen.getByText(/Parsed offline/)).toBeInTheDocument();
  });

  it("links facts to their records and credits a live parse", () => {
    renderAnswer({
      intent: "location_lookup",
      parsed_by: "live",
      answer: "Sari (animal-demo-001) was last observed on Pen A.",
      facts: [
        { label: "Last observed on", value: "Pen A · feed line", record_type: "camera", record_id: "cam-pen-a" },
        { label: "Coverage", value: "none", record_type: "animal", record_id: "animal-demo-001" },
      ],
      records: { ...records, animals: [{ id: "animal-demo-001", name: "Sari" }] },
      missing: ["active_policy"],
      fallback_reason: null,
    });
    expect(screen.getByText("No active policy is on record for Sari.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Open in Monitor/ })).toHaveAttribute(
      "href",
      "/monitor?camera=cam-pen-a&animal=animal-demo-001",
    );
    expect(screen.getByRole("link", { name: /Open passport/ })).toHaveAttribute("href", "/animals/animal-demo-001");
    expect(screen.getByText(/The language model parsed this question/)).toBeInTheDocument();
    expect(screen.queryByText(/Parsed offline/)).not.toBeInTheDocument();
  });
});

describe("answer helpers", () => {
  it("never drops an unknown missing code", () => {
    expect(missingCopy("teeth_photo", "Bima")).toBe("Not on record: teeth photo for Bima.");
    expect(missingCopy("last_observation", null)).toBe("No camera observation is on record for this animal.");
  });

  it("spots a callout the answer already states, ignoring IDs and wording", () => {
    const dewi = "No camera observation is on record for Dewi (animal-demo-005).";
    expect(restatesMissing(dewi, "last_observation", missingCopy("last_observation", "Dewi"))).toBe(true);
    expect(restatesMissing("Sari has no active coverage.", "active_policy", missingCopy("active_policy", "Sari"))).toBe(true);
    expect(restatesMissing("Sari was last observed on Pen A.", "active_policy", missingCopy("active_policy", "Sari"))).toBe(false);
  });

  it("keeps the plain statement when it is news, and the recovery when it is not", () => {
    const sari = { id: "animal-demo-001", name: "Sari" };
    expect(missingCallout("Sari was last observed on Pen A.", "active_policy", sari)).toEqual({
      text: "No active policy is on record for Sari.",
    });
    expect(missingCallout("Sari has no active coverage.", "active_policy", sari)).toEqual({
      text: "Prepare an application from the passport.",
      link: { to: "/animals/animal-demo-001/insurance", label: "Compare cover" },
    });
    expect(missingCallout("No animals have open alerts.", "alerts", null)).toBeNull();
  });

  it("sends alerts to the drawer", () => {
    expect(factLink({ label: "x", value: "y", record_type: "alert", record_id: "alr-1" }, null)).toEqual({
      to: "/alerts/alr-1",
      label: "Open alert",
    });
  });
});
